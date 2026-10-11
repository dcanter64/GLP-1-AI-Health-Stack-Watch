"""Phase 1: news-event clustering.

Multiple articles about one lawsuit, clinical result, regulatory action, or
partnership should count as one underlying event with multiple sources.
Syndicated coverage rarely shares identical headlines, so clustering is
fuzzy, not exact: a candidate joins an existing event only when all four
signals agree:

- same news theme (exact match),
- overlapping ticker sets (at least one shared ticker; untagged stories
  never merge),
- title similarity: Jaccard overlap of significant title tokens
  (alphanumeric, length >= 5) at or above TITLE_SIMILARITY_THRESHOLD,
- time proximity: published timestamps within EVENT_TIME_WINDOW_HOURS of
  the event seed (missing timestamps are neutral, not blocking).

Clustering is greedy and deterministic: articles are processed in
(published_at, title) order and each joins the first matching event,
otherwise it seeds a new one. Thresholds are heuristic judgment calls;
counts are directional, not precise.

A "material" event is a heuristic flag: high relevance, a material theme, or
three or more independent sources covering it.
"""

from __future__ import annotations

import re

import pandas as pd

from .reporting import clean_report_text

#: Jaccard similarity of significant title tokens required to link two stories.
TITLE_SIMILARITY_THRESHOLD = 0.3

#: Maximum age gap (hours) between a story and an event seed to join it.
EVENT_TIME_WINDOW_HOURS = 72

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


def _title_tokens(title: object) -> set[str]:
    text = clean_report_text(title).lower()
    return {token for token in re.findall(r"[a-z0-9]+", text) if len(token) >= 5}


def _ticker_set(value: object) -> set[str]:
    if value is None:
        return set()
    return {ticker.strip().upper() for ticker in str(value).split(",") if ticker.strip()}


def _jaccard(first: set[str], second: set[str]) -> float:
    if not first and not second:
        return 0.0
    return len(first & second) / len(first | second)


def _same_event(candidate: pd.Series, seed: pd.Series) -> bool:
    """All four signals must agree for a candidate to join the seed's event."""
    if str(candidate.get("theme") or "") != str(seed.get("theme") or ""):
        return False
    if not (_ticker_set(candidate.get("tickers")) & _ticker_set(seed.get("tickers"))):
        return False
    if (
        _jaccard(_title_tokens(candidate.get("title")), _title_tokens(seed.get("title")))
        < TITLE_SIMILARITY_THRESHOLD
    ):
        return False
    candidate_time = pd.to_datetime(candidate.get("published_at"), utc=True, errors="coerce")
    seed_time = pd.to_datetime(seed.get("published_at"), utc=True, errors="coerce")
    if pd.isna(candidate_time) or pd.isna(seed_time):
        return True  # missing timestamps are neutral, not blocking
    hours_apart = abs((candidate_time - seed_time).total_seconds()) / 3600
    return hours_apart <= EVENT_TIME_WINDOW_HOURS


def _independent_source_count(sources: pd.Series) -> int:
    cleaned = sources.fillna("").astype(str).str.strip().str.lower()
    cleaned = cleaned[~cleaned.isin({"", "unknown"})]
    return int(cleaned.nunique())


def cluster_news_events(
    articles_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cluster accepted articles into events.

    Returns ``(articles_with_event_id, events)``. The articles frame gains an
    ``event_id`` column (``EVT-001`` style, deterministic in
    (published_at, title) order); the events frame has one row per unique
    event with story/source counts and a material flag. Empty input yields
    empty frames with the expected columns.
    """
    articles = articles_df.copy()
    if articles.empty:
        articles["event_id"] = pd.Series(dtype=str)
        return articles, pd.DataFrame(columns=EVENT_COLUMNS)

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

    ordered = articles.sort_values(
        ["_published_parsed", "title"], na_position="last"
    ).reset_index(drop=False, names="_original_index")

    # Greedy deterministic clustering: each article joins the first matching
    # event seed, otherwise it seeds a new event.
    seeds: list[int] = []  # positional indices into `ordered`
    event_of_position: dict[int, str] = {}
    for position in range(len(ordered)):
        candidate = ordered.iloc[position]
        event_id = None
        for event_number, seed_position in enumerate(seeds, start=1):
            if _same_event(candidate, ordered.iloc[seed_position]):
                event_id = f"EVT-{event_number:03d}"
                break
        if event_id is None:
            seeds.append(position)
            event_id = f"EVT-{len(seeds):03d}"
        event_of_position[position] = event_id

    ordered["event_id"] = ordered.index.map(event_of_position)
    articles["event_id"] = (
        ordered.set_index("_original_index")["event_id"].reindex(articles.index).values
    )

    event_rows: list[dict[str, object]] = []
    for event_id, group in articles.groupby("event_id", sort=False):
        independent_sources = _independent_source_count(group["source"])
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
