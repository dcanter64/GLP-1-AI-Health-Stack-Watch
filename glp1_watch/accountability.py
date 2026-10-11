"""Phase 5: historical accountability metrics.

Evaluates whether prior recommendations were useful, from the decision
journal's recorded forward outcomes. Every statistic is gated on a
documented minimum sample size and always shows n. "Insufficient
history" is reported separately from poor performance: a bad number
with enough data is shown as-is; too little data is not a verdict.

Definitions (operator-approved):
- False positive (absolute): increase-type recommendation followed by a
  negative 3M forward return.
- False negative (absolute): reduce/avoid-type recommendation followed by
  a positive 3M forward return.
- Relative variants compare the 3M forward return against SPY and
  against the entity's sleeve over the same window, because a positive
  absolute return can still validate a reduction if it materially
  underperforms.
- Lead time: mean days from decision to the maximum favorable excursion
  within the 3M window, among correct-direction calls.
"""

from __future__ import annotations

import pandas as pd

from .decision_engine import (
    REC_ACCUMULATE,
    REC_AVOID,
    REC_INCREASE,
    REC_REDUCE,
    REC_STRONG_INCREASE,
    REC_STRONG_REDUCE,
)
from .decision_journal import ENTITY_SLEEVE, ENTITY_TICKER, _extract_closes
from .position_engine import REC_NOT_RATED

INCREASE_TYPES = frozenset({REC_STRONG_INCREASE, REC_INCREASE, REC_ACCUMULATE})
REDUCE_TYPES = frozenset({REC_REDUCE, REC_STRONG_REDUCE, REC_AVOID})

MIN_N_RATES = 10
MIN_N_AVG = 5

INSUFFICIENT = "insufficient history"


def _gated(value: float | None, n: int, minimum: int, label: str) -> dict:
    if n < minimum:
        return {"status": INSUFFICIENT, "n": n, "minimum": minimum, "label": label}
    return {"status": "ok", "value": value, "n": n, "label": label}


def _with_3m_outcome(journal: pd.DataFrame) -> pd.DataFrame:
    if journal.empty:
        return journal
    frame = journal.copy()
    frame["outcome_3m"] = pd.to_numeric(frame["outcome_3m"], errors="coerce")
    return frame.dropna(subset=["outcome_3m"])


def _relative_outcomes(
    frame: pd.DataFrame,
    price_history: pd.DataFrame,
    sleeve_members: dict[str, list[str]] | None,
) -> pd.DataFrame:
    """Attach SPY-relative and sleeve-relative 3M outcomes.

    Computed from price history over each row's own measurement window
    (decision_date -> outcome_3m_date). Rows without a usable window keep
    NaN relatives.
    """
    frame = frame.copy()
    frame["outcome_3m_vs_spy"] = float("nan")
    frame["outcome_3m_vs_sleeve"] = float("nan")
    closes = _extract_closes(price_history)
    if closes.empty or "SPY" not in closes.columns:
        return frame
    for idx, row in frame.iterrows():
        start = pd.to_datetime(row.get("decision_price_date") or row.get("decision_date"), errors="coerce")
        end = pd.to_datetime(row.get("outcome_3m_date"), errors="coerce")
        if pd.isna(start) or pd.isna(end):
            continue
        spy = closes["SPY"]
        spy_start = spy[spy.index >= start]
        spy_end = spy[spy.index >= end]
        if spy_start.empty or spy_end.empty:
            continue
        spy_fwd = float(spy_end.iloc[0] / spy_start.iloc[0] - 1.0)
        frame.at[idx, "outcome_3m_vs_spy"] = float(row["outcome_3m"]) - spy_fwd
        # Sleeve-relative: equal-weight member forward return.
        sleeve = None
        if str(row.get("entity_type")) == ENTITY_TICKER and sleeve_members:
            for name, members in sleeve_members.items():
                if str(row["entity_name"]) in members:
                    sleeve = name
                    break
        elif str(row.get("entity_type")) == ENTITY_SLEEVE:
            sleeve = str(row["entity_name"])
        if sleeve and sleeve_members:
            members = [m for m in sleeve_members.get(sleeve, []) if m in closes.columns]
            fwd = []
            for m in members:
                s = closes[m]
                s0, s1 = s[s.index >= start], s[s.index >= end]
                if not s0.empty and not s1.empty and s0.iloc[0]:
                    fwd.append(float(s1.iloc[0] / s0.iloc[0] - 1.0))
            if fwd:
                frame.at[idx, "outcome_3m_vs_sleeve"] = float(row["outcome_3m"]) - sum(fwd) / len(fwd)
    return frame


