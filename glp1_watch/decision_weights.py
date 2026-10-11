"""Phase 2: decision-layer weights and thresholds loading and validation.

Weights live in ``config/decision_weights.yaml`` so the scoring trade-offs
are operator-tunable without code changes. The loader validates loudly:

- every weight group sums to 1.0 (within 1e-6), no negative weights
- interpretation bands are sorted descending, cover 0-100, labels non-empty
- thresholds are present and sane (positive ints/floats where required)

Any violation raises ``ValueError`` instead of silently mis-scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "decision_weights.yaml"

REQUIRED_WEIGHT_GROUPS = (
    "opportunity_weights",
    "market_confirmation_weights",
    "expectations_risk_weights",
)


@dataclass(frozen=True)
class DecisionWeights:
    """Validated decision-layer weights and thresholds."""

    opportunity: dict[str, float]
    market_confirmation: dict[str, float]
    expectations_risk: dict[str, float]
    interpretation_bands: tuple[tuple[float, str], ...]
    catalyst_saturation_per_category: int
    trend_strong_threshold: float
    trend_weak_threshold: float
    recognition_gap_structural_min: float
    recognition_gap_catalyst_min: float
    recognition_gap_market_max: float


def _validate_weights(name: str, weights: object) -> dict[str, float]:
    if not isinstance(weights, dict) or not weights:
        raise ValueError(f"decision_weights: {name!r} must be a non-empty mapping.")
    cleaned: dict[str, float] = {}
    for key, value in weights.items():
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError(f"decision_weights: {name!r}[{key!r}] is not a number.")
        if number < 0:
            raise ValueError(f"decision_weights: {name!r}[{key!r}] is negative.")
        cleaned[str(key)] = number
    total = sum(cleaned.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            f"decision_weights: {name!r} sums to {total:.6f}, expected 1.0."
        )
    return cleaned


def _validate_bands(bands: object) -> tuple[tuple[float, str], ...]:
    if not isinstance(bands, list) or not bands:
        raise ValueError("decision_weights: interpretation_bands must be a non-empty list.")
    parsed: list[tuple[float, str]] = []
    for entry in bands:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise ValueError(f"decision_weights: bad band entry {entry!r}.")
        threshold, label = entry
        try:
            number = float(threshold)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError(f"decision_weights: bad band threshold {threshold!r}.")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"decision_weights: bad band label {label!r}.")
        parsed.append((number, label.strip()))
    thresholds = [threshold for threshold, _ in parsed]
    if thresholds != sorted(thresholds, reverse=True):
        raise ValueError("decision_weights: interpretation_bands must be sorted descending.")
    if thresholds[0] > 100 or thresholds[-1] > 0:
        raise ValueError("decision_weights: interpretation_bands must span 0-100.")
    if thresholds[-1] != 0:
        raise ValueError("decision_weights: lowest band threshold must be 0.")
    return tuple(parsed)


def load_decision_weights(path: str | Path = CONFIG_PATH) -> DecisionWeights:
    """Load and validate the decision weights configuration."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Decision weights config not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("decision_weights: config must be a mapping.")

    groups = {
        name: _validate_weights(name, data.get(name)) for name in REQUIRED_WEIGHT_GROUPS
    }
    bands = _validate_bands(data.get("interpretation_bands"))

    def _positive_number(key: str) -> float:
        value = data.get(key)
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError(f"decision_weights: {key!r} must be a number.")
        if number <= 0:
            raise ValueError(f"decision_weights: {key!r} must be positive.")
        return number

    def _threshold(key: str) -> float:
        value = data.get(key)
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError(f"decision_weights: {key!r} must be a number.")

    trend_strong = _threshold("trend_strong_threshold")
    trend_weak = _threshold("trend_weak_threshold")
    if not 0 < trend_weak < trend_strong <= 100:
        raise ValueError(
            "decision_weights: require 0 < trend_weak_threshold < "
            "trend_strong_threshold <= 100."
        )

    return DecisionWeights(
        opportunity=groups["opportunity_weights"],
        market_confirmation=groups["market_confirmation_weights"],
        expectations_risk=groups["expectations_risk_weights"],
        interpretation_bands=bands,
        catalyst_saturation_per_category=int(_positive_number("catalyst_saturation_per_category")),
        trend_strong_threshold=trend_strong,
        trend_weak_threshold=trend_weak,
        recognition_gap_structural_min=_threshold("recognition_gap_structural_min"),
        recognition_gap_catalyst_min=_threshold("recognition_gap_catalyst_min"),
        recognition_gap_market_max=_threshold("recognition_gap_market_max"),
    )


def interpret_opportunity(score: float, weights: DecisionWeights) -> str:
    """Map an opportunity score to its interpretation band label."""
    for threshold, label in weights.interpretation_bands:
        if score >= threshold:
            return label
    return weights.interpretation_bands[-1][1]
