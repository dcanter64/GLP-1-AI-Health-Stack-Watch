from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from .config import LOOKBACK_DAYS, REPORTS_DIR
from .pipeline import build_dashboard_snapshot
from .visuals import (
    component_score_chart,
    lly_price_chart,
    lly_relative_chart,
    performance_heatmap,
    theme_bar_chart,
)


def report_paths(snapshot: dict) -> list[str]:
    return [
        str(path)
        for path in snapshot.get("written_files", [])
        if str(path).lower().endswith(".md") and "\\reports\\" in str(path).lower()
    ]


def latest_saved_report() -> Path | None:
    if not REPORTS_DIR.exists():
        return None
    reports = sorted(REPORTS_DIR.glob("glp1_ai_health_stack_watch_*.md"), key=lambda path: path.stat().st_mtime)
    return reports[-1] if reports else None


@st.cache_data(show_spinner=False, ttl=3600)
def load_snapshot(lookback_days: int, force_market_refresh: bool, refresh_nonce: int) -> dict:
    return build_dashboard_snapshot(
        write_outputs=True,
        lookback_days=lookback_days,
        force_market_refresh=force_market_refresh,
    )


def metric_text(value: object) -> str:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return "Unknown"
    return f"{float(parsed):.1%}"


def source_options(snapshot: dict) -> list[str]:
    frames = []
    if not snapshot["articles"].empty:
        frames.append(snapshot["articles"][["source"]].copy())
    if not snapshot["rejected_articles"].empty:
        frames.append(snapshot["rejected_articles"][["source"]].copy())
    if not frames:
        return []

    sources = pd.concat(frames, ignore_index=True)
    labels = (
        sources["source"]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", "Unknown")
        .drop_duplicates()
        .sort_values()
        .tolist()
    )
    return labels


def apply_source_filter(df: pd.DataFrame, selected_sources: list[str]) -> pd.DataFrame:
    if df.empty or not selected_sources:
        return df
    normalized = df["source"].fillna("").astype(str).str.strip().replace("", "Unknown")
    return df[normalized.isin(selected_sources)].copy()


def render_executive_summary(snapshot: dict) -> None:
    st.subheader("Executive Summary")
    if snapshot.get("market_error"):
        st.warning(f"Market data is currently unavailable: {snapshot['market_error']}")
    market_quality = snapshot.get("market_data_quality", {})
    if market_quality.get("status") in {"Partial", "Low"}:
        st.warning(f"Market data quality is {market_quality.get('status')}: {market_quality.get('note')}")

    news_stats = snapshot["news_stats"]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Stance", snapshot["stance"])
    col2.metric("Health Stack Flywheel", f"{snapshot['overall_score']:.1f}/100")
    col3.metric("LLY AI Trade", f"{snapshot['lly_ai_trade_score']:.1f}/100")
    col4.metric("Market Data", str(market_quality.get("status", "Unknown")))

    st.write(snapshot["interpretation"])
    if snapshot["positive_drivers"] or snapshot["negative_drivers"]:
        st.caption(
            f"Top positive drivers: {', '.join(snapshot['positive_drivers']) if snapshot['positive_drivers'] else 'None'} | "
            f"Top negative drivers: {', '.join(snapshot['negative_drivers']) if snapshot['negative_drivers'] else 'None'}"
        )
    st.caption(
        f"News confidence: {snapshot['news_confidence']} | accepted {news_stats['accepted']} | fetched {news_stats['total_fetched']} | "
        f"relevance rejects {news_stats['rejected_by_relevance_gate']} | exclusion rejects {news_stats['rejected_by_exclusion_filter']}"
    )

    best_layers = snapshot["best_layers"]
    st.caption(
        f"Best-performing layers: 1W {best_layers['1w']} | 1M {best_layers['1m']} | "
        f"3M {best_layers['3m']} | 6M {best_layers['6m']}"
    )

    outperformance = snapshot["lly_outperformance"]
    st.write(
        f"LLY outperformance checks: XLV {metric_text(outperformance['XLV'])}, "
        f"XBI {metric_text(outperformance['XBI'])}, NVO {metric_text(outperformance['NVO'])}, "
        f"QQQ {metric_text(outperformance['QQQ'])}, SPY {metric_text(outperformance['SPY'])}"
    )
    st.write(
        f"GLP-1 leadership: {'Yes' if snapshot['leadership_check'] else 'No'} | "
        f"AI-biotech confirmation: {'Yes' if snapshot['ai_confirmation_check'] else 'No'}"
    )

    news_cols = st.columns(2)
    with news_cols[0]:
        st.markdown("**Positive themes**")
        st.write(", ".join(snapshot["positive_themes"]) if snapshot["positive_themes"] else "No RSS data")
    with news_cols[1]:
        st.markdown("**Negative themes**")
        st.write(", ".join(snapshot["negative_themes"]) if snapshot["negative_themes"] else "No RSS data")

    st.plotly_chart(component_score_chart(snapshot["component_scores"]), width="stretch")
    render_confirmation_structure(snapshot)


