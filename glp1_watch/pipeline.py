from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from .config import LOOKBACK_DAYS
from .catalyst_score import compute_catalyst_score
from .confirmation_state import (
    assess_leader,
    assess_stack,
    build_contradiction,
    classify_confirmation_state,
)
from .decision_weights import load_decision_weights
from .expectations_risk import compute_expectations_risk
from .health_stack_sleeves import (
    SUPPORTING_SLEEVE_NAME,
    core_breadth_tickers,
    load_sleeve_config,
)
from .market_confirmation import compute_market_confirmation
from .opportunity import compute_opportunity_scores
from .structural_thesis import compute_structural_thesis
from .leadership_concentration import (
    LEADER_SLEEVE_NAME,
    SLEEVE_STATUS_INSUFFICIENT,
    build_sleeve_summaries,
    compute_leadership_concentration,
)
from .market_data import MarketSnapshot, load_market_snapshot
from .news import NewsSnapshot, fetch_news_snapshot
from .news_event_clustering import cluster_news_events, summarize_event_counts
from .reporting import (
    append_score_history,
    write_articles_csv,
    write_performance_csv,
    write_report,
    write_validation_file,
)
from .scoring import compute_score_snapshot, qualified_scoring_articles


def format_percent_or_unknown(value: object) -> str:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return "Unknown"
    return f"{float(parsed):.1%}"



def finite_ratio(series: pd.Series) -> tuple[int, int, float]:
    if series.empty:
        return 0, 0, 0.0
    numeric = pd.to_numeric(series, errors="coerce")
    usable = int(numeric.notna().sum())
    total = int(len(numeric))
    return usable, total, usable / total if total else 0.0


def build_market_data_quality(performance_table: pd.DataFrame) -> dict[str, object]:
    if performance_table.empty:
        return {
            "status": "Low",
            "ticker_rows": 0,
            "price_count": 0,
            "return_3m_count": 0,
            "rs_cell_count": 0,
            "rs_cell_total": 0,
            "price_coverage": 0.0,
            "return_3m_coverage": 0.0,
            "rs_coverage": 0.0,
            "note": "No ticker market rows were available for this run.",
        }

    price_count, ticker_rows, price_coverage = finite_ratio(performance_table.get("price", pd.Series(dtype=float)))
    return_3m_count, _, return_3m_coverage = finite_ratio(performance_table.get("return_3m", pd.Series(dtype=float)))
    rs_columns = [column for column in ["rs_vs_xlv", "rs_vs_qqq", "rs_vs_spy"] if column in performance_table.columns]
    if rs_columns:
        rs_values = pd.Series(performance_table[rs_columns].to_numpy().ravel())
        rs_cell_count, rs_cell_total, rs_coverage = finite_ratio(rs_values)
    else:
        rs_cell_count, rs_cell_total, rs_coverage = 0, 0, 0.0

    if price_coverage >= 0.85 and return_3m_coverage >= 0.85 and rs_coverage >= 0.75:
        status = "High"
    elif price_coverage >= 0.50 or return_3m_coverage >= 0.50:
        status = "Partial"
    else:
        status = "Low"

    note = (
        f"{return_3m_count} of {ticker_rows} tickers have usable 3M returns; "
        f"{price_count} have latest prices; {rs_cell_count} of {rs_cell_total} RS cells are usable."
    )
    if status != "High":
        note += " Treat market confirmation as incomplete until price coverage improves."

    return {
        "status": status,
        "ticker_rows": ticker_rows,
        "price_count": price_count,
        "return_3m_count": return_3m_count,
        "rs_cell_count": rs_cell_count,
        "rs_cell_total": rs_cell_total,
        "price_coverage": round(price_coverage, 3),
        "return_3m_coverage": round(return_3m_coverage, 3),
        "rs_coverage": round(rs_coverage, 3),
        "note": note,
    }


def numeric_or_none(value: object) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return float(parsed)


def relative_delta(primary: object, comparator: object) -> float | None:
    primary_value = numeric_or_none(primary)
    comparator_value = numeric_or_none(comparator)
    if primary_value is None or comparator_value is None:
        return None
    return primary_value - comparator_value

