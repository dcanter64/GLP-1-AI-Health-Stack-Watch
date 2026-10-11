"""Phase 1: heuristic news-event clustering.

Multiple articles about one lawsuit, clinical result, regulatory action, or
partnership should count as one underlying event with multiple sources.

This is intentionally heuristic, not NLP: the event key reuses the existing
``story_cluster_key`` (theme + significant title tokens, with a special case
for LLY/NVO legal-ad disputes). Two different events can share a key if their
titles are near-identical, and one event can split across keys if headlines
are worded very differently. Both failure modes are documented as a Phase 1
limitation; the counts are directional, not precise.

A "material" event is a heuristic flag: high relevance, a material theme, or
three or more independent sources covering it.
"""

from __future__ import annotations

import pandas as pd

from .reporting import story_cluster_key

#: Themes treated as material on their own.
MATERIAL_THEMES = frozenset(
    {
        "Regulatory Risk",
        "Side Effects / Safety",
        "Lilly M&A / IP Acquisition",
        "Obesity Policy / Pricing",
    }
)

#: Relevance score at or above which an event is material regardless of theme.
MATERIAL_RELEVANCE_THRESHOLD = 0.6

#: Independent-source count at or above which an event is material.
MATERIAL_SOURCE_COUNT = 3

EVENT_COLUMNS = [
    "event_id",
    "story_count",
    "independent_sources",
    "tickers",
    "themes",
    "first_seen",
    "last_seen",
    "max_relevance",
    "material",
    "headline",
]


def _independent_source_count(sources: pd.Series) -> int:
    cleaned = sources.fillna("").astype(str).str.strip()
    cleaned = cleaned[~cleaned.str.lower().isin({"", "unknown"})]
    return int(cleaned.nunique())


def cluster_news_events(
    articles_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cluster accepted articles into events.

    Returns ``(articles_with_event_id, events)``. The articles frame gains an
    ``event_id`` column; the events frame has one row per unique event with
    story/source counts and a material flag. Empty input yields empty frames
    with the expected columns.
    """
    articles = articles_df.copy()
    if articles.empty:
        articles["event_id"] = pd.Series(dtype=str)
        return articles, pd.DataFrame(columns=EVENT_COLUMNS)

    articles["event_id"] = articles.apply(story_cluster_key, axis=1)

    if "published_at" in articles.columns:
        articles["_published_parsed"] = pd.to_datetime(
            articles["published_at"], utc=True, errors="coerce"
        )
    else:
        articles["_published_parsed"] = pd.NaT
    if "relevance_score" not in articles.columns:
        articles["relevance_score"] = 0.0
    if "source" not in articles.columns:
        articles["source"] = ""
    if "tickers" not in articles.columns:
        articles["tickers"] = ""
    if "theme" not in articles.columns:
        articles["theme"] = "Other"
    if "title" not in articles.columns:
        articles["title"] = ""

    event_rows: list[dict[str, object]] = []
    for event_id, group in articles.groupby("event_id"):
        sources = group["source"]
        independent_sources = _independent_source_count(sources)
        tickers = sorted(
            {
                ticker.strip()
                for value in group["tickers"].fillna("").astype(str)
                for ticker in value.split(",")
                if ticker.strip()
            }
        )
        themes = sorted(set(group["theme"].fillna("Other").astype(str)))
        max_relevance = float(
            pd.to_numeric(group["relevance_score"], errors="coerce").fillna(0.0).max()
        )
        headline_row = group.sort_values("relevance_score", ascending=False).iloc[0]
        material = (
            max_relevance >= MATERIAL_RELEVANCE_THRESHOLD
            or bool(set(themes) & MATERIAL_THEMES)
            or independent_sources >= MATERIAL_SOURCE_COUNT
        )
        event_rows.append(
            {
                "event_id": str(event_id),
                "story_count": int(len(group)),
                "independent_sources": independent_sources,
                "tickers": ", ".join(tickers),
                "themes": ", ".join(themes),
                "first_seen": group["_published_parsed"].min(),
                "last_seen": group["_published_parsed"].max(),
                "max_relevance": round(max_relevance, 3),
                "material": bool(material),
                "headline": str(headline_row["title"]),
            }
        )

    events = pd.DataFrame(event_rows, columns=EVENT_COLUMNS)
    if not events.empty:
        events = events.sort_values("story_count", ascending=False).reset_index(drop=True)
    articles = articles.drop(columns=["_published_parsed"])
    return articles, events


def summarize_event_counts(events_df: pd.DataFrame) -> dict[str, int]:
    """Compact counts for reporting: events, material events, multi-source events."""
    if events_df.empty:
        return {"unique_events": 0, "material_events": 0, "multi_source_events": 0}
    return {
        "unique_events": int(len(events_df)),
        "material_events": int(events_df["material"].astype(bool).sum()),
        "multi_source_events": int((events_df["independent_sources"] >= 2).sum()),
    }
