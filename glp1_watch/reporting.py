from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import CLASSIFIED_DIR, HISTORY_DIR, REPORTS_DIR, VALIDATION_DIR


def ensure_output_dirs() -> None:
    for path in [REPORTS_DIR, CLASSIFIED_DIR, HISTORY_DIR, VALIDATION_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def write_performance_csv(performance_table: pd.DataFrame, as_of_stamp: str) -> Path:
    ensure_output_dirs()
    path = CLASSIFIED_DIR / f"ticker_performance_{as_of_stamp}.csv"
    performance_table.to_csv(path, index=False)
    return path


def write_articles_csv(articles_df: pd.DataFrame, as_of_stamp: str) -> Path:
    ensure_output_dirs()
    path = CLASSIFIED_DIR / f"classified_articles_{as_of_stamp}.csv"
    articles_df.to_csv(path, index=False)
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
            lines.append(
                f"- Supporting sleeve {row['sleeve']}: {row['status']} "
                f"(excluded from core breadth counts)"
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


def write_report(snapshot: dict, as_of_stamp: str) -> Path:
    ensure_output_dirs()
    path = REPORTS_DIR / f"glp1_ai_health_stack_watch_{as_of_stamp}.md"
    confirmation_section = build_confirmation_structure_section(snapshot)
    top_stories = select_key_stories(snapshot["articles"], limit=10)
    news_stats = snapshot["news_stats"]
    market_quality = snapshot.get("market_data_quality", {})
    prior_delta_lines = build_prior_snapshot_delta_lines(snapshot, HISTORY_DIR / "dashboard_scores.jsonl")

    lines = [
        "# GLP-1 AI Health Stack Watch",
        "",
        "## Executive Summary",
        "",
        f"- Current stance: {snapshot['stance']}",
        f"- Overall score: {snapshot['overall_score']:.1f}",
        f"- News confidence: {snapshot['news_confidence']}",
        f"- Market data quality: {market_quality.get('status', 'Unknown')}",
        f"- Market data note: {market_quality.get('note', 'No market data quality audit available.')}",
        f"- One-line interpretation: {snapshot['interpretation']}",
        f"- Positive score drivers: {', '.join(snapshot['positive_drivers']) if snapshot['positive_drivers'] else 'None'}",
        f"- Negative score drivers: {', '.join(snapshot['negative_drivers']) if snapshot['negative_drivers'] else 'None'}",
        "",
        *confirmation_section,
        "## Change Since Prior Run",
        "",
        *prior_delta_lines,
        "",
        "## Eli Lilly AI Trade",
        "",
        f"- LLY relative strength: {snapshot['lly_summary']}",
        f"- LLY trend status: {snapshot['lly_trend_status']}",
        f"- LLY news summary: {snapshot['lly_news_summary']}",
        f"- AI-trade confirmation score: {snapshot['lly_ai_trade_score']:.1f}",
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
    ]

    if top_stories.empty:
        lines.append("- No accepted relevant stories passed the relevance gate for this run.")

    for _, row in top_stories.iterrows():
        lines.extend(
            [
                f"- {clean_report_text(row['title'])}",
                f"  - Source: {clean_report_text(row['source']) if row['source'] else 'Unknown'}",
                f"  - Date: {format_timestamp(row['published_at'])}",
                f"  - Theme: {row['theme']}",
                f"  - Sentiment: {row['sentiment_label']} ({row['sentiment_score']:.2f})",
                f"  - Tickers: {row['tickers'] or 'None detected'}",
                f"  - URL: {row['url']}",
            ]
        )

    lines.extend(
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

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def select_key_stories(articles_df: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    if articles_df.empty:
        return articles_df.head(0)

    selected_indices: list[object] = []
    theme_counts: dict[str, int] = {}
    cluster_counts: dict[str, int] = {}

    for idx, row in articles_df.iterrows():
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
        for idx, row in articles_df.iterrows():
            if idx in selected_indices:
                continue
            cluster = story_cluster_key(row)
            if cluster_counts.get(cluster, 0) >= 2:
                continue
            selected_indices.append(idx)
            cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1
            if len(selected_indices) >= limit:
                break

    return articles_df.loc[selected_indices].head(limit)


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





