"""Phase 2: Catalyst Score per sleeve.

The Catalyst Score (0-100) measures near-term event-driven upside optionality
per sleeve from *unique material events* (Phase 1 clustering), never raw
article counts: per-category net signed event counts saturate, so one noisy
narrative cannot dominate.

Theme -> catalyst category mapping (spec's six categories):
- commercial: GLP-1 Demand, Consumer Behavior Impact, Healthcare Cost Reduction,
  Manufacturing / Supply
- clinical: AI Drug Discovery, Cardiovascular / Gene Editing, Longevity,
  Lilly AI Infrastructure
- regulatory: Regulatory Risk
- partnership: Lilly M&A / IP Acquisition (IP/licensing half)
- m&a: Lilly M&A / IP Acquisition (M&A half)
- policy: Obesity Policy / Pricing

Unmapped themes (GLP-1 Competition, Side Effects / Safety, ticker fallbacks)
contribute nothing: safety is a thesis drag, not a catalyst.

Each event is signed by the mean sentiment of its articles: positive adds,
negative subtracts, neutral counts zero. Per category, the net signed count
saturates at the configured per-category cap; the score is the mean across
the six categories, rewarding catalyst breadth over single-story spikes.
"""

from __future__ import annotations

import pandas as pd

from .health_stack_sleeves import Sleeve, ticker_to_sleeve_map

CATEGORIES = ("commercial", "clinical", "regulatory", "partnership", "m&a", "policy")

#: Theme -> tuple of catalyst categories it feeds.
CATALYST_CATEGORY_BY_THEME: dict[str, tuple[str, ...]] = {
    "GLP-1 Demand": ("commercial",),
    "Consumer Behavior Impact": ("commercial",),
    "Healthcare Cost Reduction": ("commercial",),
    "Manufacturing / Supply": ("commercial",),
    "AI Drug Discovery": ("clinical",),
    "Cardiovascular / Gene Editing": ("clinical",),
    "Longevity": ("clinical",),
    "Lilly AI Infrastructure": ("clinical",),
    "Regulatory Risk": ("regulatory",),
    "Lilly M&A / IP Acquisition": ("partnership", "m&a"),
    "Obesity Policy / Pricing": ("policy",),
}

POSITIVE_SENTIMENT = 0.15
NEGATIVE_SENTIMENT = -0.15


def _event_sign(mean_sentiment: float) -> int:
    if pd.isna(mean_sentiment):
        return 0
    if mean_sentiment > POSITIVE_SENTIMENT:
        return 1
    if mean_sentiment < NEGATIVE_SENTIMENT:
        return -1
    return 0


def _parse_tickers(value: object) -> set[str]:
    if value is None:
        return set()
    return {t.strip().upper() for t in str(value).split(",") if t.strip()}


def compute_catalyst_score(
    news_events: pd.DataFrame,
    articles_df: pd.DataFrame,
    sleeves: list[Sleeve],
    saturation_per_category: int = 3,
) -> pd.DataFrame:
    """One row per sleeve with the Catalyst Score (0-100)."""
    columns = [
        "sleeve",
        "required",
        "catalyst_score",
        "confidence",
        "note",
        "material_events",
        "category_counts",
    ]
    ticker_map = ticker_to_sleeve_map(sleeves)
    # Net signed material-event counts per sleeve per category.
    net: dict[str, dict[str, int]] = {
        sleeve.name: {category: 0 for category in CATEGORIES} for sleeve in sleeves
    }
    event_counts: dict[str, int] = {sleeve.name: 0 for sleeve in sleeves}

    if news_events is not None and not news_events.empty:
        sentiments = pd.Series(dtype=float)
        if articles_df is not None and not articles_df.empty and "event_id" in articles_df.columns:
            sentiment_col = (
                pd.to_numeric(articles_df["sentiment_score"], errors="coerce")
                if "sentiment_score" in articles_df.columns
                else pd.Series([float("nan")] * len(articles_df), index=articles_df.index)
            )
            sentiments = sentiment_col.groupby(articles_df["event_id"]).mean()

        for _, event in news_events.iterrows():
            event_id = event.get("event_id")
            event_tickers = _parse_tickers(event.get("tickers"))
            touched = {ticker_map[t] for t in event_tickers if t in ticker_map}
            if not touched:
                continue
            theme = str(event.get("theme") or event.get("themes") or "").split(",")[0].strip()
            categories = CATALYST_CATEGORY_BY_THEME.get(theme, ())
            if not categories:
                continue
            sign = _event_sign(float(sentiments.get(event_id, float("nan"))))
            for sleeve_name in touched:
                # Confidence counts signed evidence only: an event with no
                # articles (or neutral sentiment) moves no category and must
                # not inflate confidence.
                if sign != 0:
                    event_counts[sleeve_name] += 1
                for category in categories:
                    net[sleeve_name][category] += sign

    rows: list[dict[str, object]] = []
    for sleeve in sleeves:
        category_scores = [
            min(1.0, max(0, net[sleeve.name][category]) / saturation_per_category)
            for category in CATEGORIES
        ]
        score = 100.0 * sum(category_scores) / len(CATEGORIES)
        count = event_counts[sleeve.name]
        if count >= 3:
            confidence, note = "High", f"{count} material events touching sleeve"
        elif count >= 1:
            confidence, note = "Medium", f"{count} material events touching sleeve"
        else:
            confidence, note = "Low", "no material events touching sleeve"
        rows.append(
            {
                "sleeve": sleeve.name,
                "required": sleeve.required,
                "catalyst_score": round(score, 1),
                "confidence": confidence,
                "note": note,
                "material_events": count,
                "category_counts": dict(net[sleeve.name]),
            }
        )
    return pd.DataFrame(rows, columns=columns)