def render_confirmation_structure(snapshot: dict) -> None:
    """Phase 1: light display of the confirmation structure (no-op on old snapshots)."""
    if not snapshot.get("confirmation_state"):
        return
    concentration = snapshot.get("leadership_concentration", {}) or {}
    event_counts = snapshot.get("news_event_counts", {}) or {}
    with st.expander("Health Stack Confirmation Structure", expanded=False):
        st.write(f"**Confirmation state:** {snapshot['confirmation_state']}")
        st.write(
            f"Leader assessment: {snapshot.get('leader_assessment', 'Unknown')} | "
            f"Stack assessment: {snapshot.get('stack_assessment', 'Unknown')}"
        )
        st.write(f"Leadership concentration: {concentration.get('verdict', 'insufficient data')}")
        confirming = concentration.get("confirming_sleeves", []) or []
        deteriorating = concentration.get("deteriorating_sleeves", []) or []
        st.write(
            f"Confirming sleeves: {len(confirming)} of 7 required"
            + (f" ({', '.join(confirming)})" if confirming else "")
        )
        st.write(
            f"Deteriorating sleeves: {len(deteriorating)} of 7 required"
            + (f" ({', '.join(deteriorating)})" if deteriorating else "")
        )
        st.write(
            f"Unique news events: {event_counts.get('unique_events', 0)} "
            f"({event_counts.get('material_events', 0)} material)"
        )
        st.caption(f"Main contradiction: {snapshot.get('main_contradiction', 'None identified')}")
    render_decision_layer(snapshot)
    render_positions(snapshot)
    render_journal_accountability(snapshot)
    render_opportunity_ranking(snapshot)
    render_persistence_readiness(snapshot)


def render_positions(snapshot: dict) -> None:
    """Phase 5: position-level decisions display."""
    import pandas as pd

    cards = snapshot.get("position_cards") or []
    if not cards:
        return
    with st.expander("Position-Level Decisions", expanded=False):
        st.caption(
            "Analytical only — no trade execution, no personalized sizing. "
            "A ticker call may be more defensive than its sleeve but cannot "
            "override broad-stack exposure."
        )
        rows = [
            {
                "Ticker": c["ticker"],
                "Sleeve": c.get("sleeve"),
                "Trend": c.get("price_trend"),
                "Status": c.get("status"),
                "Recommendation": c.get("recommendation"),
                "Tier": c.get("tier") if c.get("tier") is not None else "n/a",
                "Confidence": f"{c.get('confidence', 0):.0f}",
                "Urgency": c.get("urgency"),
            }
            for c in cards
        ]
        st.dataframe(pd.DataFrame(rows), width="stretch")
        divergences = snapshot.get("position_divergences") or []
        if divergences:
            st.write("**Notable defensive divergences**")
            for card in divergences:
                st.write(f"- {card['ticker']}: {card['status']} — {card.get('reason')}")


def render_journal_accountability(snapshot: dict) -> None:
    """Phase 5: decision journal and accountability display."""
    from .accountability import summarize_accountability
    from .backtest import summarize_track_a

    with st.expander("Decision Journal and Accountability", expanded=False):
        journal = snapshot.get("journal")
        n = 0 if journal is None or getattr(journal, "empty", True) else len(journal)
        st.write(f"Journal entries: {n} (methodology phase5-v1).")
        st.write("**Accountability**")
        for line in summarize_accountability(snapshot.get("accountability_metrics") or {}):
            st.write(line)
        st.write("**Backtests**")
        for line in summarize_track_a(snapshot.get("backtest_track_a") or {}):
            st.write(line)
        track_b = snapshot.get("backtest_track_b") or {}
        st.write(f"Track B: {track_b.get('status', 'n/a')}. {track_b.get('note', '')}")