def _excursions(
    frame: pd.DataFrame, price_history: pd.DataFrame
) -> pd.DataFrame:
    """Max adverse / favorable excursion within each row's 3M window."""
    frame = frame.copy()
    frame["max_adverse"] = float("nan")
    frame["max_favorable"] = float("nan")
    frame["lead_days"] = float("nan")
    closes = _extract_closes(price_history)
    if closes.empty:
        return frame
    for idx, row in frame.iterrows():
        if str(row.get("entity_type")) != ENTITY_TICKER:
            continue
        ticker = str(row["entity_name"])
        if ticker not in closes.columns:
            continue
        base = pd.to_numeric(pd.Series([row.get("decision_price")]), errors="coerce").iloc[0]
        if pd.isna(base) or not base:
            continue
        start = pd.to_datetime(row.get("decision_price_date"), errors="coerce")
        end = pd.to_datetime(row.get("outcome_3m_date"), errors="coerce")
        if pd.isna(start) or pd.isna(end):
            continue
        window = closes[ticker][(closes.index >= start) & (closes.index <= end)]
        if window.empty:
            continue
        rets = window / float(base) - 1.0
        frame.at[idx, "max_adverse"] = float(rets.min())
        frame.at[idx, "max_favorable"] = float(rets.max())
        frame.at[idx, "lead_days"] = float((rets.idxmax() - start).days)
    return frame


