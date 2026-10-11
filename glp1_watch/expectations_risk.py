"""Phase 2: Expectations Risk Score per sleeve.

The Expectations Risk Score (0-100, higher = riskier) measures how hard the
sleeve's price action has become to satisfy: extended, accelerated, crowded
moves on saturating good news. Components:

- acceleration: 1M pace running well ahead of the 3M monthly pace
- extension: average distance above the 50DMA (from price history)
- no_drawdown: trading at/near 52-week highs with no pullback
- narrow_leadership: within-sleeve gains concentrated in the top name
- news_saturation: sleeve's qualified stories dominated by strongly positive
  sentiment at high volume

Valuation and earnings-revision data are unavailable: per the spec, the
score reports reduced confidence (capped at Medium) rather than inventing
them. Components with missing inputs are skipped with weights renormalized.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .decision_weights import DecisionWeights
from .health_stack_sleeves import Sleeve
from .market_data import extract_close_prices

MIN_SLEEVE_COVERAGE = 0.5
POSITIVE_SATURATION_SENTIMENT = 0.4


def _clip01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def _mean_or_nan(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else float("nan")


def _sleeve_extension(close_prices: pd.DataFrame, tickers: tuple[str, ...]) -> float:
    """Mean (price - 50DMA) / 50DMA across sleeve tickers."""
    available = [t for t in tickers if t in close_prices.columns]
    if not available:
        return float("nan")
    prices = close_prices[available].dropna(how="all")
    if len(prices) < 60:
        return float("nan")
    ma50 = prices.rolling(50).mean().iloc[-1]
    latest = prices.iloc[-1]
    extensions = ((latest - ma50) / ma50).replace([np.inf, -np.inf], np.nan).dropna()
    return float(extensions.mean()) if not extensions.empty else float("nan")


def _sleeve_top1_share(performance_table: pd.DataFrame, tickers: tuple[str, ...]) -> float:
    frame = performance_table[performance_table["ticker"].isin(tickers)]
    if frame.empty or "return_3m" not in frame.columns:
        return float("nan")
    returns = pd.to_numeric(frame["return_3m"], errors="coerce").dropna()
    positive = returns[returns > 0]
    if positive.empty or positive.sum() <= 0:
        return 0.0  # no positive gains to concentrate: no concentration risk
    return float(positive.max() / positive.sum())


def compute_expectations_risk(
    performance_table: pd.DataFrame,
    price_history: pd.DataFrame,
    qualified_articles: pd.DataFrame,
    sleeves: list[Sleeve],
    weights: DecisionWeights,
    ticker_to_sleeve: dict[str, str] | None = None,
) -> pd.DataFrame:
    """One row per sleeve with the Expectations Risk Score (0-100)."""
    columns = [
        "sleeve",
        "required",
        "expectations_risk_score",
        "confidence",
        "note",
        "components",
    ]
    close_prices = (
        extract_close_prices(price_history) if not price_history.empty else pd.DataFrame()
    )
    if ticker_to_sleeve is None:
        from .health_stack_sleeves import ticker_to_sleeve_map

        ticker_to_sleeve = ticker_to_sleeve_map(sleeves)
    configured = weights.expectations_risk

    # Per-sleeve qualified-story stats for the saturation component.
    saturation: dict[str, dict[str, float]] = {
        sleeve.name: {"pos": 0, "total": 0} for sleeve in sleeves
    }
    if qualified_articles is not None and not qualified_articles.empty:
        sentiments = (
            pd.to_numeric(qualified_articles["sentiment_score"], errors="coerce")
            if "sentiment_score" in qualified_articles.columns
            else pd.Series([float("nan")] * len(qualified_articles), index=qualified_articles.index)
        )
        tickers_col = (
            qualified_articles["tickers"]
            if "tickers" in qualified_articles.columns
            else pd.Series([""] * len(qualified_articles), index=qualified_articles.index)
        )
        for idx in qualified_articles.index:
            sentiment = sentiments.loc[idx]
            if pd.isna(sentiment):
                continue
            touched = {
                ticker_to_sleeve[t]
                for t in str(tickers_col.loc[idx]).split(",")
                if t.strip().upper() in ticker_to_sleeve
            }
            for sleeve_name in touched:
                saturation[sleeve_name]["total"] += 1
                if sentiment > POSITIVE_SATURATION_SENTIMENT:
                    saturation[sleeve_name]["pos"] += 1

    rows: list[dict[str, object]] = []
    for sleeve in sleeves:
        frame = (
            performance_table[performance_table["ticker"].isin(sleeve.tickers)]
            if not performance_table.empty
            else performance_table
        )
        usable = (
            pd.to_numeric(frame["return_3m"], errors="coerce").notna().sum()
            if not frame.empty and "return_3m" in frame.columns
            else 0
        )
        coverage = usable / len(sleeve.tickers) if sleeve.tickers else 0.0
        if coverage < MIN_SLEEVE_COVERAGE:
            rows.append(
                {
                    "sleeve": sleeve.name,
                    "required": sleeve.required,
                    "expectations_risk_score": float("nan"),
                    "confidence": "Low",
                    "note": "insufficient data: sleeve coverage below 50%",
                    "components": {},
                }
            )
            continue

        r1m = _mean_or_nan(frame["return_1m"]) if "return_1m" in frame.columns else float("nan")
        r3m = _mean_or_nan(frame["return_3m"]) if "return_3m" in frame.columns else float("nan")
        drawdown = (
            -_mean_or_nan(frame["distance_from_52w_high"])
            if "distance_from_52w_high" in frame.columns
            else float("nan")
        )
        extension = _sleeve_extension(close_prices, sleeve.tickers)
        top1 = _sleeve_top1_share(performance_table, sleeve.tickers)
        sat = saturation[sleeve.name]

        components: dict[str, float] = {}
        if not np.isnan(r1m) and not np.isnan(r3m):
            components["acceleration"] = 100.0 * _clip01((r1m - r3m / 3) / 0.15)
        if not np.isnan(extension):
            components["extension"] = 100.0 * _clip01(extension / 0.25)
        if not np.isnan(drawdown):
            components["no_drawdown"] = 100.0 * (1.0 - _clip01(drawdown / 0.3))
        if not np.isnan(top1):
            components["narrow_leadership"] = 100.0 * _clip01(top1)
        if sat["total"] > 0:
            pos_share = sat["pos"] / sat["total"]
            components["news_saturation"] = 100.0 * pos_share * _clip01(sat["total"] / 10)

        available = {k: v for k, v in components.items() if k in configured}
        missing = sorted(set(configured) - set(available))
        weight_sum = sum(configured[k] for k in available)
        if available and weight_sum > 0:
            score = sum(components[k] * configured[k] for k in available) / weight_sum
        else:
            score = float("nan")
            if available and not missing:
                missing = ["all configured weight on missing components"]
        # Valuation and earnings-revision data are unavailable: confidence is
        # capped at Medium by spec, never invented.
        if np.isnan(score):
            confidence, note = "Low", "no usable risk inputs"
        elif missing:
            confidence = "Low"
            note = f"reduced: no valuation/revision data; missing: {', '.join(missing)}"
        else:
            confidence = "Medium"
            note = "reduced: no valuation or earnings-revision data"
        rows.append(
            {
                "sleeve": sleeve.name,
                "required": sleeve.required,
                "expectations_risk_score": round(score, 1) if not np.isnan(score) else float("nan"),
                "confidence": confidence,
                "note": note,
                "components": {k: round(v, 1) for k, v in available.items()},
            }
        )
    return pd.DataFrame(rows, columns=columns)