def render_decision_layer(snapshot: dict) -> None:
    """Phase 4: Capital Allocation Decision Layer display."""
    cards = snapshot.get("decision_cards") or []
    if not cards:
        return
    with st.expander("Capital Allocation Decision Layer", expanded=True):
        st.write(snapshot.get("committee_decision", ""))
        leader = snapshot.get("leader_decision") or {}
        stack = snapshot.get("stack_decision") or {}
        st.write(f"**Leader:** {leader.get('headline', 'n/a')}")
        st.write(f"**Stack:** {stack.get('headline', 'n/a')}")
        agreement = snapshot.get("leader_stack_agree")
        if agreement is None:
            st.info("Leader vs Stack agreement is N/A until both decisions are rated.")
        elif agreement is False:
            st.warning("Leader and Stack decisions disagree — size the leader independently of broad-stack exposure.")
        rows = [
            {
                "Sleeve": c["sleeve"],
                "Recommendation": c.get("recommendation_display", c["recommendation"]),
                "Tier": (
                    f"{c['previous_tier']} → {c['recommended_tier']}"
                    if c["previous_tier"] is not None and c["recommended_tier"] is not None
                    else (str(c["recommended_tier"]) if c["recommended_tier"] is not None else "N/A")
                ),
                "History": (
                    f"{int(c.get('history_report_count') or 0)} of "
                    f"{int(c.get('required_history_reports') or 4)}"
                ),
                "Decision Confidence": (
                    "Low - insufficient history"
                    if not c.get("is_rated", c.get("recommended_tier") is not None)
                    else f"{c['confidence']:.0f} ({c['confidence_band']})"
                ),
                "Model Input Confidence": (
                    f"{c.get('model_input_confidence', 0):.0f} "
                    f"({c.get('model_input_confidence_band', 'Low')})"
                ),
                "Urgency": c["urgency"],
                "Speed": c["implementation_speed"],
            }
            for c in cards
        ]
        import pandas as pd

        st.dataframe(pd.DataFrame(rows), width="stretch")
        st.caption(
            "Tiers are conviction statements (0 Avoid, 1 Exploratory, 2 Normal, "
            "3 Overweight, 4 Maximum-conviction overweight), not portfolio "
            "percentages. Analytical only — no orders placed."
        )
        risks = snapshot.get("decision_risks") or []
        if risks:
            st.write("**Decision risks**")
            for risk in risks:
                st.write(f"- {risk}")


def render_persistence_readiness(snapshot: dict) -> None:
    """Phase 3: persistence and decision-readiness display."""
    table = snapshot.get("persistence_table")
    if table is None or getattr(table, "empty", True):
        return
    with st.expander("Persistence and Decision Readiness", expanded=False):
        display = table[
            [
                "sleeve",
                "current_score",
                "four_report_trend",
                "readiness",
                "second_derivative",
            ]
        ].copy()
        display.columns = [
            "Sleeve",
            "Score",
            "4-Report Trend",
            "Readiness",
            "2nd Derivative",
        ]
        st.dataframe(display, width="stretch")
        for _, row in table.iterrows():
            conflicts = str(row.get("conflicts") or "").strip()
            if conflicts:
                st.caption(f"Conflicting evidence ({row['sleeve']}): {conflicts}")
        changed = snapshot.get("what_changed_lines") or []
        if changed:
            st.write("**What changed since the previous report**")
            for line in changed:
                st.write(line)


def render_opportunity_ranking(snapshot: dict) -> None:
    """Phase 2: sleeve opportunity ranking display."""
    ranking = snapshot.get("opportunity_ranking")
    if ranking is None or getattr(ranking, "empty", True):
        return
    with st.expander("Health Stack Opportunity Ranking", expanded=False):
        display = ranking[
            [
                "rank",
                "sleeve",
                "opportunity_score",
                "structural_score",
                "market_confirmation_score",
                "catalyst_score",
                "expectations_risk_score",
                "trend",
            ]
        ].copy()
        display.columns = [
            "Rank",
            "Sleeve",
            "Opportunity",
            "Structural",
            "Market Conf.",
            "Catalyst",
            "Exp. Risk",
            "Trend",
        ]
        st.dataframe(display, width="stretch")
        gaps = ranking[ranking["recognition_gap"] == True]  # noqa: E712
        for _, row in gaps.iterrows():
            st.caption(f"Recognition gap: {row['sleeve']} — strong thesis/catalysts, weak market confirmation.")
        st.caption(
            "Analytical only — no allocation tiers. Structural score is a news-evidence proxy; "
            "expectations risk has reduced confidence (no valuation data)."
        )