def compute_accountability(
    journal: pd.DataFrame,
    price_history: pd.DataFrame,
    sleeve_members: dict[str, list[str]] | None = None,
    min_n_rates: int = MIN_N_RATES,
    min_n_avg: int = MIN_N_AVG,
) -> dict:
    """Accountability metrics from recorded 3M forward outcomes.

    M3: NOT RATED rows are not decisions and are excluded from all graded
    groups — they must never appear as a HOLD call in accountability.
    """
    if journal is not None and not journal.empty and "recommendation" in journal.columns:
        journal = journal[~journal["recommendation"].isin({REC_NOT_RATED})]
    frame = _with_3m_outcome(journal)
    n = len(frame)
    # Confidence band is derived, not stored — the journal keeps the raw
    # confidence score as the immutable decision-time field.
    if not frame.empty:
        if "confidence_band" not in frame.columns:
            from .decision_engine import confidence_band as _band

            conf = pd.to_numeric(frame["confidence"], errors="coerce")
            frame["confidence_band"] = conf.apply(
                lambda c: _band(float(c)) if not pd.isna(c) else "Unknown"
            )
    metrics: dict[str, dict] = {}
    metrics["n_with_3m_outcome"] = {"status": "ok", "value": n, "n": n,
                                   "label": "decisions with a recorded 3M outcome"}

    inc = frame[frame["recommendation"].isin(INCREASE_TYPES)]
    red = frame[frame["recommendation"].isin(REDUCE_TYPES)]

    # Absolute error rates.
    fp = inc[inc["outcome_3m"] < 0]
    fn = red[red["outcome_3m"] > 0]
    metrics["false_positive_rate_absolute"] = _gated(
        len(fp) / len(inc) if len(inc) else None, len(inc), min_n_rates,
        "increase-type recommendations followed by a negative 3M return",
    )
    metrics["false_negative_rate_absolute"] = _gated(
        len(fn) / len(red) if len(red) else None, len(red), min_n_rates,
        "reduce/avoid-type recommendations followed by a positive 3M return",
    )

    # Relative error rates (vs SPY and vs sleeve).
    rel = _relative_outcomes(frame, price_history, sleeve_members)
    rel_inc = rel[rel["recommendation"].isin(INCREASE_TYPES)].dropna(subset=["outcome_3m_vs_spy"])
    rel_red = rel[rel["recommendation"].isin(REDUCE_TYPES)].dropna(subset=["outcome_3m_vs_spy"])
    fp_spy = rel_inc[rel_inc["outcome_3m_vs_spy"] < 0]
    fn_spy = rel_red[rel_red["outcome_3m_vs_spy"] > 0]
    metrics["false_positive_rate_vs_spy"] = _gated(
        len(fp_spy) / len(rel_inc) if len(rel_inc) else None, len(rel_inc), min_n_rates,
        "increase-type recommendations underperforming SPY over 3M",
    )
    metrics["false_negative_rate_vs_spy"] = _gated(
        len(fn_spy) / len(rel_red) if len(rel_red) else None, len(rel_red), min_n_rates,
        "reduce/avoid-type recommendations outperforming SPY over 3M",
    )
    rel_inc_sl = rel[rel["recommendation"].isin(INCREASE_TYPES)].dropna(subset=["outcome_3m_vs_sleeve"])
    rel_red_sl = rel[rel["recommendation"].isin(REDUCE_TYPES)].dropna(subset=["outcome_3m_vs_sleeve"])
    fp_sl = rel_inc_sl[rel_inc_sl["outcome_3m_vs_sleeve"] < 0]
    fn_sl = rel_red_sl[rel_red_sl["outcome_3m_vs_sleeve"] > 0]
    metrics["false_positive_rate_vs_sleeve"] = _gated(
        len(fp_sl) / len(rel_inc_sl) if len(rel_inc_sl) else None, len(rel_inc_sl), min_n_rates,
        "increase-type recommendations underperforming their sleeve over 3M",
    )
    metrics["false_negative_rate_vs_sleeve"] = _gated(
        len(fn_sl) / len(rel_red_sl) if len(rel_red_sl) else None, len(rel_red_sl), min_n_rates,
        "reduce/avoid-type recommendations outperforming their sleeve over 3M",
    )

    # Average forward returns after increase vs reduce.
    metrics["avg_3m_after_increase"] = _gated(
        float(inc["outcome_3m"].mean()) if len(inc) else None, len(inc), min_n_avg,
        "average 3M forward return after increase-type recommendations",
    )
    metrics["avg_3m_after_reduce"] = _gated(
        float(red["outcome_3m"].mean()) if len(red) else None, len(red), min_n_avg,
        "average 3M forward return after reduce/avoid-type recommendations",
    )

    # Excursions and lead time (ticker rows with daily bars).
    exc = _excursions(frame, price_history)
    exc_ok = exc.dropna(subset=["max_adverse"])
    metrics["max_adverse_excursion_avg"] = _gated(
        float(exc_ok["max_adverse"].mean()) if len(exc_ok) else None, len(exc_ok), min_n_avg,
        "average maximum adverse excursion within the 3M window",
    )
    metrics["max_favorable_excursion_avg"] = _gated(
        float(exc_ok["max_favorable"].mean()) if len(exc_ok) else None, len(exc_ok), min_n_avg,
        "average maximum favorable excursion within the 3M window",
    )
    correct = exc[
        ((exc["recommendation"].isin(INCREASE_TYPES)) & (exc["outcome_3m"] > 0))
        | ((exc["recommendation"].isin(REDUCE_TYPES)) & (exc["outcome_3m"] < 0))
    ].dropna(subset=["lead_days"])
    metrics["avg_lead_time_days"] = _gated(
        float(correct["lead_days"].mean()) if len(correct) else None, len(correct), min_n_avg,
        "mean days from decision to max favorable excursion, correct-direction calls",
    )

    # Recommendation turnover: tier changes per decided entity.
    journal_sorted = journal.sort_values(["entity_type", "entity_name", "decision_date"]) if not journal.empty else journal
    changes, total = 0, 0
    if not journal_sorted.empty and "recommended_tier" in journal_sorted.columns:
        tiers = pd.to_numeric(journal_sorted["recommended_tier"], errors="coerce")
        for _, group in journal_sorted.assign(_tier=tiers).groupby(["entity_type", "entity_name"]):
            seq = group["_tier"].dropna().tolist()
            total += max(len(seq) - 1, 0)
            changes += sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    metrics["recommendation_turnover"] = _gated(
        changes / total if total else None, total, min_n_avg,
        "tier changes per sequential decision opportunity",
    )

    # Performance by confidence band and by recommendation type.
    by_band = {}
    if not frame.empty and "confidence_band" in frame.columns:
        for band, group in frame.groupby("confidence_band"):
            by_band[str(band)] = _gated(
                float(group["outcome_3m"].mean()) if len(group) else None, len(group), min_n_avg,
                f"average 3M forward return, confidence {band}",
            )
    metrics["by_confidence_band"] = by_band
    by_rec = {}
    if not frame.empty and "recommendation" in frame.columns:
        for rec, group in frame.groupby("recommendation"):
            by_rec[str(rec)] = _gated(
                float(group["outcome_3m"].mean()) if len(group) else None, len(group), min_n_avg,
                f"average 3M forward return, recommendation {rec}",
            )
    metrics["by_recommendation"] = by_rec

    return metrics