def top_names(performance_table: pd.DataFrame, groups: list[str], ascending: bool = False, limit: int = 3) -> str:
    if performance_table.empty:
        return "No market data"
    subset = performance_table[performance_table["group"].isin(groups)].copy()
    if subset.empty:
        return "No data"
    subset["return_3m"] = pd.to_numeric(subset["return_3m"], errors="coerce")
    subset = subset.dropna(subset=["return_3m"])
    if subset.empty:
        return "Insufficient market data"
    ranked = subset.sort_values("return_3m", ascending=ascending).head(limit)
    return ", ".join(f"{row.ticker} ({row.return_3m:.1%})" for row in ranked.itertuples())


def summarize_themes(news_snapshot: NewsSnapshot, themes: list[str]) -> str:
    if news_snapshot.theme_summary.empty:
        return "No RSS themes available"
    subset = news_snapshot.theme_summary[news_snapshot.theme_summary["theme"].isin(themes)].head(3)
    if subset.empty:
        return "No matching themes"
    return ", ".join(f"{row.theme} ({int(row.story_count)})" for row in subset.itertuples())


def build_interpretation(stance: str, overall_score: float, lly_ai_trade_score: float) -> str:
    if stance in {"Strong Bullish", "Bullish"}:
        return (
            f"The dashboard still supports the thesis: GLP-1 cash flows and AI-health infrastructure are "
            f"confirming one another, with a {overall_score:.1f} flywheel score and a {lly_ai_trade_score:.1f} "
            "LLY AI-trade confirmation score."
        )
    if stance == "Neutral":
        return (
            f"The thesis remains live but mixed. The flywheel score at {overall_score:.1f} suggests partial "
            "confirmation rather than broad-based leadership."
        )
    return (
        f"The dashboard is weakening the thesis for now. A {overall_score:.1f} flywheel score implies the "
        "market or news backdrop is not yet validating the GLP-1-to-AI flywheel."
    )


def summarize_component_drivers(component_scores: pd.DataFrame) -> tuple[list[str], list[str]]:
    if component_scores.empty:
        return [], []

    ranked = component_scores.copy()
    ranked["contribution"] = ranked["weighted_score"] - (50.0 * ranked["weight"])
    positive = ranked.sort_values("contribution", ascending=False).head(3)
    negative = ranked.sort_values("contribution", ascending=True).head(3)
    positive_labels = [
        f"{row.component} ({row.score:.1f}/100)"
        for row in positive.itertuples()
        if row.contribution > 0
    ]
    negative_labels = [
        f"{row.component} ({row.score:.1f}/100)"
        for row in negative.itertuples()
        if row.contribution < 0
    ]
    return positive_labels, negative_labels


def build_driver_interpretation(
    stance: str,
    overall_score: float,
    lly_ai_trade_score: float,
    positive_drivers: list[str],
    negative_drivers: list[str],
    news_confidence: str,
    accepted_story_count: int,
    qualified_story_count: int,
    market_data_quality: dict[str, object] | None = None,
) -> str:
    base = build_interpretation(stance, overall_score, lly_ai_trade_score)
    positive_text = ", ".join(positive_drivers) if positive_drivers else "no major positive drivers stood out"
    negative_text = ", ".join(negative_drivers) if negative_drivers else "no major negative drivers stood out"
    coverage_text = (
        f"{qualified_story_count} of {accepted_story_count} accepted stories qualified for scoring"
        if accepted_story_count
        else "no accepted stories qualified for scoring"
    )
    market_text = ""
    if market_data_quality and market_data_quality.get("status") != "High":
        market_text = f" Market data quality is {str(market_data_quality.get('status')).lower()}: {market_data_quality.get('note')}"
    return (
        f"{base} The strongest confirming drivers were {positive_text}. "
        f"The main drags were {negative_text}. News confidence for this run is {news_confidence.lower()}, and "
        f"{coverage_text}.{market_text}"
    )

def build_news_confidence(articles_df: pd.DataFrame) -> tuple[str, str]:
    qualified_articles = qualified_scoring_articles(articles_df)
    qualified_story_count = len(qualified_articles)
    qualified_theme_count = int(qualified_articles["theme"].nunique()) if not qualified_articles.empty else 0

    if qualified_story_count < 5:
        return "Low", "Fewer than 5 qualified non-Other stories survived the quality filters, so news confidence is low."
    if qualified_story_count < 15 or qualified_theme_count < 3:
        return "Moderate", "Qualified news breadth is improving, but the story set is still somewhat narrow, so news confidence is moderate."
    return "High", "A healthy number of qualified non-Other stories survived the quality filters across multiple themes, so news confidence is high."