def render_lly_tab(snapshot: dict) -> None:
    st.subheader("Eli Lilly AI Trade")
    if snapshot["price_history"].empty:
        st.info("No market data is available yet. This section will populate once Yahoo Finance is reachable.")
        return
    st.plotly_chart(lly_price_chart(snapshot["price_history"]), width="stretch")
    for comparator in ["NVO", "XLV", "XBI", "QQQ", "NVDA"]:
        st.plotly_chart(lly_relative_chart(snapshot["price_history"], comparator), width="stretch")

    st.dataframe(
        snapshot["component_scores"],
        width="stretch",
        hide_index=True,
    )
    components = snapshot.get("lly_ai_trade_components")
    if components is not None and not getattr(components, "empty", True):
        st.markdown("**LLY AI-trade score components**")
        st.dataframe(components, width="stretch", hide_index=True)


def render_basket_tab(snapshot: dict, groups: list[str], title: str) -> None:
    st.subheader(title)
    if snapshot["performance_table"].empty:
        st.info("No market data is available yet. Basket analytics will populate automatically when prices load.")
        return
    st.plotly_chart(performance_heatmap(snapshot["performance_table"], groups), width="stretch")
    subset = snapshot["performance_table"][snapshot["performance_table"]["group"].isin(groups)].copy()
    st.dataframe(subset.sort_values(["group", "return_3m"], ascending=[True, False]), width="stretch", hide_index=True)


def render_news_tab(snapshot: dict) -> None:
    st.subheader("Yahoo Finance RSS News Engine")
    if snapshot["fetch_errors"]:
        st.warning("RSS fetch issues were detected. Market data and scoring still loaded.")
        st.write(snapshot["fetch_errors"])

    st.caption(snapshot["news_confidence_note"])
    available_sources = source_options(snapshot)
    selected_sources = st.multiselect(
        "Filter by source",
        options=available_sources,
        default=available_sources,
        help="Use this to inspect which publishers are producing relevant stories versus noisy finance headlines.",
    )

    filtered_articles = apply_source_filter(snapshot["articles"], selected_sources)
    filtered_rejected = apply_source_filter(snapshot["rejected_articles"], selected_sources)

    if filtered_articles.empty:
        filtered_theme_summary = pd.DataFrame(columns=snapshot["theme_summary"].columns)
    else:
        filtered_theme_summary = (
            filtered_articles.groupby("theme")
            .agg(story_count=("title", "count"), avg_sentiment=("sentiment_score", "mean"))
            .sort_values(["story_count", "avg_sentiment"], ascending=[False, False])
            .reset_index()
        )

    source_summary_parts = []
    if not filtered_articles.empty:
        accepted_sources = (
            filtered_articles["source"].fillna("").astype(str).str.strip().replace("", "Unknown").value_counts().head(5)
        )
        source_summary_parts.append(
            "Accepted: " + ", ".join(f"{source} ({count})" for source, count in accepted_sources.items())
        )
    if not filtered_rejected.empty:
        rejected_sources = (
            filtered_rejected["source"].fillna("").astype(str).str.strip().replace("", "Unknown").value_counts().head(5)
        )
        source_summary_parts.append(
            "Rejected: " + ", ".join(f"{source} ({count})" for source, count in rejected_sources.items())
        )
    if source_summary_parts:
        st.caption(" | ".join(source_summary_parts))

    st.plotly_chart(theme_bar_chart(filtered_theme_summary), width="stretch")
    if filtered_articles.empty:
        st.info("No RSS stories were classified in this run.")
    else:
        st.dataframe(
            filtered_articles[
                [
                    column
                    for column in [
                        "published_at",
                        "title",
                        "source_quality",
                        "evidence_type",
                        "theme",
                        "sentiment_label",
                        "tickers",
                        "relevance_score",
                        "url",
                    ]
                    if column in filtered_articles.columns
                ]
            ],
            width="stretch",
            hide_index=True,
        )

    if not filtered_rejected.empty:
        st.markdown("**Rejected stories**")
        st.dataframe(
            filtered_rejected[
                ["published_at", "source", "title", "rejection_stage", "rejection_reason", "matched_exclusion_terms", "relevance_score"]
            ].head(20),
            width="stretch",
            hide_index=True,
        )


