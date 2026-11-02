from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from .config import CLASSIFIED_DIR, HISTORY_DIR, REPORTS_DIR, VALIDATION_DIR


def ensure_output_dirs() -> None:
    for path in [REPORTS_DIR, CLASSIFIED_DIR, HISTORY_DIR, VALIDATION_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def spreadsheet_safe_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    """Neutralize strings that spreadsheet programs may execute as formulas."""
    safe = frame.copy()
    dangerous_prefixes = ("=", "+", "-", "@", "\t", "\r")

    def neutralize(value: object) -> object:
        if not isinstance(value, str):
            return value
        candidate = value.lstrip(" ")
        if candidate.startswith(dangerous_prefixes):
            return "'" + value
        return value

    for column in safe.select_dtypes(include=["object", "string"]).columns:
        safe[column] = safe[column].map(neutralize)
    return safe


def write_performance_csv(performance_table: pd.DataFrame, as_of_stamp: str) -> Path:
    ensure_output_dirs()
    path = CLASSIFIED_DIR / f"ticker_performance_{as_of_stamp}.csv"
    spreadsheet_safe_dataframe(performance_table).to_csv(path, index=False)
    return path


def write_articles_csv(articles_df: pd.DataFrame, as_of_stamp: str) -> Path:
    ensure_output_dirs()
    path = CLASSIFIED_DIR / f"classified_articles_{as_of_stamp}.csv"
    spreadsheet_safe_dataframe(articles_df).to_csv(path, index=False)
    return path


def build_confirmation_structure_section(snapshot: dict) -> list[str]:
    """Phase 1 section: sleeve confirmation, concentration, and event counts.

    Returns an empty list when the snapshot predates Phase 1 (keys missing),
    so legacy snapshots keep byte-identical report output.
    """
    state = snapshot.get("confirmation_state")
    if not state:
        return []
    concentration = snapshot.get("leadership_concentration", {}) or {}
    event_counts = snapshot.get("news_event_counts", {}) or {}
    summaries = snapshot.get("sleeve_summaries")
    confirming = concentration.get("confirming_sleeves", []) or []
    deteriorating = concentration.get("deteriorating_sleeves", []) or []
    lines = [
        "## Health Stack Confirmation Structure",
        "",
        f"- Confirmation state: {state} ({snapshot.get('confirmation_reason', '')})",
        f"- Leader assessment: {snapshot.get('leader_assessment', 'Unknown')}",
        f"- Stack assessment: {snapshot.get('stack_assessment', 'Unknown')}",
        f"- Leadership concentration: {concentration.get('verdict', 'insufficient data')}",
        f"- Confirming sleeves: {len(confirming)} of 7 required"
        + (f" ({', '.join(confirming)})" if confirming else ""),
        f"- Deteriorating sleeves: {len(deteriorating)} of 7 required"
        + (f" ({', '.join(deteriorating)})" if deteriorating else ""),
    ]
    def _format_share(value: object, precision: int = 0) -> str:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return "n/a"
        if pd.isna(number):
            return "n/a"
        return f"{number:.{precision}%}"

    if summaries is not None and not summaries.empty:
        required = summaries[summaries["required"]]
        supporting = summaries[~summaries["required"]]
        if not required.empty:
            strongest = required.sort_values("avg_return_3m", ascending=False).iloc[0]
            weakest = required.sort_values("avg_return_3m", ascending=True).iloc[0]
            lines.append(
                f"- Strongest required sleeve: {strongest['sleeve']} "
                f"({_format_share(strongest['avg_return_3m'], 1)} avg 3M, {strongest['status']})"
            )
            lines.append(
                f"- Weakest required sleeve: {weakest['sleeve']} "
                f"({_format_share(weakest['avg_return_3m'], 1)} avg 3M, {weakest['status']})"
            )
        for _, row in supporting.iterrows():
            supporting_line = (
                f"- Supporting sleeve {row['sleeve']}: {row['status']} "
                f"(excluded from core breadth counts)"
            )
            stack_assessment = snapshot.get("stack_assessment", "")
            if row["status"] == "deteriorating" and stack_assessment in {
                "Broadly confirming",
                "Selectively confirming",
            }:
                supporting_line += "; diverges from confirming stack"
            elif row["status"] == "confirming" and stack_assessment in {
                "Deteriorating",
                "Failing",
            }:
                supporting_line += "; diverges from deteriorating stack"
            lines.append(supporting_line)
    top_ticker = snapshot.get("news_top_ticker") or "n/a"
    lines.append(
        f"- Catalyst breadth: {snapshot.get('qualified_theme_count', 0)} qualified themes"
    )
    lines.append(
        f"- News concentration: top ticker {top_ticker} "
        f"({_format_share(snapshot.get('news_top_ticker_share'))} of accepted stories)"
    )
    breadth_line = (
        f"- Core health-stack breadth: {_format_share(concentration.get('pct_above_50dma'))} "
        f"above 50DMA, {_format_share(concentration.get('pct_outperform_xlv'))} "
        f"outperforming XLV (required sleeves only)"
    )
    if concentration.get("verdict") == "insufficient data":
        breadth_line += " — insufficient data"
    lines.append(breadth_line)
    lines.extend(
        [
            f"- Unique news events: {event_counts.get('unique_events', 0)} "
            f"({event_counts.get('material_events', 0)} material, "
            f"{event_counts.get('multi_source_events', 0)} multi-source)",
            f"- Main positive evidence: {snapshot.get('main_positive_evidence', 'None identified')}",
            f"- Main negative evidence: {snapshot.get('main_negative_evidence', 'None identified')}",
            f"- Main contradiction: {snapshot.get('main_contradiction', 'None identified')}",
            "",
        ]
    )
    return lines


def _format_score(value: object) -> str:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return "n/a"
    return f"{float(parsed):.1f}"


def build_opportunity_ranking_section(snapshot: dict) -> list[str]:
    """Phase 2: Health Stack Opportunity Ranking report section."""
    ranking = snapshot.get("opportunity_ranking")
    lines = ["## Health Stack Opportunity Ranking", ""]
    if ranking is None or getattr(ranking, "empty", True):
        lines.extend(
            [
                "Opportunity scoring unavailable for this run.",
                "",
            ]
        )
        return lines

    lines.extend(
        [
            "| Rank | Sleeve | Opportunity Score | Structural Score | "
            "Market Confirmation | Catalyst Score | Expectations Risk | Trend |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for _, row in ranking.iterrows():
        rank = row.get("rank")
        rank_text = str(int(rank)) if pd.notna(rank) else "n/a"
        support = "" if row.get("required") else " (supporting)"
        lines.append(
            f"| {rank_text} | {row.get('sleeve')}{support} | "
            f"{_format_score(row.get('opportunity_score'))} | "
            f"{_format_score(row.get('structural_score'))} | "
            f"{_format_score(row.get('market_confirmation_score'))} | "
            f"{_format_score(row.get('catalyst_score'))} | "
            f"{_format_score(row.get('expectations_risk_score'))} | "
            f"{row.get('trend', 'Unknown')} |"
        )
    lines.append("")

    # Decision-neutral interpretation: where evidence is strongest/weakest.
    scored = ranking[ranking["required"] & ranking["opportunity_score"].notna()]
    if not scored.empty:
        strongest = scored.iloc[0]
        weakest = scored.iloc[-1]
        lines.append(
            f"- Strongest evidence: {strongest['sleeve']} "
            f"(opportunity {_format_score(strongest['opportunity_score'])}: "
            f"{strongest['interpretation']}, trend {strongest['trend']})."
        )
        if len(scored) > 1:
            lines.append(
                f"- Weakest evidence: {weakest['sleeve']} "
                f"(opportunity {_format_score(weakest['opportunity_score'])}: "
                f"{weakest['interpretation']}, trend {weakest['trend']})."
            )
    gaps = ranking[ranking["recognition_gap"] == True]  # noqa: E712
    for _, row in gaps.iterrows():
        lines.append(
            f"- Recognition gap: {row['sleeve']} shows strong structural and "
            "catalyst evidence the market has not yet confirmed."
        )
    lines.extend(
        [
            "- This section is analytical only; it issues no allocation tiers or "
            "portfolio actions.",
            "- Data limitations: the Structural Thesis Score is a news-evidence "
            "proxy (no fundamentals feed); Expectations Risk carries reduced "
            "confidence (no valuation or earnings-revision data). The ranking's "
            "trend label is a current 1M-vs-3M pace signal; the separate "
            "Persistence section supplies multi-report decision readiness.",
            "",
        ]
    )
    return lines


def build_persistence_section(snapshot: dict) -> list[str]:
    """Phase 3: Persistence and Decision Readiness report section."""
    table = snapshot.get("persistence_table")
    lines = ["## Persistence and Decision Readiness", ""]
    if table is None or getattr(table, "empty", True):
        lines.extend(["Persistence data unavailable for this run.", ""])
        return lines
    lines.extend(
        [
            "| Sleeve | Current Score | Four-Report Trend | Persistence | Readiness | Second Derivative |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for _, row in table.iterrows():
        support = "" if row.get("required") else " (supporting)"
        persistence = []
        if pd.notna(row.get("consecutive_improving")) and int(row["consecutive_improving"]) > 0:
            persistence.append(f"{int(row['consecutive_improving'])} improving")
        if pd.notna(row.get("consecutive_deteriorating")) and int(row["consecutive_deteriorating"]) > 0:
            persistence.append(f"{int(row['consecutive_deteriorating'])} deteriorating")
        if pd.notna(row.get("consecutive_above_strong")) and int(row["consecutive_above_strong"]) > 0:
            persistence.append(f"{int(row['consecutive_above_strong'])} above strong")
        if pd.notna(row.get("consecutive_below_weak")) and int(row["consecutive_below_weak"]) > 0:
            persistence.append(f"{int(row['consecutive_below_weak'])} below weak")
        persistence_text = ", ".join(persistence) if persistence else "—"
        lines.append(
            f"| {row.get('sleeve')}{support} | "
            f"{_format_score(row.get('current_score'))} | "
            f"{row.get('four_report_trend', 'insufficient')} | "
            f"{persistence_text} | "
            f"{row.get('readiness', 'Insufficient Evidence')} | "
            f"{row.get('second_derivative', 'insufficient')} |"
        )
    lines.append("")
    for _, row in table.iterrows():
        conflicts = str(row.get("conflicts") or "").strip()
        if conflicts:
            lines.append(f"- Conflicting evidence ({row.get('sleeve')}): {conflicts}.")
    notes = {
        str(row.get("readiness_note") or "").strip()
        for _, row in table.iterrows()
        if str(row.get("readiness_note") or "").strip()
    }
    for note in sorted(notes):
        lines.append(f"- {note}")
    lines.extend(
        [
            "- Readiness classifies evidence maturity, not portfolio actions.",
            "- History starts cold: early runs read Insufficient Evidence until streaks form.",
            "",
        ]
    )
    return lines


def _strip_section_header(lines: list[str]) -> list[str]:
    """Drop a section builder's own H2 header (and following blank line)."""
    out = list(lines)
    if out and out[0].startswith("## "):
        out = out[1:]
    if out and out[0] == "":
        out = out[1:]
    return out


def _format_tier_change(card: dict) -> str:
    prev = card.get("previous_tier")
    new = card.get("recommended_tier")
    change = card.get("tier_change")
    if new is None:
        return "N/A"
    if prev is None:
        return f"new → Tier {new}"
    arrow = "→"
    sign = f"{change:+d}" if change is not None else "?"
    return f"Tier {prev} {arrow} Tier {new} ({sign})"


def build_decision_layer_sections(snapshot: dict) -> list[str]:
    """Phase 4: the Decision Layer report sections (1-7)."""
    cards = snapshot.get("decision_cards") or []
    leader = snapshot.get("leader_decision") or {}
    stack = snapshot.get("stack_decision") or {}
    market_quality = snapshot.get("market_data_quality", {}) or {}
    all_unrated = bool(cards) and all(
        not c.get("is_rated", c.get("recommended_tier") is not None)
        for c in cards
        if c.get("required")
    )
    decision_confidence = "Low" if all_unrated else (
        max(cards, key=lambda c: c.get("confidence", 0)).get("confidence_band", "Low")
        if cards
        else "Low"
    )
    agreement = snapshot.get("leader_stack_agree")
    if agreement is None:
        agreement_text = "N/A - leader or stack is not yet rated."
    elif agreement:
        agreement_text = "Yes"
    else:
        agreement_text = "No - size the leader independently of broad-stack exposure."
    lines = [
        "## 1. Investment Committee Decision",
        "",
        snapshot.get("committee_decision", "No committee decision available."),
        "",
        f"- Data quality: {market_quality.get('status', 'Unknown')}",
        f"- News confidence: {snapshot.get('news_confidence', 'Unknown')}",
        f"- Decision confidence: {decision_confidence}",
        "- Reason: insufficient persistence history"
        if all_unrated
        else "- Reason: persistence history supports rated sleeve decisions",
        "",
    ]
    pointer = str(snapshot.get("committee_pointer") or "").strip()
    if pointer:
        lines.append(pointer)
        lines.append("")
    lines.extend(
        [
            "## 2. Allocation Decisions",
            "",
            "| Sleeve | Prev -> Rec Tier | Recommendation | Decision Confidence | Urgency | Speed |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for card in cards:
        recommendation = card.get("recommendation_display", card["recommendation"])
        confidence = (
            "Low - insufficient history"
            if not card.get("is_rated", card.get("recommended_tier") is not None)
            else f"{card['confidence']:.0f} {card['confidence_band']}"
        )
        lines.append(
            f"| {card['sleeve']} | {_format_tier_change(card)} "
            f"| {recommendation} | {confidence} | {card['urgency']} "
            f"| {card['implementation_speed']} |"
        )
    lines.extend(
        [
            "",
            "Tiers are conviction statements (0 Avoid, 1 Exploratory, 2 Normal, "
            "3 Overweight, 4 Maximum-conviction overweight), not portfolio "
            "percentages. Decision confidence reflects evidence maturity; model-input "
            "confidence and data quality are reported separately.",
            "",
            "## 3. Opportunity Ranking",
            "",
            *_strip_section_header(build_opportunity_ranking_section(snapshot)),
            "## 4. Leader vs Stack Decision",
            "",
            f"- Leader: {leader.get('headline', 'n/a')}",
            f"- Stack: {stack.get('headline', 'n/a')}",
            f"- Agreement: {agreement_text}",
            "",
            "## 5. What Matters Now",
            "",
        ]
    )
    required_cards = [c for c in cards if c.get("required") and c.get("opportunity_score") is not None]
    if required_cards:
        strongest = max(required_cards, key=lambda c: c["opportunity_score"])
        weakest = min(required_cards, key=lambda c: c["opportunity_score"])
        lines.extend(
            [
                f"- Strongest provisional evidence: {strongest['sleeve']} "
                f"({strongest['opportunity_score']:.1f}).",
                f"- Weakest provisional evidence: {weakest['sleeve']} "
                f"({weakest['opportunity_score']:.1f}).",
            ]
        )
    if cards:
        maturity = min(int(c.get("history_report_count") or 0) for c in cards)
        required_count = max(int(c.get("required_history_reports") or 4) for c in cards)
        lines.append(f"- History maturity: {maturity} of {required_count} required reports.")
    lines.extend(
        [
            "- Full sleeve conditions and evidence details are in Appendix A.",
            "",
        ]
    )
    lines.extend(
        [
            "## 6. What Changed Since the Previous Report",
            "",
            *_strip_section_header(build_what_changed_section(snapshot)),
            "## 7. Decision Risks",
            "",
        ]
    )
    risks = snapshot.get("decision_risks") or []
    if risks:
        for risk in risks:
            lines.append(f"- {risk}")
    else:
        lines.append("- No elevated decision risks flagged this report.")
    lines.append("")
    return lines


def build_decision_cards_appendix(snapshot: dict) -> list[str]:
    """Detailed sleeve cards live outside the main committee narrative."""
    cards = snapshot.get("decision_cards") or []
    lines = ["## Appendix A. Decision Cards", ""]
    for card in cards:
        rated = card.get("is_rated", card.get("recommended_tier") is not None)
        if card.get("views_agree") is None:
            views_text = "N/A - insufficient persistence history."
        elif card["views_agree"]:
            views_text = "Yes"
        else:
            views_text = "No - tactical and strategic evidence point different ways."
        recommendation = card.get("recommendation_display", card["recommendation"])
        decision_confidence = (
            "Low - insufficient history"
            if not rated
            else f"{card['confidence']:.0f} ({card['confidence_band']})"
        )
        lines.extend(
            [
                f"### {card['sleeve']}",
                "",
                f"- Recommendation: {recommendation} ({_format_tier_change(card)})",
                f"- History maturity: {int(card.get('history_report_count') or 0)} of "
                f"{int(card.get('required_history_reports') or 4)} required reports",
                f"- Decision confidence: {decision_confidence}",
                f"- Model-input confidence: {card.get('model_input_confidence', 0):.0f} "
                f"({card.get('model_input_confidence_band', 'Low')})",
                f"- Implementation speed: {card['implementation_speed']}",
                f"- Urgency: {card['urgency']}",
                f"- Tactical view: {card['tactical_view']}",
                f"- Strategic view: {card['strategic_view']}",
                f"- Views agree: {views_text}",
                f"- Upgrade: {card['upgrade_condition']}",
                f"- Downgrade: {card['downgrade_condition']}",
                f"- Invalidation: {card['invalidation_condition']}",
                f"- Rationale: {card['rationale']}.",
                "",
            ]
        )
    return lines


def _fmt_pct(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "n/a"
    try:
        return f"{float(value):+.1%}"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_yes_no(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "n/a"
    return "Yes" if bool(value) else "No"


def build_positions_section(snapshot: dict) -> list[str]:
    """Phase 5 §9: position-level decisions."""
    cards = snapshot.get("position_cards") or []
    lines = ["## 9. Position-Level Decisions", ""]
    if not cards:
        lines.extend(["Position data unavailable for this run.", ""])
        return lines
    lines.extend(
        [
            "Analytical only — no trade execution, no personalized sizing. "
            "A ticker call may be more defensive than its sleeve but cannot "
            "override the broad-stack exposure decision.",
            "",
            "| Ticker | Sleeve | Trend | RS SPY | RS XLV | RS Sleeve | 50DMA | 200DMA | Drawdown | Status | Recommendation | Tier | Conf | Urgency |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for card in cards:
        tier = card.get("tier")
        tier_txt = str(tier) if tier is not None else "n/a"
        lines.append(
            f"| {card['ticker']} | {card.get('sleeve') or 'n/a'} "
            f"| {card.get('price_trend') or 'n/a'} "
            f"| {_fmt_pct(card.get('rs_vs_spy'))} | {_fmt_pct(card.get('rs_vs_xlv'))} "
            f"| {_fmt_pct(card.get('rs_vs_sleeve'))} "
            f"| {_fmt_yes_no(card.get('above_50dma'))} | {_fmt_yes_no(card.get('above_200dma'))} "
            f"| {_fmt_pct(card.get('drawdown_from_high'))} "
            f"| {card.get('status')} | {card.get('recommendation')} | {tier_txt} "
            f"| {card.get('confidence', 0):.0f} | {card.get('urgency')} |"
        )
    lines.append("")
    # Notable calls: defensive divergences and not-rated names.
    divergences = snapshot.get("position_divergences") or []
    if divergences:
        lines.append("**Notable defensive divergences** (ticker more defensive than sleeve):")
        for card in divergences:
            lines.append(f"- {card['ticker']} ({card.get('sleeve')}): {card['status']} — {card.get('reason')}.")
        lines.append("")
    not_rated = [c for c in cards if c.get("status") == "Insufficient Evidence / Not Rated"]
    if not_rated:
        lines.append(
            f"**Not rated** ({len(not_rated)}): "
            + ", ".join(c["ticker"] for c in not_rated[:10])
            + ("…" if len(not_rated) > 10 else "")
            + " — insufficient technical or thesis data; no recommendation forced."
        )
        lines.append("")
    return lines


def build_journal_section(snapshot: dict) -> list[str]:
    """Phase 5 §10: decision journal and accountability."""
    from .accountability import summarize_accountability
    from .backtest import summarize_track_a

    lines = ["## 10. Decision Journal and Accountability", ""]
    journal = snapshot.get("journal")
    n_entries = 0 if journal is None or getattr(journal, "empty", True) else len(journal)
    lines.append(
        f"- Journal entries: {n_entries} (sleeve and ticker decisions, "
        f"methodology phase5-v1). Decision-time fields are immutable; only "
        f"outcome fields fill as maturities arrive."
    )
    if n_entries:
        filled_3m = 0
        try:
            filled_3m = int(journal["outcome_3m"].notna().sum())
        except Exception:
            pass
        lines.append(f"- 3M outcomes recorded: {filled_3m}; remainder fill automatically on later runs (never before maturity, never interpolated).")
    lines.append("")
    lines.append("**Accountability**")
    lines.append("")
    metrics = snapshot.get("accountability_metrics") or {}
    lines.extend(summarize_accountability(metrics) if metrics else ["- Accountability unavailable for this run."])
    lines.append("")
    lines.append("**Backtests**")
    lines.append("")
    lines.extend(summarize_track_a(snapshot.get("backtest_track_a") or {}))
    track_b = snapshot.get("backtest_track_b") or {}
    lines.append(
        f"- Track B (decision-rule strategies): {track_b.get('status', 'n/a')}. "
        f"{track_b.get('note', '')}"
    )
    lines.append("")
    return lines


def build_what_changed_section(snapshot: dict) -> list[str]:
    """Phase 3: What Changed Since the Previous Report section."""
    lines = ["## What Changed Since the Previous Report", ""]
    changed = snapshot.get("what_changed_lines") or []
    lines.extend(changed if changed else ["- No changes recorded."])
    lines.append("")
    return lines


def write_report(snapshot: dict, as_of_stamp: str) -> Path:
    ensure_output_dirs()
    path = REPORTS_DIR / f"glp1_ai_health_stack_watch_{as_of_stamp}.md"
    confirmation_section = build_confirmation_structure_section(snapshot)
    persistence_section = build_persistence_section(snapshot)
    top_stories = select_key_stories(snapshot["articles"], limit=10)
    news_stats = snapshot["news_stats"]
    market_quality = snapshot.get("market_data_quality", {})
    prior_delta_lines = build_prior_snapshot_delta_lines(snapshot, HISTORY_DIR / "dashboard_scores.jsonl")

    decision_sections = build_decision_layer_sections(snapshot)

    existing_lines = [
        "## Executive Summary",
        "",
        f"- Current stance: {snapshot['stance']}",
        f"- Health Stack Flywheel Score: {snapshot['overall_score']:.1f}",
        f"- News confidence: {snapshot['news_confidence']}",
        f"- Market data quality: {market_quality.get('status', 'Unknown')}",
        f"- Market data note: {market_quality.get('note', 'No market data quality audit available.')}",
        f"- One-line interpretation: {snapshot['interpretation']}",
        f"- Positive score drivers: {', '.join(snapshot['positive_drivers']) if snapshot['positive_drivers'] else 'None'}",
        f"- Negative score drivers: {', '.join(snapshot['negative_drivers']) if snapshot['negative_drivers'] else 'None'}",
        "",
        *confirmation_section,
        *persistence_section,
        "## Eli Lilly AI Trade",
        "",
        f"- LLY relative strength: {snapshot['lly_summary']}",
        f"- LLY trend status: {snapshot['lly_trend_status']}",
        f"- LLY news summary: {snapshot['lly_news_summary']}",
        f"- AI-trade confirmation score: {snapshot['lly_ai_trade_score']:.1f}",
        "- Score component breakdown:",
        *format_lly_component_breakdown(snapshot.get("lly_ai_trade_components")),
        "",
        "## GLP-1 Market",
        "",
        f"- Strongest names: {snapshot['glp1_winners']}",
        f"- Weakest names: {snapshot['glp1_losers']}",
        f"- News themes: {snapshot['glp1_themes']}",
        "",
        "## AI Drug Discovery / Longevity",
        "",
        f"- Strongest names: {snapshot['ai_winners']}",
        f"- Weakest names: {snapshot['ai_losers']}",
        f"- News themes: {snapshot['ai_themes']}",
        "",
        "## News Engine Audit",
        "",
        f"- Total stories fetched: {news_stats['total_fetched']}",
        f"- Stories rejected by relevance gate: {news_stats['rejected_by_relevance_gate']}",
        f"- Stories rejected by exclusion filter: {news_stats['rejected_by_exclusion_filter']}",
        f"- Accepted relevant stories: {news_stats['accepted']}",
        f"- Qualified scoring stories: {news_stats['qualified']}",
        f"- Scoring coverage: {news_stats['qualified']} of {news_stats['accepted']} accepted stories qualified for scoring",
        f"- Accepted stories by ticker: {snapshot['accepted_ticker_summary']}",
        f"- News confidence note: {snapshot['news_confidence_note']}",
        "",
        "## Key Stories",
        "",
        "- Selection method: fundamental catalysts and higher-quality sources rank first; "
        "market narrative ranks lower; routine corporate notices are excluded.",
        f"- Accepted evidence mix: {summarize_story_field(snapshot['articles'], 'evidence_type')}",
        f"- Accepted source-quality mix: {summarize_story_field(snapshot['articles'], 'source_quality')}",
        "",
    ]

    if top_stories.empty:
        existing_lines.append("- No accepted relevant stories passed the relevance gate for this run.")

    for _, row in top_stories.iterrows():
        existing_lines.extend(
            [
                f"- {clean_report_text(row['title'])}",
                f"  - Source: {clean_report_text(row['source']) if row['source'] else 'Unknown'}",
                f"  - Date: {format_timestamp(row['published_at'])}",
                f"  - Theme: {row['theme']}",
                f"  - Source quality: {row.get('source_quality', story_source_quality(row))}",
                f"  - Evidence type: {row.get('evidence_type', story_evidence_type(row))}",
                f"  - Sentiment: {row['sentiment_label']} ({row['sentiment_score']:.2f})",
                f"  - Tickers: {row['tickers'] or 'None detected'}",
                f"  - URL: {row['url']}",
            ]
        )

    existing_lines.extend(
        [
            "",
            "## Risks",
            "",
            "- GLP-1 pricing pressure",
            "- Safety / side-effect news",
            "- Reimbursement or policy risk",
            "- Competition from Novo Nordisk or challengers",
            "- Biotech market weakness",
            "- LLY valuation compression",
            "- AI-biotech hype without revenue confirmation",
            "",
            "## Investor Interpretation",
            "",
            snapshot["investor_interpretation"],
            "",
        ]
    )

    if prior_delta_lines:
        insert_at = next(
            (i for i, line in enumerate(existing_lines) if line == "## Eli Lilly AI Trade"),
            len(existing_lines),
        )
        existing_lines[insert_at:insert_at] = [
            "## Flywheel Score: Change Since Prior Run",
            "",
            *prior_delta_lines,
            "",
        ]

    # Existing sections sit under "## 8. Existing Report Sections": demote
    # their H2 headers one level so the Decision Layer numbering holds.
    demoted = [
        ("#" + line) if line.startswith("## ") else line for line in existing_lines
    ]
    lines = [
        "# GLP-1 AI Health Decision Layer",
        "",
        *build_report_metadata(snapshot),
        *decision_sections,
        "## 8. Existing Report Sections",
        "",
        *demoted,
        *build_positions_section(snapshot),
        *build_journal_section(snapshot),
        *build_decision_cards_appendix(snapshot),
    ]

    # Normalize punctuation at the final boundary as well as individual
    # headlines. This keeps reports readable in Windows tools that still
    # mis-detect UTF-8 punctuation despite the file's UTF-8 encoding.
    path.write_text(clean_report_text("\n".join(lines)), encoding="utf-8")
    return path


def build_report_metadata(snapshot: dict) -> list[str]:
    price_history = snapshot.get("price_history")
    market_cutoff = "Unavailable"
    if price_history is not None and not getattr(price_history, "empty", True):
        parsed = pd.to_datetime(price_history.index, utc=True, errors="coerce")
        valid = parsed[~pd.isna(parsed)]
        if len(valid):
            market_cutoff = pd.Timestamp(valid.max()).strftime("%Y-%m-%d")

    articles = snapshot.get("articles")
    news_cutoff = "Unavailable"
    if articles is not None and not getattr(articles, "empty", True) and "published_at" in articles.columns:
        parsed_news = pd.to_datetime(articles["published_at"], utc=True, errors="coerce").dropna()
        if not parsed_news.empty:
            news_cutoff = parsed_news.max().strftime("%Y-%m-%d %H:%M UTC")

    return [
        f"- Report generated: {snapshot.get('as_of_date', 'Unknown')}",
        f"- Market data through: {market_cutoff}",
        f"- News cutoff: {news_cutoff}",
        "",
    ]


def format_lly_component_breakdown(components: object) -> list[str]:
    if components is None or getattr(components, "empty", True):
        return ["  - Unavailable"]
    lines = []
    for _, row in components.iterrows():
        note = str(row.get("note") or "").strip()
        suffix = f" - {note}" if note else ""
        lines.append(
            f"  - {row['component']}: {float(row['score']):.1f}/100, "
            f"{float(row['contribution']):.1f} of {float(row['max_points']):.1f} points{suffix}"
        )
    return lines


def summarize_story_field(articles: pd.DataFrame, column: str) -> str:
    if articles is None or articles.empty or column not in articles.columns:
        return "Unavailable"
    counts = articles[column].fillna("Unknown").astype(str).value_counts()
    return ", ".join(f"{label} ({count})" for label, count in counts.items())


def select_key_stories(articles_df: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    if articles_df.empty:
        return articles_df.head(0)

    ranked = articles_df.copy()
    ranked["source_quality"] = ranked.apply(story_source_quality, axis=1)
    ranked["evidence_type"] = ranked.apply(story_evidence_type, axis=1)
    ranked = ranked[ranked["evidence_type"] != "Routine corporate notice"].copy()
    if ranked.empty:
        return ranked.head(0)

    quality_rank = {"Primary": 4, "High": 3, "Medium": 2, "Low": 1}
    evidence_rank = {"Fundamental catalyst": 3, "Company development": 2, "Market narrative": 1}
    ranked["_quality_rank"] = ranked["source_quality"].map(quality_rank).fillna(1)
    ranked["_evidence_rank"] = ranked["evidence_type"].map(evidence_rank).fillna(1)
    relevance = (
        ranked["relevance_score"]
        if "relevance_score" in ranked.columns
        else pd.Series(0.0, index=ranked.index)
    )
    published = (
        ranked["published_at"]
        if "published_at" in ranked.columns
        else pd.Series(pd.NaT, index=ranked.index)
    )
    ranked["_relevance_rank"] = pd.to_numeric(relevance, errors="coerce").fillna(0.0)
    ranked["_published_rank"] = pd.to_datetime(published, utc=True, errors="coerce")
    ranked = ranked.sort_values(
        ["_evidence_rank", "_quality_rank", "_relevance_rank", "_published_rank"],
        ascending=[False, False, False, False],
        na_position="last",
    )

    selected_indices: list[object] = []
    theme_counts: dict[str, int] = {}
    cluster_counts: dict[str, int] = {}

    for idx, row in ranked.iterrows():
        theme = str(row.get("theme", "Other"))
        cluster = story_cluster_key(row)
        if theme_counts.get(theme, 0) >= 3:
            continue
        if cluster_counts.get(cluster, 0) >= 2:
            continue
        selected_indices.append(idx)
        theme_counts[theme] = theme_counts.get(theme, 0) + 1
        cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1
        if len(selected_indices) >= limit:
            break

    if len(selected_indices) < limit:
        for idx, row in ranked.iterrows():
            if idx in selected_indices:
                continue
            cluster = story_cluster_key(row)
            if cluster_counts.get(cluster, 0) >= 2:
                continue
            selected_indices.append(idx)
            cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1
            if len(selected_indices) >= limit:
                break

    return ranked.loc[selected_indices].head(limit).drop(
        columns=["_quality_rank", "_evidence_rank", "_relevance_rank", "_published_rank"],
        errors="ignore",
    )


def _safe_story_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def story_source_quality(row: pd.Series) -> str:
    """Coarse source tier for report ordering, not a truthfulness verdict."""
    source = _safe_story_text(row.get("source")).lower()
    host = urlparse(_safe_story_text(row.get("url"))).netloc.lower()
    title = clean_report_text(row.get("title", "")).lower()
    if any(domain in host for domain in ("fda.gov", "sec.gov", "clinicaltrials.gov")):
        return "Primary"
    if any(token in source for token in ("reuters", "associated press", "bloomberg")):
        return "High"
    if any(token in source for token in ("stocktwits", "motley fool", "thestreet")):
        return "Low"
    if any(token in title for token in ("jim cramer", "price target", "analyst says")):
        return "Low"
    return "Medium"


def story_evidence_type(row: pd.Series) -> str:
    """Separate fundamental catalysts from narrative and routine notices."""
    title = clean_report_text(row.get("title", "")).lower()
    theme = _safe_story_text(row.get("theme")) or "Other"
    routine_terms = (
        "inducement grant",
        "listing rule 5635",
        "form 4",
        "stock award",
        "director compensation",
    )
    if any(term in title for term in routine_terms):
        return "Routine corporate notice"
    narrative_terms = (
        "jim cramer",
        "did claude",
        "shares slip",
        "stocks rise",
        "is it too late to buy",
        "price target",
        "forecast",
    )
    if any(term in title for term in narrative_terms):
        return "Market narrative"
    catalyst_terms = (
        "fda",
        "phase 1",
        "phase 2",
        "phase 3",
        "trial",
        "approval",
        "priority review",
        "acquisition",
        "partnership",
        "data readout",
        "regulatory",
    )
    if any(term in title for term in catalyst_terms) or theme in {
        "Regulatory Risk",
        "Manufacturing / Supply",
        "Lilly M&A / IP Acquisition",
    }:
        return "Fundamental catalyst"
    return "Company development"


def story_cluster_key(row: pd.Series) -> str:
    title = clean_report_text(row.get("title", "")).lower()
    tickers = str(row.get("tickers", ""))
    theme = str(row.get("theme", "Other"))
    legal_terms = ["sues", "suing", "lawsuit", "injunction", "court", "legal"]
    ad_terms = ["ad", "advertising", "weight-loss", "weight loss"]
    if "LLY" in tickers and "NVO" in tickers and any(term in title for term in legal_terms) and any(
        term in title for term in ad_terms
    ):
        return "lly_nvo_legal_ads"
    tokens = [token for token in re.findall(r"[a-z0-9]+", title) if len(token) >= 5]
    return f"{theme}|{'-'.join(tokens[:6])}"


def build_prior_snapshot_delta_lines(snapshot: dict, history_path: Path) -> list[str]:
    prior = latest_score_history_entry(history_path)
    if prior is None:
        return ["- Prior snapshot: None available"]

    news_stats = snapshot.get("news_stats", {})
    comparable = {
        "overall_score": snapshot.get("overall_score"),
        "stance": snapshot.get("stance"),
        "lly_ai_trade_score": snapshot.get("lly_ai_trade_score"),
        "accepted_story_count": news_stats.get("accepted"),
        "qualified_story_count": news_stats.get("qualified"),
    }
    unchanged = all(prior.get(key) == value for key, value in comparable.items())
    prior_time = pd.to_datetime(prior.get("as_of_date"), utc=True, errors="coerce")
    current_time = pd.to_datetime(snapshot.get("as_of_date"), utc=True, errors="coerce")
    if unchanged and pd.notna(prior_time) and pd.notna(current_time):
        elapsed = abs((current_time - prior_time).total_seconds())
        if elapsed <= 15 * 60:
            # Suppress operational reruns that add no analytical information.
            return []

    return [
        f"- Prior snapshot: {prior.get('as_of_date', 'Unknown')} | {prior.get('stance', 'Unknown')} | score {format_number(prior.get('overall_score'))}",
        f"- Score change: {format_delta(snapshot.get('overall_score'), prior.get('overall_score'))}",
        f"- Stance change: {prior.get('stance', 'Unknown')} -> {snapshot.get('stance', 'Unknown')}",
        f"- LLY AI trade score change: {format_delta(snapshot.get('lly_ai_trade_score'), prior.get('lly_ai_trade_score'))}",
        f"- Accepted stories change: {format_delta(news_stats.get('accepted'), prior.get('accepted_story_count'), decimals=0)}",
        f"- Qualified scoring stories change: {format_delta(news_stats.get('qualified'), prior.get('qualified_story_count'), decimals=0)}",
    ]


def write_validation_file(snapshot: dict, as_of_stamp: str) -> Path:
    ensure_output_dirs()
    path = VALIDATION_DIR / f"validation_{as_of_stamp}.md"
    news_stats = snapshot["news_stats"]
    market_quality = snapshot.get("market_data_quality", {})
    lines = [
        "# Validation Audit",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- Ticker rows: {len(snapshot['performance_table'])}",
        f"- Total stories fetched: {news_stats['total_fetched']}",
        f"- Stories rejected by relevance gate: {news_stats['rejected_by_relevance_gate']}",
        f"- Stories rejected by exclusion filter: {news_stats['rejected_by_exclusion_filter']}",
        f"- Accepted stories: {news_stats['accepted']}",
        f"- Qualified scoring stories: {news_stats['qualified']}",
        f"- Scoring coverage: {news_stats['qualified']} of {news_stats['accepted']} accepted stories qualified for scoring",
        f"- RSS errors: {len(snapshot['fetch_errors'])}",
        f"- Market data error: {snapshot.get('market_error') or 'None'}",
        f"- Market data quality: {market_quality.get('status', 'Unknown')}",
        f"- Market data coverage: prices {market_quality.get('price_count', 0)} of {market_quality.get('ticker_rows', 0)}, 3M returns {market_quality.get('return_3m_count', 0)} of {market_quality.get('ticker_rows', 0)}, RS cells {market_quality.get('rs_cell_count', 0)} of {market_quality.get('rs_cell_total', 0)}",
        f"- Market data note: {market_quality.get('note', 'No market data quality audit available.')}",
        f"- Ticker exceptions applied: {len(snapshot['ticker_diagnostics'].get('exceptions', []))}",
        f"- News confidence: {snapshot['news_confidence']}",
        f"- Outputs written: {', '.join(str(p) for p in snapshot['written_files'])}",
        "- Notes: Dashboard remains usable if RSS ingestion returns zero articles; scoring defaults to market-only factors.",
        "",
    ]
    lines.extend(build_ticker_exceptions_section(snapshot["ticker_diagnostics"]))
    lines.extend(build_count_section("Accepted Stories by Theme", snapshot["accepted_by_theme"], "theme"))
    lines.extend(build_count_section("Accepted Stories by Ticker", snapshot["accepted_by_ticker"], "ticker"))
    lines.extend(build_rejected_section(snapshot["rejected_articles"]))
    if snapshot["fetch_errors"]:
        lines.append("## RSS Errors")
        lines.append("")
        lines.extend(f"- {error}" for error in snapshot["fetch_errors"])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path

def append_score_history(snapshot: dict) -> Path:
    ensure_output_dirs()
    path = HISTORY_DIR / "dashboard_scores.jsonl"
    entry = build_score_history_entry(snapshot)
    if is_duplicate_same_minute_history_entry(path, entry):
        return path
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    return path


def build_score_history_entry(snapshot: dict) -> dict:
    return {
        "as_of_date": snapshot["as_of_date"],
        "overall_score": snapshot["overall_score"],
        "stance": snapshot["stance"],
        "lly_ai_trade_score": snapshot["lly_ai_trade_score"],
        "article_count": len(snapshot["articles"]),
        "accepted_story_count": snapshot["news_stats"]["accepted"],
        "qualified_story_count": snapshot["news_stats"]["qualified"],
    }


def is_duplicate_same_minute_history_entry(path: Path, entry: dict) -> bool:
    latest = latest_score_history_entry(path)
    if latest is None:
        return False
    latest_time = pd.to_datetime(latest.get("as_of_date"), utc=True, errors="coerce")
    entry_time = pd.to_datetime(entry.get("as_of_date"), utc=True, errors="coerce")
    if pd.isna(latest_time) or pd.isna(entry_time):
        return False
    if latest_time.floor("min") != entry_time.floor("min"):
        return False
    comparable_fields = [
        "overall_score",
        "stance",
        "lly_ai_trade_score",
        "article_count",
        "accepted_story_count",
        "qualified_story_count",
    ]
    return all(latest.get(field) == entry.get(field) for field in comparable_fields)


def latest_score_history_entry(path: Path) -> dict | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        for line in reversed(handle.read().splitlines()):
            if not line.strip():
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                return None
    return None


def format_timestamp(value: object) -> str:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return "Unknown"
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def format_number(value: object, decimals: int = 1) -> str:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return "Unknown"
    return f"{float(parsed):.{decimals}f}"


def format_delta(current: object, prior: object, decimals: int = 1) -> str:
    current_value = pd.to_numeric(current, errors="coerce")
    prior_value = pd.to_numeric(prior, errors="coerce")
    if pd.isna(current_value) or pd.isna(prior_value):
        return "Unknown"
    delta = float(current_value) - float(prior_value)
    return f"{delta:+.{decimals}f}"


def build_count_section(title: str, df: pd.DataFrame, label_column: str) -> list[str]:
    lines = [f"## {title}", ""]
    if df.empty:
        lines.append("- None")
        lines.append("")
        return lines
    for row in df.itertuples():
        label = getattr(row, label_column)
        lines.append(f"- {label}: {int(row.story_count)}")
    lines.append("")
    return lines


def build_rejected_section(rejected_df: pd.DataFrame) -> list[str]:
    lines = ["## Top Rejected Stories", ""]
    if rejected_df.empty:
        lines.append("- None")
        lines.append("")
        return lines

    top_rejected = rejected_df.head(10)
    for row in top_rejected.itertuples():
        lines.append(
            f"- {clean_report_text(row.title)} | stage={row.rejection_stage} | reason={clean_report_text(row.rejection_reason)}"
        )
    lines.append("")
    return lines


def clean_report_text(value: object) -> str:
    text = "" if value is None else str(value)
    replacements = {
        "â€™": "'",
        "â€˜": "'",
        "â€œ": '"',
        "â€�": '"',
        "â€“": "-",
        "â€”": "-",
        "–": "-",
        "—": "-",
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "→": "->",
        "≥": ">=",
        "≤": "<=",
        "…": "...",
        "§": "Section ",
        "Â ": " ",
        "Â": "",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text

def build_ticker_exceptions_section(ticker_diagnostics: dict[str, object]) -> list[str]:
    lines = ["## Ticker Exceptions", ""]
    exceptions = ticker_diagnostics.get("exceptions", [])
    if not exceptions:
        lines.append("- None")
        lines.append("")
        return lines

    for entry in exceptions:
        replacement = f" -> {entry['replacement']}" if entry.get("replacement") else ""
        lines.append(
            f"- {entry['ticker']}{replacement} | action={entry['action']} | reason={entry['reason']}"
        )
    lines.append("")
    return lines





