"""Phase 5: position-level decisions.

Ticker-level position cards derived from sleeve decision cards (Phase 4)
modulated by ticker technicals. Analytical only: no trade execution, no
personalized sizing.

Key rules (operator-approved):
- A ticker call may be more defensive than its sleeve, never more
  aggressive. Strong price action alone never raises a ticker above its
  sleeve tier; it is recognized through position status, confidence,
  and reason instead.
- Ticker tier = sleeve tier, minus 1 when the ticker is both below its
  200DMA and underperforming its sleeve, floored at Tier 0.
- Sleeve-relative strength = ticker return minus the equal-weight sleeve
  return over the same horizon.
- Ticker calls cannot override the broad-stack exposure decision.
- Missing technical or thesis data -> "Insufficient Evidence / Not Rated",
  never forced into one of the 13 investment statuses.
"""

from __future__ import annotations

import pandas as pd

from .decision_engine import (
    REC_ACCUMULATE,
    REC_AVOID,
    REC_CATALYST_WATCH,
    REC_HOLD,
    REC_HOLD_STOP,
    REC_INCREASE,
    REC_REDUCE,
    REC_STRONG_INCREASE,
    REC_STRONG_REDUCE,
    REC_WATCH_REENTRY,
    LEADER_SLEEVE,
    URGENCY_HIGH,
    URGENCY_IMMEDIATE,
    confidence_band,
)

METHODOLOGY_VERSION = "phase5-v1"

# Position statuses (spec). Precedence-ordered: defensive states and hard
# invalidations first, constructive states last. INSUFFICIENT_STATUS sits
# outside the 13 as the explicit not-rated outcome.
INSUFFICIENT_STATUS = "Insufficient Evidence / Not Rated"
STATUS_EXIT = "Exit candidate"
STATUS_AVOID = "Avoid new capital"
STATUS_THESIS_PRICE_BROKEN = "Thesis intact / price broken"
STATUS_PRICE_THESIS_WEAK = "Price intact / thesis weakening"
STATUS_ROTATION_SOURCE = "Rotation source"
STATUS_EXPECTATIONS_RISK = "Expectations-risk leader"
STATUS_RECOGNITION_GAP = "Recognition gap"
STATUS_RECOVERY = "Recovery candidate"
STATUS_CATALYST_DEP = "Catalyst-dependent"
STATUS_EARLY_ACCUM = "Early accumulation"
STATUS_EMERGING_LEADER = "Emerging leader"
STATUS_TACTICAL_LEADER = "Tactical leader"
STATUS_CORE_LEADER = "Core leader"

INVESTMENT_STATUSES = (
    STATUS_EXIT,
    STATUS_AVOID,
    STATUS_THESIS_PRICE_BROKEN,
    STATUS_PRICE_THESIS_WEAK,
    STATUS_ROTATION_SOURCE,
    STATUS_EXPECTATIONS_RISK,
    STATUS_RECOGNITION_GAP,
    STATUS_RECOVERY,
    STATUS_CATALYST_DEP,
    STATUS_EARLY_ACCUM,
    STATUS_EMERGING_LEADER,
    STATUS_TACTICAL_LEADER,
    STATUS_CORE_LEADER,
)

# Aggressiveness ordering, most aggressive first. A ticker recommendation
# may only move down this list relative to its sleeve (more defensive),
# never up.
AGGRESSIVENESS = (
    REC_STRONG_INCREASE,
    REC_INCREASE,
    REC_ACCUMULATE,
    REC_HOLD,
    REC_HOLD_STOP,
    REC_CATALYST_WATCH,
    REC_WATCH_REENTRY,
    REC_REDUCE,
    REC_AVOID,
    REC_STRONG_REDUCE,
)

DEFENSIVE_STATUSES = frozenset(
    {
        STATUS_EXIT,
        STATUS_AVOID,
        STATUS_THESIS_PRICE_BROKEN,
        STATUS_PRICE_THESIS_WEAK,
        STATUS_ROTATION_SOURCE,
    }
)


