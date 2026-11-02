"""Phase 4: Capital Allocation Decision Layer.

Converts analytical outputs (opportunity scores, readiness states,
persistence metrics) into explicit allocation recommendations.

Analytical, not execution: tiers are conviction statements, not trade
instructions. Nothing here places orders, moves capital, or sizes
positions in percent terms.

Inputs consumed: opportunity ranking (Phase 2), persistence table and
readiness (Phase 3), confirmation state and concentration (Phase 1),
news events with material themes.

Outputs per sleeve (a "decision card"): previous tier, recommended tier,
change, recommendation category, implementation speed, confidence
(0-100, probabilistic expression), urgency, tactical view, strategic
view, measurable upgrade/downgrade/invalidation conditions.

Headlines: Leader Decision, Stack Decision (they may disagree), and an
Investment Committee Decision synthesising both.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DECISION_FILENAME = "decision_history.csv"


def _utc_today():
    return datetime.now(timezone.utc).date()

# Ten recommendation categories (spec).
REC_STRONG_INCREASE = "STRONG INCREASE"
REC_INCREASE = "INCREASE"
REC_ACCUMULATE = "ACCUMULATE GRADUALLY"
REC_HOLD = "HOLD"
REC_HOLD_STOP = "HOLD / STOP ADDING"
REC_REDUCE = "REDUCE"
REC_STRONG_REDUCE = "STRONG REDUCE"
REC_AVOID = "AVOID NEW CAPITAL"
REC_WATCH_REENTRY = "WATCH FOR RE-ENTRY"
REC_CATALYST_WATCH = "CATALYST-DEPENDENT WATCH"
# Explicit non-recommendation used when persistence history is too shallow
# to support an allocation tier. This sits outside the ten recommendation
# categories because it is deliberately not an investment action.
REC_NOT_RATED = "NOT RATED"
NOT_RATED_DISPLAY = "NOT RATED - insufficient history"
REQUIRED_HISTORY_REPORTS = 4

RECOMMENDATIONS = (
    REC_STRONG_INCREASE,
    REC_INCREASE,
    REC_ACCUMULATE,
    REC_HOLD,
    REC_HOLD_STOP,
    REC_REDUCE,
    REC_STRONG_REDUCE,
    REC_AVOID,
    REC_WATCH_REENTRY,
    REC_CATALYST_WATCH,
)

# Five allocation tiers (spec). Tiers are conviction statements, not
# portfolio percentages.
TIER_NAMES = {
    0: "Avoid",
    1: "Exploratory allocation",
    2: "Normal allocation",
    3: "Overweight",
    4: "Maximum-conviction overweight",
}

# Exposure classifications (spec).
EXPOSURE_BROAD = "Broad"
EXPOSURE_SELECTIVE = "Selective"
EXPOSURE_LEADER_ONLY = "Leader-Only"
EXPOSURE_EXPLORATORY = "Exploratory"
EXPOSURE_NO_NEW = "No New Capital"

# Urgency levels (spec).
URGENCY_LOW = "Low"
URGENCY_MODERATE = "Moderate"
URGENCY_HIGH = "High"
URGENCY_IMMEDIATE = "Immediate"

# Implementation speeds (per-sleeve; not in spec's enum list, kept small
# and documented).
SPEED_IMMEDIATE = "Immediate"
SPEED_GRADUAL = "Gradual"
SPEED_PATIENT = "Patient"

# Confidence bands (spec).
CONFIDENCE_BANDS = (
    (80, "Very High"),
    (60, "High"),
    (40, "Moderate"),
    (0, "Low"),
)

STRONG_THRESHOLD = 65.0
WEAK_THRESHOLD = 45.0

LEADER_SLEEVE = "Established GLP-1 Leaders"

DECISION_COLUMNS = [
    "as_of_date",
    "sleeve",
    "readiness",
    "previous_tier",
    "recommended_tier",
    "tier_change",
    "recommendation",
    "confidence",
    "urgency",
]


def confidence_band(score: float) -> str:
    """Band a 0-100 confidence score per the spec cutoffs."""
    for cutoff, label in CONFIDENCE_BANDS:
        if score >= cutoff:
            return label
    return "Low"


def tier_name(tier: int | None) -> str:
    if tier is None:
        return "N/A"
    return f"Tier {tier} ({TIER_NAMES[tier]})"


# ---------------------------------------------------------------------------
# Decision history store (audit trail for the Phase 5 decision journal).
# ---------------------------------------------------------------------------


def _decision_path(history_dir: str | Path) -> Path:
    return Path(history_dir) / DECISION_FILENAME


def load_decision_history(history_dir: str | Path) -> pd.DataFrame:
    """Read the decision audit trail; empty frame when absent or corrupt."""
    path = _decision_path(history_dir)
    if not path.exists():
        return pd.DataFrame(columns=DECISION_COLUMNS)
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        raise RuntimeError(
            f"decision_engine: cannot read decision history {path}; "
            "refusing to continue because a later write could erase it"
        ) from exc
    required = {"as_of_date", "sleeve"}
    missing_required = sorted(required - set(frame.columns))
    if missing_required:
        raise RuntimeError(
            f"decision_engine: decision history {path} is missing required "
            f"column(s) {', '.join(missing_required)}; refusing to continue "
            "because a later write could erase it"
        )
    for column in DECISION_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["as_of_date"] = pd.to_datetime(
        frame["as_of_date"], format="%Y-%m-%d", errors="coerce"
    )
    frame = frame.dropna(subset=["as_of_date", "sleeve"])
    return frame.sort_values(["sleeve", "as_of_date"]).reset_index(drop=True)


def previous_decision(decision_history: pd.DataFrame, sleeve: str) -> dict | None:
    """Most recent recorded decision for a sleeve, or None."""
    if decision_history.empty:
        return None
    rows = decision_history[decision_history["sleeve"] == sleeve]
    if rows.empty:
        return None
    return rows.iloc[-1].to_dict()


def consecutive_exhausted(decision_history: pd.DataFrame, sleeve: str) -> int:
    """Trailing count of consecutive Exhausted readiness records."""
    if decision_history.empty:
        return 0
    rows = decision_history[decision_history["sleeve"] == sleeve]
    count = 0
    for _, row in rows.iloc[::-1].iterrows():
        if str(row.get("readiness")) == "Exhausted":
            count += 1
        else:
            break
    return count


def append_decision_history(
    history_dir: str | Path,
    cards: list[dict],
    as_of_dt,
) -> pd.DataFrame:
    """Record this report's decisions. Atomic write; upsert on (date, sleeve).

    Only call when outputs are being written — dry runs must not pollute
    the audit trail.
    """
    path = _decision_path(history_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    date_str = as_of_dt.strftime("%Y-%m-%d")
    today = pd.Timestamp(_utc_today())
    if pd.Timestamp(date_str) > today:
        raise ValueError(
            f"decision_engine: refusing to record future report date: {date_str}"
        )
    rows = []
    for card in cards:
        rows.append(
            {
                "as_of_date": date_str,
                "sleeve": card["sleeve"],
                "readiness": card["readiness"],
                "previous_tier": card["previous_tier"],
                "recommended_tier": card["recommended_tier"],
                "tier_change": card["tier_change"],
                "recommendation": card["recommendation"],
                "confidence": round(float(card["confidence"]), 1),
                "urgency": card["urgency"],
            }
        )
    existing = load_decision_history(history_dir)
    new_frame = pd.DataFrame(rows, columns=DECISION_COLUMNS)
    combined = (
        pd.concat([existing, new_frame], ignore_index=True)
        if not new_frame.empty
        else existing
    )
    if not combined.empty:
        # Normalize dates before dedup: existing rows carry datetimes while
        # incoming rows carry strings, and mixed types never compare equal.
        combined["as_of_date"] = pd.to_datetime(
            combined["as_of_date"], format="%Y-%m-%d", errors="coerce"
        )
        combined = combined.dropna(subset=["as_of_date"])
        combined = combined.drop_duplicates(subset=["as_of_date", "sleeve"], keep="last")
        combined = combined.sort_values(["sleeve", "as_of_date"]).reset_index(drop=True)
        combined["as_of_date"] = combined["as_of_date"].dt.strftime("%Y-%m-%d")
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            combined.to_csv(handle, index=False)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return load_decision_history(history_dir)


# ---------------------------------------------------------------------------
# Recommendation matrix: (readiness, opportunity) -> target tier.
# ---------------------------------------------------------------------------


def target_tier(readiness: str, opportunity: float | None) -> int | None:
    """Target allocation tier from readiness and opportunity score.

    Returns None when the evidence is genuinely inconclusive (hold at the
    previous tier) or when the sleeve cannot be scored. Exhausted is
    handled by step-down logic in the caller, not here.
    """
    if opportunity is None or (isinstance(opportunity, float) and pd.isna(opportunity)):
        return None
    opp = float(opportunity)
    if readiness == "Persistent":
        if opp >= STRONG_THRESHOLD:
            return 4
        if opp >= 55:
            return 3
        if opp >= WEAK_THRESHOLD:
            return 2
        return None  # contradictory: persistent but weak — hold, flagged
    if readiness == "Confirmed":
        if opp >= 55:
            return 3
        if opp >= WEAK_THRESHOLD:
            return 2
        return None
    if readiness == "Developing":
        if opp >= 55:
            return 2
        return 1
    if readiness == "Early Signal":
        # Weak score with one improving report: watch, no capital yet.
        return 1 if opp >= WEAK_THRESHOLD else 0
    if readiness == "Repairing":
        return 1
    # Exhausted: step-down logic in the caller. Insufficient Evidence: hold.
    return None


def _ticker_set(value: object) -> set[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return set()
    return {t.strip().upper() for t in str(value).split(",") if t.strip()}


def regulatory_override(sleeve_tickers: list[str], news_events: pd.DataFrame) -> bool:
    """True when a material Regulatory Risk event touches the sleeve."""
    if news_events is None or news_events.empty:
        return False
    sleeve_set = {t.upper() for t in sleeve_tickers}
    theme_col = "themes" if "themes" in news_events.columns else "theme"
    ticker_col = "tickers" if "tickers" in news_events.columns else "ticker"
    for _, event in news_events.iterrows():
        themes = str(event.get(theme_col) or "")
        if "Regulatory Risk" not in themes:
            continue
        material = event.get("material_event", event.get("material", True))
        if material is False:
            continue
        if _ticker_set(event.get(ticker_col)) & sleeve_set:
            return True
    return False


def severe_break_trigger(
    *,
    opportunity_change: float | None,
    readiness: str,
    readiness_changed: bool,
    breadth_collapse: bool,
    regulatory_hit: bool,
    exhausted_streak: int,
    catalyst_confirmed: bool,
) -> tuple[bool, str]:
    """Whether a two-tier move is allowed, and why.

    Negative breaks: single-report collapse, Exhausted onset with breadth
    collapse, or a regulatory hit on an already-weakening sleeve.
    Positive breaks: newly confirmed strength with a fresh material
    catalyst and breadth confirmation. Rare by design.
    """
    if opportunity_change is not None and opportunity_change <= -15:
        return True, f"opportunity score fell {opportunity_change:.1f} in one report"
    if readiness == "Exhausted" and readiness_changed and breadth_collapse:
        return True, "Exhausted onset with breadth collapse"
    if regulatory_hit and readiness in ("Exhausted",):
        return True, "regulatory hit on an exhausting sleeve"
    if exhausted_streak >= 2:
        return True, "Exhausted persisting across reports"
    if catalyst_confirmed and readiness in ("Confirmed", "Persistent") and readiness_changed:
        return True, "newly confirmed strength with material catalyst and breadth"
    return False, ""


def apply_tier_limiter(
    prev_tier: int | None,
    target_tier_value: int | None,
    severe_break: bool,
) -> int | None:
    """Normal changes are limited to one tier per report."""
    if prev_tier is None or pd.isna(prev_tier):
        return target_tier_value  # initialization: no limiter
    if target_tier_value is None:
        return int(prev_tier)  # hold
    prev = int(prev_tier)
    delta = int(target_tier_value) - prev
    max_move = 2 if severe_break else 1
    if abs(delta) <= max_move:
        return int(target_tier_value)
    return prev + max_move * (1 if delta > 0 else -1)


def recommendation_for(
    *,
    readiness: str,
    opportunity: float | None,
    prev_tier: int | None,
    new_tier: int | None,
    regulatory_hit: bool,
) -> str:
    """Map the tier decision to one of the ten recommendation categories."""
    if new_tier is None:
        return REC_HOLD
    new_tier = int(new_tier)
    if prev_tier is None or (isinstance(prev_tier, float) and pd.isna(prev_tier)):
        # First decision: categorize by the initialized tier.
        if new_tier >= 4:
            return REC_STRONG_INCREASE if readiness == "Persistent" else REC_INCREASE
        if new_tier == 3:
            return REC_INCREASE
        if new_tier == 2:
            return REC_ACCUMULATE
        if new_tier == 1:
            if readiness == "Repairing":
                return REC_ACCUMULATE
            if readiness == "Early Signal":
                return REC_CATALYST_WATCH
            return REC_ACCUMULATE
        return REC_AVOID
    delta = new_tier - int(prev_tier)
    if delta >= 2:
        return REC_STRONG_INCREASE
    if delta == 1:
        return REC_INCREASE if new_tier >= 3 else REC_ACCUMULATE
    if delta == 0:
        if regulatory_hit:
            # No tier change, but do not add into a regulatory overhang.
            return REC_HOLD_STOP if new_tier > 0 else REC_AVOID
        if readiness == "Exhausted":
            return REC_HOLD_STOP if new_tier > 0 else REC_AVOID
        if readiness == "Early Signal":
            opp = float(opportunity) if opportunity is not None else float("nan")
            if not pd.isna(opp) and opp < WEAK_THRESHOLD:
                return REC_WATCH_REENTRY
            return REC_CATALYST_WATCH
        if readiness == "Repairing":
            return REC_ACCUMULATE
        if new_tier == 0:
            return REC_AVOID
        return REC_HOLD
    if delta == -1:
        return REC_REDUCE if new_tier > 0 else REC_AVOID
    return REC_STRONG_REDUCE


def implementation_speed(recommendation: str, regulatory_hit: bool) -> str:
    if regulatory_hit or recommendation in (REC_STRONG_INCREASE, REC_STRONG_REDUCE):
        return SPEED_IMMEDIATE
    if recommendation in (REC_INCREASE, REC_REDUCE, REC_ACCUMULATE):
        return SPEED_GRADUAL
    return SPEED_PATIENT


# ---------------------------------------------------------------------------
# Confidence scoring: nine inputs, YAML weights, 0-100 probabilistic read.
# ---------------------------------------------------------------------------

DATA_QUALITY_SCORES = {"High": 1.0, "Medium": 0.6, "Low": 0.3}
CONCENTRATION_SCORES = {"broad": 1.0, "moderate": 0.6, "concentrated": 0.3}


def confidence_inputs(
    *,
    persist_row: dict,
    opp_row: dict,
    sleeve_history: pd.DataFrame,
    concentration: dict,
    market_data_quality: dict,
    news_confidence: str,
) -> dict[str, float]:
    """Nine normalized (0-1) confidence inputs from available evidence."""
    improving = int(persist_row.get("consecutive_improving") or 0)
    deteriorating = int(persist_row.get("consecutive_deteriorating") or 0)
    above_strong = int(persist_row.get("consecutive_above_strong") or 0)
    below_weak = int(persist_row.get("consecutive_below_weak") or 0)
    signal_persistence = min(max(improving, deteriorating, above_strong, below_weak) / 4.0, 1.0)

    structural = opp_row.get("structural_score")
    market_conf = opp_row.get("market_confirmation_score")
    if structural is not None and market_conf is not None and not pd.isna(structural) and not pd.isna(market_conf):
        price_fundamentals = 1.0 - min(abs(float(market_conf) - float(structural)) / 50.0, 1.0)
    else:
        price_fundamentals = 0.5

    breadth = 0.5
    if sleeve_history is not None and not sleeve_history.empty and "breadth_50dma" in sleeve_history.columns:
        sleeve_rows = sleeve_history[sleeve_history["sleeve"] == persist_row.get("sleeve")]
        if not sleeve_rows.empty:
            latest = sleeve_rows.iloc[-1].get("breadth_50dma")
            if latest is not None and not pd.isna(latest):
                breadth = float(max(0.0, min(1.0, latest)))

    data_quality = DATA_QUALITY_SCORES.get(
        str(market_data_quality.get("status", "")), 0.5
    )

    material_count = 0
    if sleeve_history is not None and not sleeve_history.empty and "material_event_count" in sleeve_history.columns:
        sleeve_rows = sleeve_history[sleeve_history["sleeve"] == persist_row.get("sleeve")]
        if not sleeve_rows.empty:
            latest = sleeve_rows.iloc[-1].get("material_event_count")
            if latest is not None and not pd.isna(latest):
                material_count = int(latest)
    catalyst_diversity = min(material_count / 5.0, 1.0)

    leadership_concentration = CONCENTRATION_SCORES.get(
        str(concentration.get("verdict", "")).lower(), 0.5
    )

    # Time-horizon agreement: tactical direction vs structural thesis direction.
    trend = str(persist_row.get("four_report_trend") or "")
    tactical = 1 if "improving" in trend else (-1 if "deteriorating" in trend else 0)
    strategic = 0
    if structural is not None and not pd.isna(structural):
        strategic = 1 if float(structural) >= 50 else -1
    if tactical == 0 or strategic == 0:
        time_horizon = 0.5
    else:
        time_horizon = 1.0 if tactical == strategic else 0.0

    conflicts = persist_row.get("conflicts") or []
    if isinstance(conflicts, str):
        conflicts = [conflicts] if conflicts else []
    conflict_degree = 0.4 if len(conflicts) > 0 else 1.0

    historical_stability = 0.5
    if sleeve_history is not None and not sleeve_history.empty and "opportunity_score" in sleeve_history.columns:
        sleeve_rows = sleeve_history[sleeve_history["sleeve"] == persist_row.get("sleeve")]
        scores = pd.to_numeric(sleeve_rows["opportunity_score"], errors="coerce").dropna()
        if len(scores) >= 2:
            historical_stability = 1.0 - min(float(scores.std(ddof=0)) / 25.0, 1.0)
        elif len(scores) == 1:
            historical_stability = 0.5

    _ = news_confidence  # reserved: news confidence feeds data_quality via market audit
    return {
        "signal_persistence": signal_persistence,
        "price_fundamentals_agreement": price_fundamentals,
        "breadth": breadth,
        "data_quality": data_quality,
        "catalyst_diversity": catalyst_diversity,
        "leadership_concentration": leadership_concentration,
        "time_horizon_agreement": time_horizon,
        "conflict_degree": conflict_degree,
        "historical_stability": historical_stability,
    }


def confidence_score(inputs: dict[str, float], weights: dict[str, float]) -> float:
    """Weighted 0-100 confidence. Weights must cover exactly the inputs."""
    missing = set(inputs) - set(weights)
    extra = set(weights) - set(inputs)
    if missing or extra:
        raise ValueError(
            f"decision_engine: confidence weight keys mismatch "
            f"(missing={sorted(missing)}, extra={sorted(extra)})"
        )
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"decision_engine: confidence weights sum to {total}, not 1.0")
    return round(sum(inputs[k] * weights[k] for k in inputs) * 100.0, 1)


# ---------------------------------------------------------------------------
# Urgency, views, conditions.
# ---------------------------------------------------------------------------


def urgency_for(
    *,
    regulatory_hit: bool,
    readiness: str,
    readiness_changed: bool,
    tier_change: int | None,
    second_derivative: str,
    streak_continuing: bool,
) -> str:
    if regulatory_hit:
        return URGENCY_IMMEDIATE
    if readiness == "Exhausted" and readiness_changed:
        return URGENCY_IMMEDIATE
    if readiness_changed:
        return URGENCY_HIGH
    if tier_change not in (None, 0) and second_derivative == "accelerating":
        return URGENCY_HIGH
    if streak_continuing:
        return URGENCY_MODERATE
    return URGENCY_LOW


def _trend_phrase(persist_row: dict) -> str:
    trend = str(persist_row.get("four_report_trend") or "insufficient")
    improving = int(persist_row.get("consecutive_improving") or 0)
    deteriorating = int(persist_row.get("consecutive_deteriorating") or 0)
    second = str(persist_row.get("second_derivative") or "")
    if improving > 0:
        phrase = f"improving for {improving} consecutive report(s)"
    elif deteriorating > 0:
        phrase = f"deteriorating for {deteriorating} consecutive report(s)"
    else:
        phrase = "no clear directional streak"
    if second in ("accelerating", "decelerating", "steady", "mixed"):
        phrase += f", momentum {second}"
    return f"{phrase} (four-report trend: {trend})"


def tactical_view(persist_row: dict, readiness: str) -> str:
    return (
        f"Next 1-3 reports: {_trend_phrase(persist_row)}. "
        f"Readiness is {readiness}."
    )


def strategic_view(opp_row: dict, readiness: str) -> str:
    structural = opp_row.get("structural_score")
    structural_txt = (
        f"{float(structural):.1f}" if structural is not None and not pd.isna(structural) else "n/a"
    )
    return (
        f"Thesis horizon: structural score {structural_txt}; "
        f"evidence maturity {readiness}."
    )


def views_agree(persist_row: dict, opp_row: dict) -> bool:
    trend = str(persist_row.get("four_report_trend") or "")
    tactical_up = "improving" in trend
    tactical_down = "deteriorating" in trend
    structural = opp_row.get("structural_score")
    if structural is None or pd.isna(structural):
        return True  # cannot judge disagreement without structural data
    strategic_up = float(structural) >= 50
    if tactical_up:
        return strategic_up
    if tactical_down:
        return not strategic_up
    return True


def upgrade_condition(
    readiness: str,
    recommended_tier: int | None,
    opportunity: float | None,
    persist_row: dict | None = None,
    history_report_count: int = 0,
) -> str:
    if recommended_tier is None:
        remaining = max(REQUIRED_HISTORY_REPORTS - history_report_count, 0)
        return (
            "Path to initial rating: complete "
            f"{remaining} additional report(s) ({history_report_count} of "
            f"{REQUIRED_HISTORY_REPORTS} recorded), then require Early Signal "
            f"readiness or better with opportunity >= {WEAK_THRESHOLD:.0f}."
        )
    if recommended_tier >= 4:
        return "Already at maximum tier - no higher upgrade tier exists."
    banked = ""
    if persist_row is not None:
        above = int(persist_row.get("consecutive_above_strong") or 0)
        improving = int(persist_row.get("consecutive_improving") or 0)
        banked = (
            f" (Now: readiness {readiness}, {above} consecutive report(s) "
            f"above 65, {improving} improving.)"
        )
    nxt = recommended_tier + 1
    if nxt >= 4:
        return (
            f"Upgrade to Tier 4: Persistent readiness with opportunity ≥ "
            f"{STRONG_THRESHOLD:.0f} for 2 consecutive reports and breadth confirmation."
            f"{banked}"
        )
    if nxt == 3:
        return (
            f"Upgrade to Tier 3: Confirmed or Persistent readiness with "
            f"opportunity ≥ 55 for 2 consecutive reports."
            f"{banked}"
        )
    if nxt == 2:
        return (
            f"Upgrade to Tier 2: Developing readiness or better with "
            f"opportunity ≥ 55, or Confirmed readiness."
            f"{banked}"
        )
    return (
        f"Upgrade to Tier 1: Early Signal or Repairing readiness with "
        f"opportunity ≥ {WEAK_THRESHOLD:.0f}, or any improving streak."
        f"{banked}"
    )


def downgrade_condition(recommended_tier: int | None) -> str:
    if recommended_tier is None:
        return "Not applicable until an initial allocation tier is established."
    if recommended_tier <= 0:
        return "Already at Tier 0 - no lower downgrade tier exists."
    return (
        f"Downgrade to Tier {recommended_tier - 1}: readiness Exhausted, "
        f"opportunity < {WEAK_THRESHOLD:.0f} for 2 consecutive reports, "
        f"or a single-report opportunity drop ≥ 15 points."
    )


def invalidation_condition(
    structural_score: float | None = None,
    *,
    is_rated: bool = True,
) -> str:
    threshold = (
        "structural thesis score < 40, or a material adverse regulatory "
        "event directly affecting core sleeve holdings"
    )
    if not is_rated:
        if structural_score is not None and structural_score < 40:
            return (
                "Not applicable until an initial rating is established; "
                f"current structural score {structural_score:.1f} already "
                "fails the <40 threshold and is flagged as a watch risk."
            )
        return f"Not applicable until an initial rating is established; monitor {threshold}."
    return threshold + "."


# ---------------------------------------------------------------------------
# Decision cards.
# ---------------------------------------------------------------------------


def _safe_float(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_decision_card(
    *,
    sleeve: str,
    sleeve_tickers: list[str],
    opp_row: dict,
    persist_row: dict,
    prev: dict | None,
    sleeve_history: pd.DataFrame,
    confirmation_state: str,
    concentration: dict,
    market_data_quality: dict,
    news_confidence: str,
    news_events: pd.DataFrame,
    confidence_weights: dict[str, float],
) -> dict:
    opportunity = _safe_float(opp_row.get("opportunity_score"))
    readiness = str(persist_row.get("readiness") or "Insufficient Evidence")
    prev_tier_raw = (prev or {}).get("recommended_tier")
    prev_tier = None if prev_tier_raw is None or pd.isna(prev_tier_raw) else int(prev_tier_raw)
    prev_readiness = str((prev or {}).get("readiness") or "")
    readiness_changed = bool(prev) and prev_readiness != readiness

    regulatory_hit = regulatory_override(sleeve_tickers, news_events)
    sleeve_rows = (
        sleeve_history[sleeve_history["sleeve"] == sleeve]
        if sleeve_history is not None
        and not sleeve_history.empty
        and "sleeve" in sleeve_history.columns
        else pd.DataFrame()
    )
    if not sleeve_rows.empty and "as_of_date" in sleeve_rows.columns:
        history_report_count = int(sleeve_rows["as_of_date"].nunique())
    else:
        history_report_count = int(len(sleeve_rows))

    # Breadth collapse: 50DMA participation falling over three reports.
    breadth_collapse = False
    if sleeve_history is not None and not sleeve_history.empty and "breadth_50dma" in sleeve_history.columns:
        rows = sleeve_history[sleeve_history["sleeve"] == sleeve]
        breadth = pd.to_numeric(rows["breadth_50dma"], errors="coerce").dropna()
        if len(breadth) >= 3:
            breadth_collapse = float(breadth.iloc[-1] - breadth.iloc[-3]) <= -0.15

    # Fresh material catalyst with breadth confirmation (positive break input).
    catalyst_confirmed = False
    if sleeve_history is not None and not sleeve_history.empty:
        rows = sleeve_history[sleeve_history["sleeve"] == sleeve]
        if "material_event_count" in rows.columns and len(rows) >= 2:
            counts = pd.to_numeric(rows["material_event_count"], errors="coerce").dropna()
            catalyst_up = (
                len(counts) >= 2 and int(counts.iloc[-1]) > int(counts.iloc[-2])
            )
        else:
            catalyst_up = False
        breadth = pd.to_numeric(rows["breadth_50dma"], errors="coerce").dropna() if "breadth_50dma" in rows.columns else pd.Series(dtype=float)
        breadth_ok = (
            len(breadth) >= 3
            and float(breadth.iloc[-1]) >= 0.5
            and float(breadth.iloc[-1] - breadth.iloc[-3]) > 0
        )
        catalyst_confirmed = catalyst_up and breadth_ok

    score_change = _safe_float(persist_row.get("score_change"))

    # Exhausted streak from prior decisions (for STRONG REDUCE persistence).
    # Note: computed by the caller via consecutive_exhausted; passed through
    # the card pipeline as exhausted_streak below.
    exhausted_streak = int(persist_row.get("_exhausted_streak") or 0)

    severe_break, break_reason = severe_break_trigger(
        opportunity_change=score_change,
        readiness=readiness,
        readiness_changed=readiness_changed,
        breadth_collapse=breadth_collapse,
        regulatory_hit=regulatory_hit,
        exhausted_streak=exhausted_streak,
        catalyst_confirmed=catalyst_confirmed,
    )

    if opportunity is None:
        # Cannot score — hold at previous, no fabrication.
        new_tier = prev_tier
        recommendation = REC_HOLD
    elif readiness == "Exhausted":
        # Exhausted classification already requires three reports of
        # catalyst history — that is the persistence the STRONG REDUCE
        # guardrail demands.
        step = 2 if severe_break else 1
        if prev_tier is None:
            new_tier = 1  # initialize weak: avoid anchoring high on exhaustion
            recommendation = REC_REDUCE
        else:
            new_tier = max(0, prev_tier - step)
            recommendation = REC_STRONG_REDUCE if step == 2 else REC_REDUCE
        if new_tier == 0:
            recommendation = REC_AVOID
    else:
        tgt = target_tier(readiness, opportunity)
        if regulatory_hit and (prev_tier is not None or tgt is not None):
            # Risk cap: no more than exploratory while the event is
            # unresolved. Never creates a tier from nothing.
            tgt = 1 if tgt is None else min(tgt, 1)
            if prev_tier is not None and prev_tier > tgt:
                # Rapid derisk, but within the spec's two-tier cap.
                severe_break = True
                break_reason = (
                    (break_reason + "; " if break_reason else "")
                    + "regulatory override — rapid derisk"
                )
        new_tier = apply_tier_limiter(prev_tier, tgt, severe_break)
        recommendation = recommendation_for(
            readiness=readiness,
            opportunity=opportunity,
            prev_tier=prev_tier,
            new_tier=new_tier,
            regulatory_hit=regulatory_hit,
        )

    is_unrated = new_tier is None and prev_tier is None
    if is_unrated:
        recommendation = REC_NOT_RATED

    tier_change = (
        None
        if new_tier is None or prev_tier is None
        else int(new_tier) - int(prev_tier)
    )

    inputs = confidence_inputs(
        persist_row=persist_row,
        opp_row=opp_row,
        sleeve_history=sleeve_history,
        concentration=concentration,
        market_data_quality=market_data_quality,
        news_confidence=news_confidence,
    )
    model_input_confidence = confidence_score(inputs, confidence_weights)
    confidence = model_input_confidence
    if regulatory_hit:
        confidence = max(0.0, confidence - 20.0)

    # Expectations risk tempers confidence: priced-for-perfection is fragile.
    expectations_risk = _safe_float(opp_row.get("expectations_risk_score"))
    if expectations_risk is not None and expectations_risk >= 70:
        confidence = max(0.0, confidence - 10.0)

    # A high-quality cross-sectional snapshot is not the same thing as a
    # high-confidence allocation decision. Cold-start recommendations stay
    # explicitly Low confidence until persistence history can rate them.
    if is_unrated:
        confidence = min(confidence, 39.0)

    improving = int(persist_row.get("consecutive_improving") or 0)
    deteriorating = int(persist_row.get("consecutive_deteriorating") or 0)
    streak_continuing = (improving >= 2 or deteriorating >= 2) and not readiness_changed
    urgency = urgency_for(
        regulatory_hit=regulatory_hit,
        readiness=readiness,
        readiness_changed=readiness_changed,
        tier_change=tier_change,
        second_derivative=str(persist_row.get("second_derivative") or ""),
        streak_continuing=streak_continuing,
    )

    tactical = tactical_view(persist_row, readiness)
    strategic = strategic_view(opp_row, readiness)
    agree = None if is_unrated else views_agree(persist_row, opp_row)

    recognition_gap = str(opp_row.get("recognition_gap") or "")

    rationale_bits = [
        f"readiness {readiness}",
        f"opportunity {opportunity:.1f}" if opportunity is not None else "opportunity n/a",
    ]
    if prev_tier is not None and new_tier is not None and tier_change not in (None, 0):
        rationale_bits.append(f"tier {prev_tier} → {new_tier}")
    if severe_break:
        rationale_bits.append(f"severe break: {break_reason}")
    if regulatory_hit:
        rationale_bits.append("regulatory override active")
    if recognition_gap and recognition_gap.lower() != "none":
        rationale_bits.append(f"recognition gap: {recognition_gap}")

    structural_score = _safe_float(opp_row.get("structural_score"))
    structural_invalidation_breached = bool(
        structural_score is not None and structural_score < 40
    )
    invalidation_breached = structural_invalidation_breached or regulatory_hit

    return {
        "sleeve": sleeve,
        "required": bool(opp_row.get("required", True)),
        "opportunity_score": opportunity,
        "readiness": readiness,
        "previous_tier": prev_tier,
        "recommended_tier": new_tier,
        "tier_change": tier_change,
        "recommendation": recommendation,
        "recommendation_display": NOT_RATED_DISPLAY if is_unrated else recommendation,
        "is_rated": not is_unrated,
        "history_report_count": history_report_count,
        "required_history_reports": REQUIRED_HISTORY_REPORTS,
        "implementation_speed": implementation_speed(recommendation, regulatory_hit),
        "confidence": confidence,
        "confidence_band": confidence_band(confidence),
        "model_input_confidence": model_input_confidence,
        "model_input_confidence_band": confidence_band(model_input_confidence),
        "urgency": urgency,
        "tactical_view": tactical,
        "strategic_view": strategic,
        "views_agree": agree,
        "recognition_gap": recognition_gap,
        "upgrade_condition": upgrade_condition(
            readiness,
            new_tier,
            opportunity,
            persist_row,
            history_report_count,
        ),
        "downgrade_condition": downgrade_condition(new_tier),
        "invalidation_condition": invalidation_condition(
            structural_score,
            is_rated=not is_unrated,
        ),
        "invalidation_breached": invalidation_breached,
        "structural_invalidation_breached": structural_invalidation_breached,
        "structural_score": structural_score,
        "regulatory_override": regulatory_hit,
        "severe_break": severe_break,
        "break_reason": break_reason,
        "confidence_inputs": inputs,
        "rationale": "; ".join(rationale_bits),
        "confirmation_state": confirmation_state,
    }


def build_decision_cards(
    *,
    opportunity_ranking: pd.DataFrame,
    persistence_table: pd.DataFrame,
    sleeve_history: pd.DataFrame,
    decision_history: pd.DataFrame,
    sleeves: list,
    confirmation_state: str,
    concentration: dict,
    market_data_quality: dict,
    news_confidence: str,
    news_events: pd.DataFrame,
    confidence_weights: dict[str, float],
) -> list[dict]:
    """One decision card per sleeve in opportunity-rank order."""
    opp_by_sleeve = {}
    if opportunity_ranking is not None and not opportunity_ranking.empty:
        for _, row in opportunity_ranking.iterrows():
            opp_by_sleeve[str(row.get("sleeve"))] = row.to_dict()
    persist_by_sleeve = {}
    if persistence_table is not None and not persistence_table.empty:
        for _, row in persistence_table.iterrows():
            d = row.to_dict()
            d["_exhausted_streak"] = consecutive_exhausted(decision_history, str(row.get("sleeve")))
            persist_by_sleeve[str(row.get("sleeve"))] = d
    tickers_by_sleeve = {s.name: list(s.tickers) for s in sleeves}

    order = (
        opportunity_ranking["sleeve"].astype(str).tolist()
        if opportunity_ranking is not None and not opportunity_ranking.empty
        else [s.name for s in sleeves]
    )
    cards = []
    for name in order:
        opp_row = opp_by_sleeve.get(name, {"sleeve": name, "required": True})
        persist_row = persist_by_sleeve.get(name, {"sleeve": name, "readiness": "Insufficient Evidence"})
        cards.append(
            build_decision_card(
                sleeve=name,
                sleeve_tickers=tickers_by_sleeve.get(name, []),
                opp_row=opp_row,
                persist_row=persist_row,
                prev=previous_decision(decision_history, name),
                sleeve_history=sleeve_history,
                confirmation_state=confirmation_state,
                concentration=concentration,
                market_data_quality=market_data_quality,
                news_confidence=news_confidence,
                news_events=news_events,
                confidence_weights=confidence_weights,
            )
        )
    return cards


# ---------------------------------------------------------------------------
# Headline decisions: Leader, Stack, Exposure, Committee.
# ---------------------------------------------------------------------------


def build_leader_decision(cards: list[dict]) -> dict:
    """Headline decision for the Established GLP-1 Leaders sleeve."""
    card = next((c for c in cards if c["sleeve"] == LEADER_SLEEVE), None)
    if card is None:
        return {
            "sleeve": LEADER_SLEEVE,
            "recommendation": REC_NOT_RATED,
            "tier": None,
            "confidence": 0.0,
            "direction": "not rated",
            "is_rated": False,
            "headline": f"{LEADER_SLEEVE}: {NOT_RATED_DISPLAY}.",
        }
    if not card.get("is_rated", card.get("recommended_tier") is not None):
        count = int(card.get("history_report_count") or 0)
        required = int(card.get("required_history_reports") or REQUIRED_HISTORY_REPORTS)
        return {
            "sleeve": LEADER_SLEEVE,
            "recommendation": REC_NOT_RATED,
            "tier": None,
            "confidence": card["confidence"],
            "direction": "not rated",
            "is_rated": False,
            "headline": (
                f"{LEADER_SLEEVE}: {NOT_RATED_DISPLAY} "
                f"({count} of {required} required reports)."
            ),
        }
    direction = (
        "constructive"
        if card["recommendation"] in (REC_STRONG_INCREASE, REC_INCREASE, REC_ACCUMULATE)
        else "defensive"
        if card["recommendation"] in (REC_REDUCE, REC_STRONG_REDUCE, REC_AVOID)
        else "neutral"
    )
    return {
        "sleeve": LEADER_SLEEVE,
        "recommendation": card["recommendation"],
        "tier": card["recommended_tier"],
        "confidence": card["confidence"],
        "direction": direction,
        "is_rated": True,
        "headline": (
            f"{LEADER_SLEEVE}: {card['recommendation']} "
            f"({tier_name(card['recommended_tier'])}, "
            f"confidence {card['confidence']:.0f} {card['confidence_band']}). "
            f"{card['rationale']}."
        ),
    }


def classify_exposure(
    *,
    confirmation_state: str,
    concentration: dict,
    cards: list[dict],
) -> str:
    """Preferred stack implementation: Broad / Selective / Leader-Only /
    Exploratory / No New Capital. Precedence-ordered."""
    if not cards:
        return EXPOSURE_EXPLORATORY  # no evidence — not a defensive call
    required = [c for c in cards if c.get("required")]
    opps = [c["opportunity_score"] for c in required if c["opportunity_score"] is not None]
    median_opp = sorted(opps)[len(opps) // 2] if opps else None
    exhausted = sum(1 for c in required if c["readiness"] == "Exhausted")

    if (median_opp is not None and median_opp < WEAK_THRESHOLD) or exhausted >= 2:
        return EXPOSURE_NO_NEW
    if confirmation_state == "Leader-Dependent Confirming":
        return EXPOSURE_LEADER_ONLY
    breadth = concentration.get("pct_above_50dma")
    if confirmation_state == "Broadly Confirming" and breadth is not None and float(breadth) >= 0.5:
        return EXPOSURE_BROAD
    if confirmation_state == "Selectively Confirming":
        return EXPOSURE_SELECTIVE
    return EXPOSURE_EXPLORATORY


def build_stack_decision(
    cards: list[dict],
    exposure: str,
    flywheel_score: float | None,
) -> dict:
    """Headline decision for the broad health stack."""
    required = [c for c in cards if c.get("required")]
    tiers = [c["recommended_tier"] for c in required if c["recommended_tier"] is not None]
    median_tier = sorted(tiers)[len(tiers) // 2] if tiers else None
    increases = sum(
        1 for c in required if c["recommendation"] in (REC_STRONG_INCREASE, REC_INCREASE, REC_ACCUMULATE)
    )
    decreases = sum(
        1 for c in required if c["recommendation"] in (REC_REDUCE, REC_STRONG_REDUCE, REC_AVOID)
    )
    all_unrated = bool(required) and all(
        not c.get("is_rated", c.get("recommended_tier") is not None)
        for c in required
    )
    if exposure == EXPOSURE_NO_NEW:
        stance = "defensive"
    elif increases > decreases:
        stance = "constructive"
    elif decreases > increases:
        stance = "defensive"
    else:
        stance = "neutral"
    fly_txt = f"{flywheel_score:.1f}" if flywheel_score is not None else "n/a"
    if all_unrated:
        stance = "not rated"
        headline = (
            f"Provisional {exposure.lower()} signal; allocation decision deferred "
            f"(flywheel {fly_txt}). Constructive sleeves: N/A; defensive sleeves: "
            "N/A; median sleeve tier: N/A."
        )
    else:
        headline = (
            f"{exposure} exposure (flywheel {fly_txt}). "
            f"{increases} sleeve(s) constructive, {decreases} defensive. "
            f"Median sleeve tier: {tier_name(median_tier)}."
        )
    return {
        "exposure": exposure,
        "median_tier": median_tier,
        "stance": stance,
        "constructive_count": None if all_unrated else increases,
        "defensive_count": None if all_unrated else decreases,
        "provisional": all_unrated,
        "headline": headline,
    }


def leaders_stack_agree(leader: dict, stack: dict) -> bool | None:
    """Do the Leader and Stack decisions point the same way?"""
    if not leader.get("is_rated", leader.get("tier") is not None) or stack.get("provisional"):
        return None
    leader_dir = leader.get("direction", "neutral")
    stack_stance = stack.get("stance", "neutral")
    exposure = stack.get("exposure", "")
    if leader_dir == "constructive":
        return stack_stance == "constructive" or exposure in (EXPOSURE_BROAD, EXPOSURE_LEADER_ONLY)
    if leader_dir == "defensive":
        return stack_stance == "defensive" or exposure == EXPOSURE_NO_NEW
    return stack_stance == "neutral"


def build_committee_decision(
    leader: dict,
    stack: dict,
    cards: list[dict],
) -> str:
    """Section 1: one-paragraph Investment Committee Decision."""
    agree = leaders_stack_agree(leader, stack)
    required = [c for c in cards if c.get("required")]
    all_unrated = bool(required) and all(
        not c.get("is_rated", c.get("recommended_tier") is not None)
        for c in required
    )
    if all_unrated:
        ranked = [c for c in required if c.get("opportunity_score") is not None]
        strongest = max(ranked, key=lambda c: c["opportunity_score"], default=None)
        weakest = min(ranked, key=lambda c: c["opportunity_score"], default=None)
        count = min(
            (int(c.get("history_report_count") or 0) for c in required),
            default=0,
        )
        remaining = max(REQUIRED_HISTORY_REPORTS - count, 0)
        evidence = ""
        if strongest and weakest:
            evidence = (
                f" Cross-sectional evidence provisionally favors {strongest['sleeve']}, "
                f"while {weakest['sleeve']} is weakest."
            )
        return (
            "Current conclusion: No formal sleeve allocations yet because "
            f"persistence history contains {count} of {REQUIRED_HISTORY_REPORTS} "
            f"required reports.{evidence} Maintain a selective watchlist and "
            f"reassess after {remaining} additional report(s) or a material catalyst."
        )
    top = max(
        (c for c in cards if c["recommended_tier"] is not None),
        key=lambda c: (c["recommended_tier"], c["confidence"]),
        default=None,
    )
    lines = [
        f"Exposure: {stack['exposure']}.",
        f"Leader: {leader['recommendation']} ({tier_name(leader['tier'])}).",
        f"Stack: {stack['headline']}",
    ]
    if agree is False:
        lines.append(
            "The Leader and Stack decisions disagree — size the leader "
            "independently of broad-stack exposure."
        )
    if top is not None:
        lines.append(
            f"Highest conviction: {top['sleeve']} — {top['recommendation']} "
            f"({tier_name(top['recommended_tier'])}, confidence "
            f"{top['confidence']:.0f} {top['confidence_band']})."
        )
    immediate = [c["sleeve"] for c in cards if c["urgency"] == URGENCY_IMMEDIATE]
    if immediate:
        lines.append(f"Immediate attention: {', '.join(immediate)}.")
    return " ".join(lines)


def build_decision_risks(cards: list[dict], leader: dict, stack: dict) -> list[str]:
    """Section 7: decision risks as concrete bullets, no vague language."""
    risks: list[str] = []
    agreement = leaders_stack_agree(leader, stack)
    if agreement is False:
        risks.append(
            f"Leader vs stack disagreement: leader is {leader['direction']} "
            f"while the stack reads {stack['stance']} ({stack['exposure']}). "
            "A single-sleeve call must not override stack-level exposure."
        )
    required = [c for c in cards if c.get("required")]
    if required and all(
        not c.get("is_rated", c.get("recommended_tier") is not None)
        for c in required
    ):
        count = min((int(c.get("history_report_count") or 0) for c in required), default=0)
        risks.append(
            "Decision maturity risk: every required sleeve is unrated because "
            f"persistence history contains only {count} of {REQUIRED_HISTORY_REPORTS} "
            "required reports; cross-sectional signals are provisional."
        )
    for card in cards:
        opp = card.get("opportunity_score")
        if card["readiness"] == "Exhausted":
            risks.append(
                f"{card['sleeve']}: Exhausted — strong score "
                f"({opp:.1f}) with worsening catalysts and narrowing breadth; "
                "further deterioration forces another tier cut."
            )
        if card["regulatory_override"]:
            risks.append(
                f"{card['sleeve']}: material Regulatory Risk event in the "
                "current window — tier increases blocked until it resolves."
            )
        if card.get("structural_invalidation_breached") and not card.get("is_rated", True):
            structural = card.get("structural_score")
            structural_text = f"{structural:.1f}" if structural is not None else "n/a"
            risks.append(
                f"{card['sleeve']}: current structural score {structural_text} "
                "is below the <40 invalidation threshold. No thesis can be "
                "formally invalidated before an initial rating, so this remains "
                "an explicit watch risk."
            )
        elif card.get("structural_invalidation_breached"):
            structural = card.get("structural_score")
            structural_text = f"{structural:.1f}" if structural is not None else "n/a"
            risks.append(
                f"{card['sleeve']}: active thesis-invalidation condition - "
                f"structural score {structural_text} is below 40."
            )
        gap = str(card.get("recognition_gap") or "")
        if gap and gap.lower() not in ("none", ""):
            risks.append(
                f"{card['sleeve']}: recognition gap ({gap}) — the market "
                "may not yet price what the scores see, in either direction."
            )
    return risks
