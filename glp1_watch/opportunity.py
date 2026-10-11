"""Phase 2: Sleeve Opportunity Scores, trend classification, and ranking.

The Opportunity Score (0-100) blends the four component scores per sleeve:

    opportunity = w_mkt * market_confirmation
              + w_struct * structural_thesis
              + w_cat * catalyst
              + w_risk * (100 - expectations_risk)

Expectations risk is inverted (higher risk lowers opportunity). Any missing
component, or sleeve coverage below 50%, yields no score ("insufficient
data") rather than a partial blend: an opportunity score that silently
ignores a missing risk input would be worse than none.

Trend classification combines the opportunity level with a stateless
momentum proxy (1M pace versus 3M monthly pace). True persistence tracking
arrives in Phase 3; the proxy is documented as such.

Recognition gap: strong structural thesis (>= 60) and strong catalysts
(>= 60) with weak market confirmation (< 45) — the market may not yet have
recognized the evidence. Flagged, never scored around.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .decision_weights import DecisionWeights, interpret_opportunity
from .health_stack_sleeves import Sleeve

MIN_SLEEVE_COVERAGE = 0.5


def _trend_label(
    opportunity: float,
    return_1m: float,
    return_3m: float,
    weights: DecisionWeights,
) -> str:
    if np.isnan(opportunity):
        return "Unknown"
    if opportunity >= weights.trend_strong_threshold:
        level = "Strong"
    elif opportunity >= weights.trend_weak_threshold:
        level = "Neutral"
    else:
        level = "Weak"
    # Stateless momentum proxy: recent monthly pace versus 3M monthly pace.
    if np.isnan(return_1m) or np.isnan(return_3m):
        direction = "direction unknown"
    elif return_1m >= return_3m / 3:
        direction = "improving"
    else:
        direction = "decelerating" if level == "Strong" else "deteriorating"
    mapping = {
        ("Strong", "improving"): "Strong and improving",
        ("Strong", "decelerating"): "Strong but decelerating",
        ("Neutral", "improving"): "Neutral and improving",
        ("Neutral", "deteriorating"): "Neutral and deteriorating",
        ("Weak", "improving"): "Weak but improving",
        ("Weak", "deteriorating"): "Weak and deteriorating",
    }
    return mapping.get((level, direction), f"{level} ({direction})")


def compute_opportunity_scores(
    market_df: pd.DataFrame,
    structural_df: pd.DataFrame,
    catalyst_df: pd.DataFrame,
    risk_df: pd.DataFrame,
    sleeve_summaries: pd.DataFrame,
    sleeves: list[Sleeve],
    weights: DecisionWeights,
) -> pd.DataFrame:
    """One row per sleeve with the Opportunity Score and trend label."""
    columns = [
        "sleeve",
        "required",
        "opportunity_score",
        "interpretation",
        "trend",
        "recognition_gap",
        "confidence",
        "note",
        "structural_score",
        "market_confirmation_score",
        "catalyst_score",
        "expectations_risk_score",
    ]
    w = weights.opportunity
    coverage = (
        dict(zip(sleeve_summaries["sleeve"], sleeve_summaries["coverage"]))
        if not sleeve_summaries.empty
        else {}
    )
    # Per-sleeve return paces for the trend proxy come from the market
    # confirmation frame, which already computes them.
    avg_1m = (
        dict(zip(market_df["sleeve"], market_df["avg_return_1m"]))
        if not market_df.empty and "avg_return_1m" in market_df.columns
        else {}
    )
    avg_3m = (
        dict(zip(market_df["sleeve"], market_df["avg_return_3m"]))
        if not market_df.empty and "avg_return_3m" in market_df.columns
        else {}
    )

    def _score(frame: pd.DataFrame, sleeve_name: str, column: str) -> float:
        if frame.empty or column not in frame.columns:
            return float("nan")
        rows = frame[frame["sleeve"] == sleeve_name]
        if rows.empty:
            return float("nan")
        value = pd.to_numeric(rows.iloc[0][column], errors="coerce")
        return float(value) if not pd.isna(value) else float("nan")

    rows: list[dict[str, object]] = []
    for sleeve in sleeves:
        name = sleeve.name
        mkt = _score(market_df, name, "market_confirmation_score")
        struct = _score(structural_df, name, "structural_score")
        cat = _score(catalyst_df, name, "catalyst_score")
        risk = _score(risk_df, name, "expectations_risk_score")
        cov = coverage.get(name, 0.0)

        parts = {"market_confirmation": mkt, "structural_thesis": struct, "catalyst": cat}
        missing = [k for k, v in parts.items() if np.isnan(v)] + (
            ["expectations_risk"] if np.isnan(risk) else []
        )
        if missing or cov < MIN_SLEEVE_COVERAGE:
            rows.append(
                {
                    "sleeve": name,
                    "required": sleeve.required,
                    "opportunity_score": float("nan"),
                    "interpretation": "Insufficient data",
                    "trend": "Unknown",
                    "recognition_gap": False,
                    "confidence": "Low",
                    "note": (
                        f"insufficient data: missing {', '.join(missing)}"
                        if missing
                        else "insufficient data: sleeve coverage below 50%"
                    ),
                    "structural_score": struct,
                    "market_confirmation_score": mkt,
                    "catalyst_score": cat,
                    "expectations_risk_score": risk,
                }
            )
            continue

        opportunity = (
            w["market_confirmation"] * mkt
            + w["structural_thesis"] * struct
            + w["catalyst"] * cat
            + w["expectations_risk"] * (100.0 - risk)
        )
        r1m = float(avg_1m.get(name, float("nan")))
        r3m = float(avg_3m.get(name, float("nan")))
        trend = _trend_label(opportunity, r1m, r3m, weights)
        recognition_gap = (
            struct >= weights.recognition_gap_structural_min
            and cat >= weights.recognition_gap_catalyst_min
            and mkt < weights.recognition_gap_market_max
        )
        confidences = []
        for frame, column in (
            (market_df, "confidence"),
            (structural_df, "confidence"),
            (catalyst_df, "confidence"),
            (risk_df, "confidence"),
        ):
            if not frame.empty and column in frame.columns:
                sub = frame[frame["sleeve"] == name]
                if not sub.empty:
                    confidences.append(str(sub.iloc[0][column]))
        confidence = "Low" if "Low" in confidences else ("Medium" if "Medium" in confidences else "High")
        rows.append(
            {
                "sleeve": name,
                "required": sleeve.required,
                "opportunity_score": round(opportunity, 1),
                "interpretation": interpret_opportunity(opportunity, weights),
                "trend": trend,
                "recognition_gap": bool(recognition_gap),
                "confidence": confidence,
                "note": "recognition gap: strong thesis/catalysts, weak market confirmation"
                if recognition_gap
                else "",
                "structural_score": struct,
                "market_confirmation_score": mkt,
                "catalyst_score": cat,
                "expectations_risk_score": risk,
            }
        )
    ranking = pd.DataFrame(rows, columns=columns)
    if not ranking.empty:
        ranking = ranking.sort_values(
            "opportunity_score", ascending=False, na_position="last"
        ).reset_index(drop=True)
        ranking["rank"] = ranking["opportunity_score"].rank(
            method="min", ascending=False, na_option="keep"
        )
    return ranking