def _safe_float(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_bool(value: object) -> bool | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return bool(value)


def sleeve_relative_strength(
    ticker_return: float | None,
    sleeve_returns: list[float | None],
) -> float | None:
    """Ticker return minus the equal-weight sleeve return, same horizon."""
    if ticker_return is None:
        return None
    clean = [r for r in sleeve_returns if r is not None]
    if not clean:
        return None
    return float(ticker_return) - sum(clean) / len(clean)


def price_trend(perf_row: dict) -> str:
    """Current price trend from DMA position and 1M pace."""
    above_50 = _safe_bool(perf_row.get("above_50dma"))
    above_200 = _safe_bool(perf_row.get("above_200dma"))
    ret_1m = _safe_float(perf_row.get("return_1m"))
    if above_50 is None or above_200 is None:
        return "unknown"
    if above_50 and above_200:
        return "Uptrend" if (ret_1m or 0) >= 0 else "Uptrend, fading pace"
    if above_50:
        return "Recovering"
    if above_200:
        return "Weakening"
    return "Downtrend"


def _technicals(perf_row: dict, rs_vs_sleeve: float | None) -> dict:
    above_200 = _safe_bool(perf_row.get("above_200dma"))
    above_50 = _safe_bool(perf_row.get("above_50dma"))
    ret_3m = _safe_float(perf_row.get("return_3m"))
    strong = (
        above_200 is True
        and rs_vs_sleeve is not None
        and rs_vs_sleeve > 0
        and (ret_3m or 0) > 0
    )
    broken = (
        above_200 is False
        and rs_vs_sleeve is not None
        and rs_vs_sleeve < 0
    )
    return {"above_200": above_200, "above_50": above_50, "strong": strong, "broken": broken}


def classify_position_status(
    *,
    perf_row: dict,
    sleeve_card: dict | None,
    rs_vs_sleeve: float | None,
    sleeve_rank_by_rs: int | None,
) -> str:
    """Precedence-ordered position status classifier.

    Returns one of the 13 investment statuses, or the explicit
    Insufficient Evidence / Not Rated outcome when data is missing.
    """
    # Not-rated gate: never force a recommendation without data.
    required_tech = (
        _safe_bool(perf_row.get("above_50dma")),
        _safe_bool(perf_row.get("above_200dma")),
        _safe_float(perf_row.get("return_3m")),
    )
    if any(v is None for v in required_tech) or rs_vs_sleeve is None:
        return INSUFFICIENT_STATUS
    if sleeve_card is None:
        return INSUFFICIENT_STATUS
    sleeve_tier = sleeve_card.get("recommended_tier")
    if sleeve_tier is None or (isinstance(sleeve_tier, float) and pd.isna(sleeve_tier)):
        return INSUFFICIENT_STATUS
    sleeve_tier = int(sleeve_tier)

    tech = _technicals(perf_row, rs_vs_sleeve)
    rec = str(sleeve_card.get("recommendation") or "")
    readiness = str(sleeve_card.get("readiness") or "")
    expectations_risk = _safe_float(sleeve_card.get("expectations_risk"))
    recognition_gap = str(sleeve_card.get("recognition_gap") or "")
    is_leader_sleeve = str(sleeve_card.get("sleeve") or "") == LEADER_SLEEVE
    ret_1m = _safe_float(perf_row.get("return_1m")) or 0.0
    rs_vs_spy = _safe_float(perf_row.get("rs_vs_spy"))

    # Hard defensive states first.
    if rec == REC_STRONG_REDUCE or (sleeve_tier == 0 and tech["broken"]):
        return STATUS_EXIT
    if sleeve_tier == 0 or rec == REC_AVOID:
        return STATUS_AVOID
    if sleeve_tier >= 2 and tech["above_200"] is False:
        return STATUS_THESIS_PRICE_BROKEN
    if sleeve_tier <= 1 and tech["above_200"] is True and (rs_vs_spy or 0) > 0:
        return STATUS_PRICE_THESIS_WEAK
    if readiness == "Exhausted" and tech["above_200"] is True:
        return STATUS_ROTATION_SOURCE
    if (
        expectations_risk is not None
        and expectations_risk >= 70
        and sleeve_rank_by_rs is not None
        and sleeve_rank_by_rs <= 2
    ):
        return STATUS_EXPECTATIONS_RISK
    if recognition_gap and recognition_gap.lower() not in ("none", "") and tech["strong"]:
        return STATUS_RECOGNITION_GAP
    if readiness == "Repairing" and tech["above_50"] is True:
        return STATUS_RECOVERY
    if rec == REC_CATALYST_WATCH:
        return STATUS_CATALYST_DEP
    if readiness in ("Developing", "Early Signal", "Repairing") and ret_1m > 0:
        return STATUS_EARLY_ACCUM
    if not is_leader_sleeve and sleeve_tier >= 2:
        return STATUS_EMERGING_LEADER
    if is_leader_sleeve:
        return STATUS_CORE_LEADER if sleeve_tier >= 3 else STATUS_TACTICAL_LEADER
    # Posture-based default for anything not otherwise characterized.
    if sleeve_tier == 1:
        return STATUS_EARLY_ACCUM
    return STATUS_AVOID


def _step_more_defensive(recommendation: str) -> str:
    try:
        idx = AGGRESSIVENESS.index(recommendation)
    except ValueError:
        return REC_HOLD
    return AGGRESSIVENESS[min(idx + 1, len(AGGRESSIVENESS) - 1)]


def build_position_card(
    *,
    ticker: str,
    perf_row: dict,
    sleeve_card: dict | None,
    sleeve_tickers: list[str],
    sleeve_returns_3m: dict[str, float | None],
    ticker_material_events: int,
    news_events_for_ticker: int = 0,
) -> dict:
    """One position card for a ticker.

    The ticker recommendation starts at the sleeve recommendation and may
    step more defensive on broken technicals — never more aggressive.
    """
    _ = news_events_for_ticker  # reserved for ticker-level catalyst work
    perf = dict(perf_row)
    ret_3m = _safe_float(perf.get("return_3m"))
    rs_vs_sleeve = sleeve_relative_strength(
        ret_3m, [sleeve_returns_3m.get(t) for t in sleeve_tickers]
    )

    # Sleeve rank by 3M return within the sleeve (1 = strongest).
    ranked = sorted(
        ((t, sleeve_returns_3m.get(t)) for t in sleeve_tickers),
        key=lambda kv: (kv[1] is None, -(kv[1] or 0)),
    )
    sleeve_rank = next(
        (i + 1 for i, (t, _) in enumerate(ranked) if t == ticker), None
    )

    status = classify_position_status(
        perf_row=perf,
        sleeve_card=sleeve_card,
        rs_vs_sleeve=rs_vs_sleeve,
        sleeve_rank_by_rs=sleeve_rank,
    )

    if status == INSUFFICIENT_STATUS or sleeve_card is None:
        return {
            "ticker": ticker,
            "sleeve": perf.get("sleeve"),
            "status": INSUFFICIENT_STATUS,
            "recommendation": REC_HOLD,
            "tier": None,
            "confidence": 0.0,
            "confidence_band": "Low",
            "urgency": "Low",
            "reason": "insufficient technical or thesis data — not rated",
            "price_trend": price_trend(perf),
            "rs_vs_spy": _safe_float(perf.get("rs_vs_spy")),
            "rs_vs_xlv": _safe_float(perf.get("rs_vs_xlv")),
            "rs_vs_sleeve": rs_vs_sleeve,
            "above_50dma": _safe_bool(perf.get("above_50dma")),
            "above_200dma": _safe_bool(perf_row.get("above_200dma")),
            "drawdown_from_high": _safe_float(perf.get("distance_from_52w_high")),
            "ticker_material_events": ticker_material_events,
        }

    sleeve_rec = str(sleeve_card.get("recommendation") or REC_HOLD)
    sleeve_tier = int(sleeve_card["recommended_tier"])
    tech = _technicals(perf, rs_vs_sleeve)

    # Recommendation: sleeve-level, stepped more defensive on broken
    # technicals. Never more aggressive.
    recommendation = sleeve_rec
    if tech["broken"]:
        recommendation = _step_more_defensive(sleeve_rec)

    # Tier: sleeve tier minus 1 when below 200DMA and underperforming the
    # sleeve; floored at 0; never above the sleeve tier.
    tier = sleeve_tier
    if tech["above_200"] is False and rs_vs_sleeve is not None and rs_vs_sleeve < 0:
        tier = max(0, sleeve_tier - 1)

    # Confidence: sleeve confidence adjusted for technical agreement.
    sleeve_conf = float(sleeve_card.get("confidence") or 0.0)
    if tech["strong"]:
        confidence = min(100.0, sleeve_conf + 10.0)
    elif tech["broken"]:
        confidence = max(0.0, sleeve_conf - 15.0)
    elif status in DEFENSIVE_STATUSES:
        confidence = max(0.0, sleeve_conf - 10.0)
    else:
        confidence = sleeve_conf
    confidence = round(confidence, 1)

    # Urgency: inherit, escalate on newly-broken technicals.
    urgency = str(sleeve_card.get("urgency") or "Low")
    if tech["broken"] and urgency in ("Low", "Moderate"):
        urgency = URGENCY_HIGH

    reason_bits = [
        f"sleeve {sleeve_card.get('sleeve')} is {sleeve_rec} (tier {sleeve_tier})",
        f"status {status}",
    ]
    if rs_vs_sleeve is not None:
        reason_bits.append(f"RS vs sleeve {rs_vs_sleeve:+.1%}")
    if tech["broken"]:
        reason_bits.append("technicals broken (below 200DMA, lagging sleeve)")
    elif tech["strong"]:
        reason_bits.append("technicals strong — recognized via status/confidence, tier uncapped at sleeve level")
    if ticker_material_events:
        reason_bits.append(f"{ticker_material_events} material event(s) tagging the ticker")

    return {
        "ticker": ticker,
        "sleeve": sleeve_card.get("sleeve"),
        "status": status,
        "recommendation": recommendation,
        "tier": tier,
        "sleeve_tier": sleeve_tier,
        "confidence": confidence,
        "confidence_band": confidence_band(confidence),
        "urgency": urgency,
        "reason": "; ".join(reason_bits),
        "price_trend": price_trend(perf),
        "rs_vs_spy": _safe_float(perf.get("rs_vs_spy")),
        "rs_vs_xlv": _safe_float(perf.get("rs_vs_xlv")),
        "rs_vs_sleeve": rs_vs_sleeve,
        "above_50dma": tech["above_50"],
        "above_200dma": tech["above_200"],
        "drawdown_from_high": _safe_float(perf.get("distance_from_52w_high")),
        "sleeve_market_confirmation": _safe_float(sleeve_card.get("market_confirmation")),
        "sleeve_catalyst": _safe_float(sleeve_card.get("catalyst")),
        "sleeve_expectations_risk": _safe_float(sleeve_card.get("expectations_risk")),
        "ticker_material_events": ticker_material_events,
        "upgrade_condition": (
            "Reclaim the 50DMA with RS vs sleeve turning positive for "
            "2 consecutive reports."
        ),
        "downgrade_condition": (
            "Close below the 200DMA, or RS vs sleeve worse than -10% over 3M."
        ),
        "invalidation_condition": (
            str(sleeve_card.get("invalidation_condition") or "n/a")
            + " Ticker-level: removal from the sleeve roster."
        ),
    }


def build_position_cards(
    *,
    performance_table: pd.DataFrame,
    decision_cards: list[dict],
    opportunity_ranking: pd.DataFrame,
    sleeves: list,
    news_events: pd.DataFrame,
) -> list[dict]:
    """One position card per sleeve-member ticker."""
    opp_by_sleeve: dict[str, dict] = {}
    if opportunity_ranking is not None and not opportunity_ranking.empty:
        for _, row in opportunity_ranking.iterrows():
            opp_by_sleeve[str(row.get("sleeve"))] = row.to_dict()
    # Decision cards carry the recommendation; opportunity rows carry the
    # scores the position classifier needs. Merge both per sleeve.
    cards_by_sleeve = {}
    for c in decision_cards:
        merged = dict(c)
        opp = opp_by_sleeve.get(c["sleeve"], {})
        merged["market_confirmation"] = _safe_float(opp.get("market_confirmation_score"))
        merged["catalyst"] = _safe_float(opp.get("catalyst_score"))
        merged["expectations_risk"] = _safe_float(opp.get("expectations_risk_score"))
        merged["structural"] = _safe_float(opp.get("structural_score"))
        if not merged.get("recognition_gap"):
            merged["recognition_gap"] = str(opp.get("recognition_gap") or "")
        cards_by_sleeve[c["sleeve"]] = merged
    tickers_by_sleeve = {s.name: list(s.tickers) for s in sleeves}
    sleeve_of = {}
    for name, tickers in tickers_by_sleeve.items():
        for t in tickers:
            sleeve_of[t] = name

    perf_by_ticker = {}
    if performance_table is not None and not performance_table.empty:
        for _, row in performance_table.iterrows():
            d = row.to_dict()
            d["sleeve"] = sleeve_of.get(str(d.get("ticker")))
            perf_by_ticker[str(d.get("ticker"))] = d

    # Ticker-tagged material event counts.
    event_counts: dict[str, int] = {}
    if news_events is not None and not news_events.empty:
        ticker_col = "tickers" if "tickers" in news_events.columns else "ticker"
        for _, event in news_events.iterrows():
            material = event.get("material_event", event.get("material", False))
            if not material:
                continue
            raw = event.get(ticker_col)
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                continue
            for t in str(raw).split(","):
                t = t.strip().upper()
                if t:
                    event_counts[t] = event_counts.get(t, 0) + 1

    returns_3m = {
        t: _safe_float(d.get("return_3m")) for t, d in perf_by_ticker.items()
    }

    cards = []
    for sleeve_name, tickers in tickers_by_sleeve.items():
        sleeve_card = cards_by_sleeve.get(sleeve_name)
        for ticker in tickers:
            perf = perf_by_ticker.get(ticker)
            if perf is None:
                perf = {"ticker": ticker, "sleeve": sleeve_name}
            cards.append(
                build_position_card(
                    ticker=ticker,
                    perf_row=perf,
                    sleeve_card=sleeve_card,
                    sleeve_tickers=tickers,
                    sleeve_returns_3m=returns_3m,
                    ticker_material_events=event_counts.get(ticker.upper(), 0),
                )
            )
    return cards


def position_divergences(cards: list[dict]) -> list[dict]:
    """Tickers materially more defensive than their sleeve — for the §1 pointer."""
    out = []
    for card in cards:
        if card.get("status") in (STATUS_EXIT, STATUS_THESIS_PRICE_BROKEN) or (
            card.get("tier") is not None
            and card.get("sleeve_tier") is not None
            and card["tier"] < card["sleeve_tier"]
        ):
            out.append(card)
    return out
