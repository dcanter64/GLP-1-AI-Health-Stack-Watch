"""Phase 2: Structural Thesis Score per sleeve.

The Structural Thesis Score (0-100) measures whether the long-term GLP-1
and AI-health flywheel is accumulating supporting evidence. With no
fundamentals feed available (no revenue, pipeline-database, or reimbursement
data), this is explicitly a *news-evidence* score, not a fundamentals
score: it aggregates qualified-story sentiment across thesis-relevant
themes for each sleeve's tickers.

Scoring is a Bayesian-smoothed net balance: with no evidence the score is
50 (neutral) at Low confidence, never 0. Missing data degrades confidence,
never the signal.

Theme roles:
- positive: demand, adoption, pipeline, partnership/M&A, AI-health progress
- negative: safety, regulatory, and supply constraints on the thesis
- mixed: counted by sentiment sign (positive mention helps, negative hurts)
- unlisted (e.g. ticker-fallback themes): ignored
"""

from __future__ import annotations

import pandas as pd

from .health_stack_sleeves import Sleeve, ticker_to_sleeve_map

#: Themes that count as positive structural evidence when sentiment is positive.
THESIS_POSITIVE_THEMES = frozenset(
    {
        "GLP-1 Demand",
        "AI Drug Discovery",
        "Lilly AI Infrastructure",
        "Lilly M&A / IP Acquisition",
        "Healthcare Cost Reduction",
        "Longevity",
        "Consumer Behavior Impact",
        "Cardiovascular / Gene Editing",
    }
)

#: Themes that count as negative structural evidence when sentiment is negative.
THESIS_NEGATIVE_THEMES = frozenset(
    {
        "Side Effects / Safety",
        "Regulatory Risk",
        "Manufacturing / Supply",
    }
)

#: Themes counted by sentiment sign either way.
THESIS_MIXED_THEMES = frozenset(
    {
        "Obesity Policy / Pricing",
        "GLP-1 Competition",
    }
)

POSITIVE_SENTIMENT = 0.15
NEGATIVE_SENTIMENT = -0.15

#: Bayesian smoothing: with zero evidence the score is exactly 50 (neutral).
SMOOTHING = 2.0


def _sleeve_tickers(article_tickers: object, ticker_map: dict[str, str]) -> set[str]:
    if article_tickers is None:
        return set()
    sleeves = set()
    for ticker in str(article_tickers).split(","):
        ticker = ticker.strip().upper()
        if ticker in ticker_map:
            sleeves.add(ticker_map[ticker])
    return sleeves


def compute_structural_thesis(
    qualified_articles: pd.DataFrame,
    sleeves: list[Sleeve],
) -> pd.DataFrame:
    """One row per sleeve with the Structural Thesis Score (0-100).

    Inputs are the qualified scoring articles (signal quality) with
    ``tickers``, ``theme``, and ``sentiment_score`` columns.
    """
    columns = [
        "sleeve",
        "required",
        "structural_score",
        "confidence",
        "note",
        "pos_stories",
        "neg_stories",
    ]
    ticker_map = ticker_to_sleeve_map(sleeves)
    counts: dict[str, dict[str, int]] = {
        sleeve.name: {"pos": 0, "neg": 0} for sleeve in sleeves
    }

    if qualified_articles is not None and not qualified_articles.empty:
        frame = qualified_articles
        sentiments = (
            pd.to_numeric(frame["sentiment_score"], errors="coerce")
            if "sentiment_score" in frame.columns
            else pd.Series([float("nan")] * len(frame), index=frame.index)
        )
        themes = frame["theme"].astype(str) if "theme" in frame.columns else ""
        tickers = frame["tickers"] if "tickers" in frame.columns else ""
        for idx in frame.index:
            sentiment = sentiments.loc[idx]
            if pd.isna(sentiment):
                continue
            theme = themes.loc[idx] if not isinstance(themes, str) else ""
            is_pos = sentiment > POSITIVE_SENTIMENT and (
                theme in THESIS_POSITIVE_THEMES or theme in THESIS_MIXED_THEMES
            )
            is_neg = sentiment < NEGATIVE_SENTIMENT and (
                theme in THESIS_NEGATIVE_THEMES or theme in THESIS_MIXED_THEMES
            )
            if not (is_pos or is_neg):
                continue
            for sleeve_name in _sleeve_tickers(tickers.loc[idx], ticker_map):
                counts[sleeve_name]["pos" if is_pos else "neg"] += 1

    rows: list[dict[str, object]] = []
    for sleeve in sleeves:
        pos = counts[sleeve.name]["pos"]
        neg = counts[sleeve.name]["neg"]
        total = pos + neg
        raw = 100.0 * (pos - neg + SMOOTHING) / (total + 2 * SMOOTHING)
        score = min(100.0, max(0.0, raw))
        if total >= 10:
            confidence, note = "High", f"{total} thesis-relevant qualified stories"
        elif total >= 3:
            confidence, note = "Medium", f"{total} thesis-relevant qualified stories"
        else:
            confidence, note = (
                "Low",
                "insufficient thesis-relevant stories; score is near-neutral by construction",
            )
        rows.append(
            {
                "sleeve": sleeve.name,
                "required": sleeve.required,
                "structural_score": round(score, 1),
                "confidence": confidence,
                "note": note,
                "pos_stories": pos,
                "neg_stories": neg,
            }
        )
    return pd.DataFrame(rows, columns=columns)