def render_theme_scores_tab(snapshot: dict) -> None:
    st.subheader("Theme Scores")
    if snapshot["theme_summary"].empty and snapshot["sentiment_summary"].empty:
        st.info("No theme scores are available yet because no RSS stories were classified in this run.")
        return
    left, right = st.columns(2)
    with left:
        st.dataframe(snapshot["theme_summary"], width="stretch", hide_index=True)
    with right:
        st.dataframe(snapshot["sentiment_summary"], width="stretch", hide_index=True)


def render_raw_data_tab(snapshot: dict) -> None:
    st.subheader("Raw Data / Diagnostics")
    st.write(f"As of: {snapshot['as_of_date']}")
    st.write("Written files")
    if snapshot["written_files"]:
        for path in snapshot["written_files"]:
            st.code(str(path))
    st.markdown("**Ticker performance**")
    st.dataframe(snapshot["performance_table"], width="stretch", hide_index=True)
    st.markdown("**Ticker exceptions**")
    ticker_exceptions = snapshot["ticker_diagnostics"].get("exceptions", [])
    if ticker_exceptions:
        st.dataframe(pd.DataFrame(ticker_exceptions), width="stretch", hide_index=True)
    else:
        st.write("No ticker exceptions applied.")
    st.markdown("**Classified articles**")
    st.dataframe(snapshot["articles"], width="stretch", hide_index=True)
    st.markdown("**Rejected articles**")
    st.dataframe(snapshot["rejected_articles"], width="stretch", hide_index=True)


def main() -> None:
    st.set_page_config(page_title="GLP-1 AI Health Stack Watch", layout="wide")
    st.title("GLP-1 AI Health Stack Watch")
    st.caption("Tracking GLP-1 leadership, Lilly's AI-trade thesis, and AI-enabled healthcare stack confirmation.")

    if "refresh_nonce" not in st.session_state:
        st.session_state["refresh_nonce"] = 0

    st.sidebar.header("Controls")
    lookback_days = st.sidebar.selectbox(
        "Lookback window",
        options=[252, 300, LOOKBACK_DAYS, 504],
        index=[252, 300, LOOKBACK_DAYS, 504].index(LOOKBACK_DAYS),
        format_func=lambda value: f"{value} days",
    )
    refresh_mode = st.sidebar.radio(
        "Market price source",
        options=["Use cached prices", "Force live market refresh"],
        help="This only chooses whether the next saved snapshot reuses cached prices or asks Yahoo Finance for fresh prices.",
    )
    if st.sidebar.button("Save full snapshot report"):
        load_snapshot.clear()
        st.session_state["refresh_nonce"] += 1

    snapshot = load_snapshot(
        lookback_days=lookback_days,
        force_market_refresh=(refresh_mode == "Force live market refresh"),
        refresh_nonce=st.session_state["refresh_nonce"],
    )
    st.sidebar.caption(
        f"Current snapshot uses a {snapshot['lookback_days']}-day market window. "
        f"Refresh count: {st.session_state['refresh_nonce']}."
    )
    saved_reports = report_paths(snapshot)
    if saved_reports:
        st.sidebar.success("Report saved")
        st.sidebar.code(saved_reports[-1])
    else:
        st.sidebar.caption(f"Report folder: {REPORTS_DIR}")
        latest_report = latest_saved_report()
        if latest_report is not None:
            st.sidebar.caption(f"Last saved report: {latest_report.name}")

    tabs = st.tabs(
        [
            "Executive Summary",
            "Eli Lilly AI Trade",
            "GLP-1 Basket",
            "AI Drug Discovery Basket",
            "Longevity / Gene Editing",
            "News Feed",
            "Theme Scores",
            "Raw Data / Diagnostics",
        ]
    )

    with tabs[0]:
        render_executive_summary(snapshot)
    with tabs[1]:
        render_lly_tab(snapshot)
    with tabs[2]:
        render_basket_tab(snapshot, ["Core GLP-1 Leaders", "GLP-1 Challengers"], "GLP-1 Basket")
    with tabs[3]:
        render_basket_tab(snapshot, ["AI Drug Discovery Platforms"], "AI Drug Discovery Basket")
    with tabs[4]:
        render_basket_tab(
            snapshot,
            ["Gene Editing / Cardiometabolic Adjacent"],
            "Longevity / Gene Editing",
        )
    with tabs[5]:
        render_news_tab(snapshot)
    with tabs[6]:
        render_theme_scores_tab(snapshot)
    with tabs[7]:
        render_raw_data_tab(snapshot)


if __name__ == "__main__":
    main()