def summarize_ticker_counts(accepted_by_ticker: pd.DataFrame) -> str:
    if accepted_by_ticker.empty:
        return "No accepted ticker-tagged stories"
    top_rows = accepted_by_ticker.head(5)
    return ", ".join(f"{row.ticker} ({int(row.story_count)})" for row in top_rows.itertuples())


def build_dashboard_snapshot(
    write_outputs: bool = True,
    lookback_days: int = LOOKBACK_DAYS,
    force_market_refresh: bool = False,
) -> dict:
    market_error = None
    try:
        market_snapshot = load_market_snapshot(
            lookback_days=lookback_days,
            force_refresh=force_market_refresh,
        )
    except Exception as exc:
        market_error = str(exc)
        market_snapshot = MarketSnapshot(
            price_history=pd.DataFrame(),
            performance_table=pd.DataFrame(
                columns=[
                    "ticker",
                    "price",
                    "return_5d",
                    "return_1m",
                    "return_3m",
                    "return_6m",
                    "return_ytd",
                    "above_50dma",
                    "above_200dma",
                    "distance_from_52w_high",
                    "rs_vs_xlv",
                    "rs_vs_qqq",
                    "rs_vs_spy",
                    "group",
                    "is_benchmark",
                ]
            ),
            layer_performance=pd.DataFrame(columns=["group", "return_5d", "return_1m", "return_3m", "return_6m"]),
            ticker_diagnostics={"requested_count": 0, "active_tickers": [], "exceptions": []},
        )
    try:
        news_snapshot = fetch_news_snapshot(write_raw_json=write_outputs)
    except Exception as exc:
        news_snapshot = NewsSnapshot(
            articles=pd.DataFrame(),
            rejected_articles=pd.DataFrame(),
            theme_summary=pd.DataFrame(columns=["theme", "story_count", "avg_sentiment"]),
            sentiment_summary=pd.DataFrame(columns=["sentiment_label", "story_count"]),
            fetch_errors=[str(exc)],
            raw_payload_path=None,
            total_fetched=0,
            rejected_by_relevance_gate=0,
            rejected_by_exclusion_filter=0,
            accepted_story_count=0,
            accepted_by_theme=pd.DataFrame(columns=["theme", "story_count"]),
            accepted_by_ticker=pd.DataFrame(columns=["ticker", "story_count"]),
        )

    score_snapshot = compute_score_snapshot(
        market_snapshot.performance_table,
        news_snapshot.articles,
    )

    as_of_dt = datetime.now(timezone.utc)
    as_of_stamp = as_of_dt.strftime("%Y%m%dT%H%M%SZ")
    performance = market_snapshot.performance_table
    lly_rows = performance.loc[performance["ticker"] == "LLY"] if not performance.empty else pd.DataFrame()
    lly = lly_rows.squeeze() if not lly_rows.empty else pd.Series(dtype=float)

    layer_perf = market_snapshot.layer_performance
    best_layers = {
        "1w": layer_perf.sort_values("return_5d", ascending=False).iloc[0]["group"] if not layer_perf.empty else "N/A",
        "1m": layer_perf.sort_values("return_1m", ascending=False).iloc[0]["group"] if not layer_perf.empty else "N/A",
        "3m": layer_perf.sort_values("return_3m", ascending=False).iloc[0]["group"] if not layer_perf.empty else "N/A",
        "6m": layer_perf.sort_values("return_6m", ascending=False).iloc[0]["group"] if not layer_perf.empty else "N/A",
    }

    news_count_by_theme = (
        news_snapshot.theme_summary.set_index("theme")["story_count"].to_dict()
        if not news_snapshot.theme_summary.empty
        else {}
    )

    nvo_return = (
        numeric_or_none(performance.loc[performance["ticker"] == "NVO"]["return_3m"].iloc[0])
        if not performance.empty and "NVO" in performance["ticker"].values
        else None
    )
    xbi_return = (
        numeric_or_none(performance.loc[performance["ticker"] == "XBI"]["return_3m"].iloc[0])
        if not performance.empty and "XBI" in performance["ticker"].values
        else None
    )
    qualified_articles = qualified_scoring_articles(news_snapshot.articles)
    market_data_quality = build_market_data_quality(performance)
    news_confidence, news_confidence_note = build_news_confidence(news_snapshot.articles)
    positive_drivers, negative_drivers = summarize_component_drivers(score_snapshot.component_scores)

    # Phase 1: confirmation structure (sleeves, concentration, state, events).
    sleeves = load_sleeve_config()
    sleeve_summaries = build_sleeve_summaries(performance, sleeves)
    concentration = compute_leadership_concentration(performance, sleeve_summaries, sleeves)
    articles_with_events, news_events = cluster_news_events(news_snapshot.articles)
    news_event_counts = summarize_event_counts(news_events)
    qualified_theme_count = (
        int(qualified_articles["theme"].nunique()) if not qualified_articles.empty else 0
    )
    accepted_total = int(news_snapshot.accepted_story_count or 0)
    if not news_snapshot.accepted_by_ticker.empty and accepted_total:
        news_top_ticker_share = (
            float(news_snapshot.accepted_by_ticker["story_count"].max()) / accepted_total
        )
        news_top_ticker: str | None = str(news_snapshot.accepted_by_ticker.iloc[0]["ticker"])
    else:
        news_top_ticker_share = 0.0
        news_top_ticker = None
    leader_tickers = tuple(
        next(sleeve.tickers for sleeve in sleeves if sleeve.name == LEADER_SLEEVE_NAME)
    )
    core_names = core_breadth_tickers(sleeves)
    if not performance.empty and core_names:
        core_returns = pd.to_numeric(
            performance.loc[performance["ticker"].isin(core_names), "return_3m"],
            errors="coerce",
        ).dropna()
        core_coverage = len(core_returns) / len(core_names)
    else:
        core_coverage = 0.0
    def _sleeve_status_lookup(name: str) -> str:
        if sleeve_summaries.empty or name not in sleeve_summaries["sleeve"].values:
            return SLEEVE_STATUS_INSUFFICIENT
        return str(sleeve_summaries.set_index("sleeve").loc[name, "status"])

    leader_status = _sleeve_status_lookup(LEADER_SLEEVE_NAME)
    supporting_sleeve_status = _sleeve_status_lookup(SUPPORTING_SLEEVE_NAME)
    confirmation = classify_confirmation_state(
        overall_score=score_snapshot.overall_score,
        confirming_count=int(concentration["confirming_count"]),
        deteriorating_count=int(concentration["deteriorating_count"]),
        breadth_50dma=float(concentration["pct_above_50dma"]),
        concentration_verdict=str(concentration["verdict"]),
        leader_status=leader_status,
        market_data_quality=str(market_data_quality.get("status", "Unknown")),
        core_coverage=float(core_coverage),
        qualified_theme_count=qualified_theme_count,
        news_top_ticker_share=news_top_ticker_share,
        news_top_ticker=news_top_ticker,
        leader_tickers=leader_tickers,
        supporting_sleeve_status=supporting_sleeve_status,
    )
    leader_assessment = assess_leader(leader_status, score_snapshot.lly_ai_trade_score)
    stack_assessment = assess_stack(confirmation["state"])
    main_contradiction = build_contradiction(leader_assessment, stack_assessment)
    strongest_sleeve = concentration.get("strongest_sleeve")
    weakest_sleeve = concentration.get("weakest_sleeve")
    sleeve_status_by_name = (
        dict(zip(sleeve_summaries["sleeve"], sleeve_summaries["status"]))
        if not sleeve_summaries.empty
        else {}
    )
    strongest_status = sleeve_status_by_name.get(str(strongest_sleeve), "unknown")
    weakest_status = sleeve_status_by_name.get(str(weakest_sleeve), "unknown")
    main_positive_evidence = (
        f"{strongest_sleeve} ({strongest_status}); top drivers: {', '.join(positive_drivers[:2])}"
        if strongest_sleeve and positive_drivers
        else (
            f"{strongest_sleeve} ({strongest_status})" if strongest_sleeve else "None identified"
        )
    )
    main_negative_evidence = (
        f"{weakest_sleeve} ({weakest_status}); top drags: {', '.join(negative_drivers[:2])}"
        if weakest_sleeve and negative_drivers
        else (f"{weakest_sleeve} ({weakest_status})" if weakest_sleeve else "None identified")
    )
    accepted_story_count = news_snapshot.accepted_story_count
    qualified_story_count = len(qualified_articles)

    # Phase 2: sleeve-level opportunity scoring.
    decision_weights = load_decision_weights()
    structural_df = compute_structural_thesis(qualified_articles, sleeves)
    market_confirmation_df = compute_market_confirmation(
        performance, market_snapshot.price_history, sleeves, decision_weights
    )
    catalyst_df = compute_catalyst_score(
        news_events,
        articles_with_events,
        sleeves,
        decision_weights.catalyst_saturation_per_category,
    )
    expectations_df = compute_expectations_risk(
        performance,
        market_snapshot.price_history,
        qualified_articles,
        sleeves,
        decision_weights,
    )
    opportunity_ranking = compute_opportunity_scores(
        market_confirmation_df,
        structural_df,
        catalyst_df,
        expectations_df,
        sleeve_summaries,
        sleeves,
        decision_weights,
    )

    snapshot = {
        "as_of_date": as_of_dt.strftime("%Y-%m-%d %H:%M UTC"),
        "lookback_days": lookback_days,
        "force_market_refresh": force_market_refresh,
        "performance_table": performance,
        "layer_performance": market_snapshot.layer_performance,
        "ticker_diagnostics": market_snapshot.ticker_diagnostics,
        "price_history": market_snapshot.price_history,
        "articles": articles_with_events,
        "sleeve_summaries": sleeve_summaries,
        "leadership_concentration": concentration,
        "confirmation_state": confirmation["state"],
        "confirmation_reason": confirmation["reason"],
        "leader_assessment": leader_assessment,
        "stack_assessment": stack_assessment,
        "main_positive_evidence": main_positive_evidence,
        "main_negative_evidence": main_negative_evidence,
        "main_contradiction": main_contradiction,
        "news_events": news_events,
        "news_event_counts": news_event_counts,
        "structural_thesis": structural_df,
        "market_confirmation": market_confirmation_df,
        "catalyst_scores": catalyst_df,
        "expectations_risk": expectations_df,
        "opportunity_ranking": opportunity_ranking,
        "qualified_theme_count": qualified_theme_count,
        "news_top_ticker_share": round(news_top_ticker_share, 3),
        "news_top_ticker": news_top_ticker,
        "supporting_sleeve_status": supporting_sleeve_status,
        "rejected_articles": news_snapshot.rejected_articles,
        "theme_summary": news_snapshot.theme_summary,
        "sentiment_summary": news_snapshot.sentiment_summary,
        "fetch_errors": news_snapshot.fetch_errors,
        "market_error": market_error,
        "market_data_quality": market_data_quality,
        "raw_payload_path": news_snapshot.raw_payload_path,
        "news_stats": {
            "total_fetched": news_snapshot.total_fetched,
            "rejected_by_relevance_gate": news_snapshot.rejected_by_relevance_gate,
            "rejected_by_exclusion_filter": news_snapshot.rejected_by_exclusion_filter,
            "accepted": accepted_story_count,
            "qualified": qualified_story_count,
        },
        "accepted_by_theme": news_snapshot.accepted_by_theme,
        "accepted_by_ticker": news_snapshot.accepted_by_ticker,
        "news_confidence": news_confidence,
        "news_confidence_note": news_confidence_note,
        "overall_score": score_snapshot.overall_score,
        "stance": score_snapshot.stance,
        "lly_ai_trade_score": score_snapshot.lly_ai_trade_score,
        "component_scores": score_snapshot.component_scores,
        "best_layers": best_layers,
        "lly_outperformance": {
            "XLV": numeric_or_none(lly.get("rs_vs_xlv")),
            "QQQ": numeric_or_none(lly.get("rs_vs_qqq")),
            "SPY": numeric_or_none(lly.get("rs_vs_spy")),
            "NVO": relative_delta(lly.get("return_3m"), nvo_return),
            "XBI": relative_delta(lly.get("return_3m"), xbi_return),
        },
        "leadership_check": bool(
            not performance.empty and
            performance[performance["group"].isin(["Core GLP-1 Leaders", "GLP-1 Challengers"])]["return_3m"].mean()
            > performance[performance["is_benchmark"]]["return_3m"].mean()
        ),
        "ai_confirmation_check": bool(
            not performance.empty and
            performance[performance["group"] == "AI Drug Discovery Platforms"]["return_3m"].mean()
            > performance[performance["group"] == "Healthcare Benchmarks"]["return_3m"].mean()
        ),
        "news_count_by_theme": news_count_by_theme,
        "positive_themes": (
            news_snapshot.theme_summary.sort_values("avg_sentiment", ascending=False).head(3)["theme"].tolist()
            if not news_snapshot.theme_summary.empty
            else []
        ),
        "negative_themes": (
            news_snapshot.theme_summary.sort_values("avg_sentiment", ascending=True).head(3)["theme"].tolist()
            if not news_snapshot.theme_summary.empty
            else []
        ),
        "interpretation": build_interpretation(
            score_snapshot.stance,
            score_snapshot.overall_score,
            score_snapshot.lly_ai_trade_score,
        ),
        "positive_drivers": positive_drivers,
        "negative_drivers": negative_drivers,
        "driver_interpretation": build_driver_interpretation(
            score_snapshot.stance,
            score_snapshot.overall_score,
            score_snapshot.lly_ai_trade_score,
            positive_drivers,
            negative_drivers,
            news_confidence,
            accepted_story_count,
            qualified_story_count,
            market_data_quality,
        ),
        "lly_summary": (
            f"3M RS vs XLV {format_percent_or_unknown(lly.get('rs_vs_xlv'))}, "
            f"vs QQQ {format_percent_or_unknown(lly.get('rs_vs_qqq'))}, "
            f"vs SPY {format_percent_or_unknown(lly.get('rs_vs_spy'))}"
        ),
        "lly_trend_status": (
            f"Above 50DMA: {'Yes' if bool(lly.get('above_50dma')) else 'No'} | "
            f"Above 200DMA: {'Yes' if bool(lly.get('above_200dma')) else 'No'} | "
            f"Drawdown from 52W high: {format_percent_or_unknown(lly.get('distance_from_52w_high'))}"
        ),
        "lly_news_summary": (
            "No LLY-tagged Yahoo RSS stories detected"
            if news_snapshot.articles.empty
            else f"{len(news_snapshot.articles[news_snapshot.articles['tickers'].str.contains('LLY', na=False)])} LLY-tagged stories"
        ),
        "accepted_ticker_summary": summarize_ticker_counts(news_snapshot.accepted_by_ticker),
        "glp1_winners": top_names(performance, ["Core GLP-1 Leaders", "GLP-1 Challengers"], ascending=False),
        "glp1_losers": top_names(performance, ["Core GLP-1 Leaders", "GLP-1 Challengers"], ascending=True),
        "glp1_themes": summarize_themes(news_snapshot, ["GLP-1 Demand", "GLP-1 Competition", "Obesity Policy / Pricing"]),
        "ai_winners": top_names(performance, ["AI Drug Discovery Platforms", "Gene Editing / Cardiometabolic Adjacent"], ascending=False),
        "ai_losers": top_names(performance, ["AI Drug Discovery Platforms", "Gene Editing / Cardiometabolic Adjacent"], ascending=True),
        "ai_themes": summarize_themes(news_snapshot, ["AI Drug Discovery", "Longevity", "Cardiovascular / Gene Editing"]),
        "investor_interpretation": build_interpretation(
            score_snapshot.stance,
            score_snapshot.overall_score,
            score_snapshot.lly_ai_trade_score,
        ),
        "written_files": [],
    }
    snapshot["investor_interpretation"] = snapshot["driver_interpretation"]

    if write_outputs:
        written_files = [
            write_performance_csv(snapshot["performance_table"], as_of_stamp),
            write_articles_csv(snapshot["articles"], as_of_stamp),
            write_report(snapshot, as_of_stamp),
            append_score_history(snapshot),
        ]
        written_files.append(write_validation_file({**snapshot, "written_files": written_files}, as_of_stamp))
        snapshot["written_files"] = written_files

    return snapshot