def build_committee_pointer(divergences: list[dict], metrics: dict) -> str:
    """Short §1 pointer when position divergence or accountability is material.

    Fires only for divergences or gradable (above-minimum) accountability
    metrics. Below-minimum data stays silent here by design: §10 already
    reports "insufficient history (n=X)" per metric, and a §1 pointer must
    not amplify non-gradable data into the Investment Committee Decision.
    """
    bits = []
    if divergences:
        names = ", ".join(d["ticker"] for d in divergences[:5])
        more = f" (+{len(divergences) - 5} more)" if len(divergences) > 5 else ""
        bits.append(
            f"Position-level divergence: {names}{more} read more defensive "
            f"than their sleeves (see §9). Ticker calls do not override "
            f"broad-stack exposure."
        )
    gradable = any(
        isinstance(m, dict) and m.get("status") == "ok"
        for key, m in metrics.items()
        if key != "n_with_3m_outcome"
    )
    if gradable:
        bits.append("Accountability: first graded recommendation outcomes available (see §10).")
    return " ".join(bits)


def summarize_accountability(metrics: dict) -> list[str]:
    """Human-readable lines for the report. Insufficient-history and poor
    performance are never conflated."""
    lines = []
    n = metrics.get("n_with_3m_outcome", {}).get("n", 0)
    lines.append(f"- Decisions with a recorded 3M outcome: {n}.")
    for key, metric in metrics.items():
        if key in ("n_with_3m_outcome", "by_confidence_band", "by_recommendation"):
            continue
        if metric["status"] == INSUFFICIENT:
            lines.append(
                f"- {metric['label']}: insufficient history "
                f"(n={metric['n']}, need {metric['minimum']}) — not a performance verdict."
            )
        else:
            value = metric["value"]
            txt = f"{value:.1%}" if isinstance(value, float) and ("rate" in key or "return" in key or "excursion" in key) else f"{value:.1f}"
            if "lead_time" in key:
                txt = f"{value:.0f} days"
            if "turnover" in key:
                txt = f"{value:.2f}"
            lines.append(f"- {metric['label']}: {txt} (n={metric['n']}).")
    for section, title in (("by_confidence_band", "By confidence band"), ("by_recommendation", "By recommendation")):
        lines.append(f"- {title}:")
        for name, metric in metrics.get(section, {}).items():
            if metric["status"] == INSUFFICIENT:
                lines.append(f"  - {name}: insufficient history (n={metric['n']}).")
            else:
                lines.append(f"  - {name}: {metric['value']:.1%} (n={metric['n']}).")
    return lines
