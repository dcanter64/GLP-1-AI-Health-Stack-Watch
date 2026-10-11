"""Phase 2: Market Confirmation Score per sleeve.

The Market Confirmation Score (0-100) measures whether the market is
rewarding the thesis for each sleeve, from price and trend data only:

- absolute_3m: scaled average 3M return
- rs_breadth: average share outperforming XLV/SPY/QQQ (3M)
- trend_position: average share above 50/200DMA
- drawdown: proximity to 52-week highs (closer = higher)
- momentum_pace: 1M pace versus 3M monthly pace (improving momentum scores higher)
- volatility: annualized daily-return volatility from price history (lower = higher)
- concentration: within-sleeve breadth of gains (1 - top-name share of positive 3M returns)

Components with missing inputs are skipped and the configured weights are
renormalized over the available components; the confidence note records
what was missing. Sleeves below 50% data coverage get no score
("insufficient data") rather than a fabricated one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .decision_weights import DecisionWeights
from .health_stack_sleeves import Sleeve
from .market_data import extract_close_prices

MIN_SLEEVE_COVERAGE = 0.5


def _clip01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def _mean_or_nan(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else float("nan")


def _sleeve_frame(
    performance_table: pd.DataFrame, tickers: tuple[str, ...]
) -> pd.DataFrame:
    if performance_table.empty:
        return performance_table
    return performance_table[performance_table["ticker"].isin(tickers)]


def _within_sleeve_top1_share(frame: pd.DataFrame) -> float:
    if frame.empty or "return_3m" not in frame.columns:
        return float("nan")
    returns = pd.to_numeric(frame["return_3m"], errors="coerce").dropna()
    positive = returns[returns > 0]
    if positive.empty or positive.sum() <= 0:
        return float("nan")
    return float(positive.max() / positive.sum())


def _sleeve_volatility(
    close_prices: pd.DataFrame, tickers: tuple[str, ...]
) -> float:
    available = [t for t in tickers if t in close_prices.columns]
    if not available:
        return float("nan")
    prices = close_prices[available].dropna(how="all")
    if len(prices) < 20:
        return float("nan")
    daily = prices.pct_change().dropna(how="all")
    vols = daily.std() * np.sqrt(252)
    vols = vols.replace([np.inf, -np.inf], np.nan).dropna()
    return float(vols.mean()) if not vols.empty else float("nan")


def compute_market_confirmation(
    performance_table: pd.DataFrame,
    price_history: pd.DataFrame,
    sleeves: list[Sleeve],
    weights: DecisionWeights,
) -> pd.DataFrame:
    """One row per sleeve with the Market Confirmation Score (0-100)."""
    columns = [
        "sleeve",
        "required",
        "market_confirmation_score",
        "confidence",
        "note",
        "avg_return_1m",
        "avg_return_3m",
        "components",
    ]
    close_prices = (
        extract_close_prices(price_history) if not price_history.empty else pd.DataFrame()
    )
    configured = weights.market_confirmation

    rows: list[dict[str, object]] = []
    for sleeve in sleeves:
        frame = _sleeve_frame(performance_table, sleeve.tickers)
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
                    "market_confirmation_score": float("nan"),
                    "confidence": "Low",
                    "note": "insufficient data: sleeve coverage below 50%",
                    "avg_return_1m": float("nan"),
                    "avg_return_3m": float("nan"),
                    "components": {},
                }
            )
            continue

        r3m = _mean_or_nan(frame["return_3m"]) if "return_3m" in frame.columns else float("nan")
        r1m = _mean_or_nan(frame["return_1m"]) if "return_1m" in frame.columns else float("nan")
        # NaN RS values must be masked BEFORE the > 0 comparison: NaN > 0 is
        # False, which would fabricate a 0.0 share (deterioration) during a
        # benchmark outage instead of skipping the component.
        rs_shares = []
        for col in ("rs_vs_xlv", "rs_vs_spy", "rs_vs_qqq"):
            if col not in frame.columns:
                continue
            series = pd.to_numeric(frame[col], errors="coerce").dropna()
            if not series.empty:
                rs_shares.append(float((series > 0).mean()))
        above_50 = _mean_or_nan(frame["above_50dma"].astype(float)) if "above_50dma" in frame.columns else float("nan")
        above_200 = _mean_or_nan(frame["above_200dma"].astype(float)) if "above_200dma" in frame.columns else float("nan")
        drawdown = (
            -_mean_or_nan(frame["distance_from_52w_high"])
            if "distance_from_52w_high" in frame.columns
            else float("nan")
        )
        vol = _sleeve_volatility(close_prices, sleeve.tickers)
        top1 = _within_sleeve_top1_share(frame)

        components: dict[str, float] = {}
        if not np.isnan(r3m):
            components["absolute_3m"] = 50.0 + 50.0 * float(min(1.0, max(-1.0, r3m / 0.3)))
        if rs_shares:
            components["rs_breadth"] = 100.0 * float(np.mean(rs_shares))
        trend_bits = [v for v in (above_50, above_200) if not np.isnan(v)]
        if trend_bits:
            components["trend_position"] = 100.0 * float(np.mean(trend_bits))
        if not np.isnan(drawdown):
            components["drawdown"] = 100.0 * (1.0 - _clip01(drawdown / 0.5))
        if not np.isnan(r1m) and not np.isnan(r3m):
            components["momentum_pace"] = 50.0 + 50.0 * float(min(1.0, max(-1.0, (r1m - r3m / 3) / 0.1)))
        if not np.isnan(vol):
            components["volatility"] = 100.0 * (1.0 - _clip01((vol - 0.15) / 0.85))
        if not np.isnan(top1):
            components["concentration"] = 100.0 * (1.0 - _clip01(top1))

        available = {k: v for k, v in components.items() if k in configured}
        missing = sorted(set(configured) - set(available))
        weight_sum = sum(configured[k] for k in available)
        if available and weight_sum > 0:
            score = sum(components[k] * configured[k] for k in available) / weight_sum
        else:
            score = float("nan")
            if available and not missing:
                missing = ["all configured weight on missing components"]
        if coverage >= 0.9 and not missing:
            confidence, note = "High", "full component coverage"
        elif not missing:
            confidence, note = "Medium", f"coverage {coverage:.0%}"
        else:
            confidence, note = "Medium", f"missing components: {', '.join(missing)}"
        rows.append(
            {
                "sleeve": sleeve.name,
                "required": sleeve.required,
                "market_confirmation_score": round(score, 1) if not np.isnan(score) else float("nan"),
                "confidence": confidence,
                "note": note,
                "avg_return_1m": round(r1m, 4) if not np.isnan(r1m) else float("nan"),
                "avg_return_3m": round(r3m, 4) if not np.isnan(r3m) else float("nan"),
                "components": {k: round(v, 1) for k, v in available.items()},
            }
        )
    return pd.DataFrame(rows, columns=columns)
