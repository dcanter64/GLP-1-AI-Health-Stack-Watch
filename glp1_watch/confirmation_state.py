"""Phase 1: confirmation-state classification.

The classifier maps a fixed set of inputs to one of eight confirmation
states through a precedence-ordered rule table: the first matching rule wins.
Rules are deliberately simple and deterministic so every state is reachable
in tests and every classification is explainable in the report.

States:
    Broadly Confirming, Selectively Confirming, Leader-Dependent, Fragmenting,
    Early Repair, Deteriorating, Failing, Insufficient Evidence

Precedence notes:
- "Broadly Confirming" additionally requires the leadership-concentration
  verdict to be "broad", so concentrated single-name strength can never
  masquerade as broad health (it falls through to Leader-Dependent or
  Selectively Confirming instead).
- "Early Repair" is shadowed by "Selectively Confirming": it is reachable
  only when 2 or fewer sleeves confirm.
- Only "Low" market-data quality (not "Partial") triggers Insufficient
  Evidence, alongside core coverage below 50%.
"""

from __future__ import annotations

from collections.abc import Callable

STATE_BROADLY_CONFIRMING = "Broadly Confirming"
STATE_SELECTIVELY_CONFIRMING = "Selectively Confirming"
STATE_LEADER_DEPENDENT = "Leader-Dependent"
STATE_FRAGMENTING = "Fragmenting"
STATE_EARLY_REPAIR = "Early Repair"
STATE_DETERIORATING = "Deteriorating"
STATE_FAILING = "Failing"
STATE_INSUFFICIENT_EVIDENCE = "Insufficient Evidence"

ALL_STATES = (
    STATE_BROADLY_CONFIRMING,
    STATE_SELECTIVELY_CONFIRMING,
    STATE_LEADER_DEPENDENT,
    STATE_FRAGMENTING,
    STATE_EARLY_REPAIR,
    STATE_DETERIORATING,
    STATE_FAILING,
    STATE_INSUFFICIENT_EVIDENCE,
)


def _rule_table() -> list[tuple[str, Callable[[dict], bool], str]]:
    """Ordered (state, predicate, reason) rules. First match wins."""
    return [
        (
            STATE_INSUFFICIENT_EVIDENCE,
            lambda c: c["market_data_quality"] == "Low" or c["core_coverage"] < 0.5,
            "market data quality is Low or fewer than half of core names have data",
        ),
        (
            STATE_BROADLY_CONFIRMING,
            lambda c: c["overall_score"] >= 70
            and c["confirming_count"] >= 5
            and c["breadth_50dma"] >= 0.6
            and c["concentration_verdict"] == "broad",
            "score >= 70 with 5+ confirming sleeves, strong 50DMA participation, "
            "and broadly distributed gains",
        ),
        (
            STATE_LEADER_DEPENDENT,
            lambda c: c["concentration_verdict"] == "leader-dependent"
            and c["leader_status"] == "confirming",
            "evidence concentrates in the leader sleeve while the stack lags",
        ),
        (
            STATE_SELECTIVELY_CONFIRMING,
            lambda c: c["confirming_count"] >= 3,
            "3+ sleeves confirming without broad participation",
        ),
        (
            STATE_FAILING,
            lambda c: c["overall_score"] < 30 and c["deteriorating_count"] >= 5,
            "score < 30 with 5+ deteriorating sleeves",
        ),
        (
            STATE_DETERIORATING,
            lambda c: c["deteriorating_count"] >= 4,
            "4+ sleeves deteriorating",
        ),
        (
            STATE_EARLY_REPAIR,
            lambda c: c["overall_score"] >= 40
            and c["deteriorating_count"] == 0
            and c["breadth_50dma"] >= 0.5,
            "no deteriorating sleeves with score >= 40 and rebuilding participation",
        ),
        (
            STATE_FRAGMENTING,
            lambda c: True,
            "sleeves disagree: no rule above matched",
        ),
    ]


def classify_confirmation_state(
    *,
    overall_score: float,
    confirming_count: int,
    deteriorating_count: int,
    breadth_50dma: float,
    concentration_verdict: str,
    leader_status: str,
    market_data_quality: str,
    core_coverage: float,
) -> dict[str, str]:
    """Classify into one confirmation state.

    Returns ``{"state": ..., "reason": ...}``. All inputs are plain values so
    the classifier stays free of DataFrame plumbing and trivially testable.
    """
    context = {
        "overall_score": float(overall_score),
        "confirming_count": int(confirming_count),
        "deteriorating_count": int(deteriorating_count),
        "breadth_50dma": float(breadth_50dma),
        "concentration_verdict": str(concentration_verdict),
        "leader_status": str(leader_status),
        "market_data_quality": str(market_data_quality),
        "core_coverage": float(core_coverage),
    }
    for state, predicate, reason in _rule_table():
        if predicate(context):
            return {"state": state, "reason": reason}
    # The final rule always matches; this is unreachable by construction.
    return {"state": STATE_FRAGMENTING, "reason": "no rule matched"}


def assess_leader(leader_status: str, lly_ai_trade_score: float | None) -> str:
    """Separate leader assessment: is the established leader confirming?

    Returns one of "Confirming", "Mixed", "Deteriorating", "Unknown".
    """
    if leader_status == "insufficient data" or lly_ai_trade_score is None:
        return "Unknown"
    score = float(lly_ai_trade_score)
    if leader_status == "confirming" and score >= 60:
        return "Confirming"
    if leader_status == "deteriorating" or score < 40:
        return "Deteriorating"
    return "Mixed"


def assess_stack(state: str) -> str:
    """Separate stack assessment derived from the confirmation state."""
    mapping = {
        STATE_BROADLY_CONFIRMING: "Broadly confirming",
        STATE_SELECTIVELY_CONFIRMING: "Selectively confirming",
        STATE_LEADER_DEPENDENT: "Narrow - dependent on leaders",
        STATE_FRAGMENTING: "Fragmented",
        STATE_EARLY_REPAIR: "Early repair",
        STATE_DETERIORATING: "Deteriorating",
        STATE_FAILING: "Failing",
        STATE_INSUFFICIENT_EVIDENCE: "Unknown",
    }
    return mapping.get(state, "Unknown")


def build_contradiction(leader_assessment: str, stack_assessment: str) -> str:
    """Name the main tension between leader and stack, if any."""
    if leader_assessment == "Unknown" or stack_assessment == "Unknown":
        return "Leader/stack comparison unavailable: insufficient evidence on one side."
    if leader_assessment == "Confirming" and stack_assessment == "Narrow - dependent on leaders":
        return (
            "Leader is confirming and the stack is narrow: strength is concentrated in "
            "the leader and breadth has not confirmed — fragile if leadership falters."
        )
    if leader_assessment == "Confirming" and stack_assessment in {
        "Fragmented",
        "Deteriorating",
        "Failing",
    }:
        return (
            f"Leader is {leader_assessment.lower()} while the broad stack reads "
            f"'{stack_assessment.lower()}': leadership is not carrying the stack."
        )
    if leader_assessment == "Deteriorating" and stack_assessment in {
        "Broadly confirming",
        "Selectively confirming",
    }:
        return (
            "Leader is deteriorating while the stack confirms: breadth exists "
            "without its historical leader."
        )
    if leader_assessment == stack_assessment or (
        leader_assessment == "Confirming" and stack_assessment == "Broadly confirming"
    ):
        return "No material contradiction: leader and stack assessments agree."
    return (
        f"Leader reads '{leader_assessment.lower()}' against a stack reading "
        f"'{stack_assessment.lower()}': partial disagreement worth watching."
    )
