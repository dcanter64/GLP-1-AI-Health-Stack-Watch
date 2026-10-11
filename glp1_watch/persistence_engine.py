"""Phase 3: persistence engine — history store, persistence metrics, readiness.

The history store is a CSV at ``output/history/health_stack_history.csv``
(one row per sleeve per report date) following the project's storage
convention. Writes are upserts on (as_of_date, sleeve): a same-day rerun
replaces its rows instead of duplicating them. Writes are atomic
(temp file + rename) so a mid-write crash cannot truncate the store.

Streaks are keyed by sleeve name: renaming a sleeve starts a fresh history
for the new name (the old rows remain under the old name). This is expected
behavior — sleeve identity is the name, not the roster.

Persistence metrics per sleeve (from the sorted history):
- current / previous opportunity score
- four-report and eight-report trend (first-vs-last delta over the window)
- consecutive improving / deteriorating reports (delta >= 1.0 / <= -1.0)
- consecutive reports above / below threshold (strong 65 / weak 45)
- date the current condition began
- maximum severity reached (extreme score inside the current streak)
- second derivative: accelerating / decelerating / steady / insufficient

Recommendation-readiness classification (precedence order):
1. Insufficient Evidence — fewer than two scored reports, or no signal
2. Repairing — weak (<45) with two or more consecutive improving reports
3. Exhausted — strong (>=65) with worsening catalysts and narrowing breadth
4. Persistent — strong (>=65) for four or more consecutive reports
5. Confirmed — three or more consecutive improving reports with breadth confirmation
6. Developing — two consecutive improving reports
7. Early Signal — one improving report
8. Fallback: Insufficient Evidence (stable/neutral — insufficient evidence *for action*)

Exhausted deliberately outranks Persistent: a strong-but-rotting sleeve must
not read as persistently healthy. Conflicting evidence is always attached to
the classification, never hidden by it.
"""

from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

HISTORY_FILENAME = "health_stack_history.csv"

#: Minimum opportunity-score delta counting as improvement/deterioration.
IMPROVEMENT_EPSILON = 1.0

STRONG_THRESHOLD = 65.0
WEAK_THRESHOLD = 45.0

READINESS_INSUFFICIENT = "Insufficient Evidence"
READINESS_EARLY_SIGNAL = "Early Signal"
READINESS_DEVELOPING = "Developing"
READINESS_CONFIRMED = "Confirmed"
READINESS_PERSISTENT = "Persistent"
READINESS_EXHAUSTED = "Exhausted"
READINESS_REPAIRING = "Repairing"

HISTORY_COLUMNS = [
    "as_of_date",
    "sleeve",
    "required",
    "opportunity_score",
    "structural_score",
    "market_confirmation_score",
    "catalyst_score",
    "expectations_risk_score",
    "trend",
    "confirmation_state",
    "breadth_50dma",
    "breadth_outperform_xlv",
    "concentration_verdict",
    "market_data_quality",
    "news_confidence",
    "material_event_count",
    "flywheel_score",
]


def history_path(history_dir: str | Path) -> Path:
    return Path(history_dir) / HISTORY_FILENAME


def load_history(history_dir: str | Path) -> pd.DataFrame:
    """Load the sleeve history, sorted by (sleeve, as_of_date), deduplicated."""
    path = history_path(history_dir)
    if not path.exists():
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    frame = pd.read_csv(path)
    for column in HISTORY_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame = frame[HISTORY_COLUMNS].copy()
    frame["as_of_date"] = pd.to_datetime(frame["as_of_date"], format="%Y-%m-%d", errors="coerce")
    frame = frame.dropna(subset=["as_of_date", "sleeve"])
    frame = frame.drop_duplicates(subset=["as_of_date", "sleeve"], keep="last")
    frame = frame.sort_values(["sleeve", "as_of_date"]).reset_index(drop=True)
    return frame


def append_history(
    history_dir: str | Path,
    rows: list[dict[str, object]],
) -> pd.DataFrame:
    """Upsert rows into the history store and return the full sorted history.

    Rows with the same (as_of_date, sleeve) as existing rows replace them.
    """
    path = history_path(history_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_history(history_dir)
    new_frame = pd.DataFrame(rows, columns=HISTORY_COLUMNS)
    if not new_frame.empty:
        new_frame["as_of_date"] = pd.to_datetime(new_frame["as_of_date"], format="%Y-%m-%d", errors="coerce")
        new_frame = new_frame.dropna(subset=["as_of_date", "sleeve"])
        today = pd.Timestamp(date.today().isoformat())
        future = new_frame[new_frame["as_of_date"] > today]
        if not future.empty:
            bad = sorted(future["as_of_date"].dt.strftime("%Y-%m-%d").unique().tolist())
            raise ValueError(
                f"persistence_engine: refusing to record future report date(s): {', '.join(bad)}"
            )
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
    # Atomic write: a crash mid-write must never leave a truncated history.
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
    return load_history(history_dir)


def _sleeve_history(history: pd.DataFrame, sleeve: str) -> pd.DataFrame:
    frame = history[history["sleeve"] == sleeve].copy()
    return frame.sort_values("as_of_date").reset_index(drop=True)


def _scores(frame: pd.DataFrame) -> list[float]:
    return [
        float(value) if pd.notna(value) else float("nan")
        for value in pd.to_numeric(frame["opportunity_score"], errors="coerce")
    ]


def _window_trend(scores: list[float], window: int) -> str:
    usable = [s for s in scores[-window:] if not pd.isna(s)]
    if len(usable) < 2:
        return "insufficient"
    delta = usable[-1] - usable[0]
    if delta >= IMPROVEMENT_EPSILON:
        return "improving"
    if delta <= -IMPROVEMENT_EPSILON:
        return "deteriorating"
    return "flat"


def _consecutive(scores: list[float], predicate) -> int:
    count = 0
    for value in reversed(scores):
        if pd.isna(value) or not predicate(value):
            break
        count += 1
    return count


def _streak_deltas(scores: list[float]) -> list[float]:
    deltas = []
    for previous, current in zip(scores, scores[1:]):
        if pd.isna(previous) or pd.isna(current):
            deltas.append(float("nan"))
            continue
        deltas.append(current - previous)
    return deltas


def compute_persistence_metrics(history: pd.DataFrame, sleeve: str) -> dict[str, object]:
    """Persistence metrics for one sleeve from its sorted history."""
    frame = _sleeve_history(history, sleeve)
    scores = _scores(frame)
    usable = [s for s in scores if not pd.isna(s)]
    metrics: dict[str, object] = {
        "sleeve": sleeve,
        "report_count": len(usable),
        "current_score": usable[-1] if usable else float("nan"),
        "previous_score": usable[-2] if len(usable) >= 2 else float("nan"),
        "four_report_trend": _window_trend(scores, 4),
        "eight_report_trend": _window_trend(scores, 8),
        "consecutive_improving": 0,
        "consecutive_deteriorating": 0,
        "consecutive_above_strong": 0,
        "consecutive_below_weak": 0,
        "condition": None,
        "condition_began": None,
        "max_severity": float("nan"),
        "second_derivative": "insufficient",
    }
    if len(usable) < 2:
        return metrics

    deltas = _streak_deltas(scores)
    improving = 0
    for delta in reversed(deltas):
        if pd.isna(delta) or delta < IMPROVEMENT_EPSILON:
            break
        improving += 1
    deteriorating = 0
    for delta in reversed(deltas):
        if pd.isna(delta) or delta > -IMPROVEMENT_EPSILON:
            break
        deteriorating += 1
    above_strong = _consecutive(scores, lambda v: v >= STRONG_THRESHOLD)
    below_weak = _consecutive(scores, lambda v: v < WEAK_THRESHOLD)

    metrics["consecutive_improving"] = improving
    metrics["consecutive_deteriorating"] = deteriorating
    metrics["consecutive_above_strong"] = above_strong
    metrics["consecutive_below_weak"] = below_weak

    # The current condition is the longest active streak; its start date is
    # the earliest report participating in it. The winning streak is named so
    # overlapping streaks are not ambiguous.
    streaks = {
        "improving": improving,
        "deteriorating": deteriorating,
        "above_strong": above_strong,
        "below_weak": below_weak,
    }
    streak_length = max(streaks.values())
    metrics["condition"] = (
        max(streaks, key=lambda k: streaks[k]) if streak_length > 0 else None
    )
    if streak_length > 0:
        streak_rows = frame.tail(streak_length + 1)
        first = streak_rows.iloc[0]["as_of_date"]
        metrics["condition_began"] = (
            first.strftime("%Y-%m-%d") if hasattr(first, "strftime") else str(first)
        )
        streak_scores = [s for s in scores[-(streak_length + 1):] if not pd.isna(s)]
        if deteriorating >= improving:
            metrics["max_severity"] = min(streak_scores) if streak_scores else float("nan")
        else:
            metrics["max_severity"] = max(streak_scores) if streak_scores else float("nan")

    # Second derivative needs three scored reports (two deltas). Differences
    # below the noise floor count as steady, not (de)accelerating.
    clean_deltas = [d for d in deltas[-2:] if not pd.isna(d)]
    if len(clean_deltas) == 2:
        older, newer = clean_deltas
        if abs(newer - older) < IMPROVEMENT_EPSILON:
            metrics["second_derivative"] = "steady"
        elif older >= IMPROVEMENT_EPSILON and newer >= IMPROVEMENT_EPSILON:
            metrics["second_derivative"] = (
                "accelerating" if newer > older else "decelerating"
            )
        elif older <= -IMPROVEMENT_EPSILON and newer <= -IMPROVEMENT_EPSILON:
            metrics["second_derivative"] = (
                "accelerating" if newer < older else "decelerating"
            )
        else:
            metrics["second_derivative"] = "mixed"
    return metrics


def _column_delta(frame: pd.DataFrame, column: str, lookback: int) -> float:
    if column not in frame.columns:
        return float("nan")
    values = [
        float(v) if pd.notna(v) else float("nan")
        for v in pd.to_numeric(frame[column], errors="coerce").tail(lookback + 1)
    ]
    usable = [v for v in values if not pd.isna(v)]
    if len(usable) < 2:
        return float("nan")
    return usable[-1] - usable[0]


def classify_readiness(
    history: pd.DataFrame,
    sleeve: str,
    metrics: dict[str, object] | None = None,
) -> dict[str, object]:
    """Recommendation-readiness classification for one sleeve.

    Returns state, note, and any conflicting evidence. Conflicts are reported
    alongside the state, never hidden by it.
    """
    if metrics is None:
        metrics = compute_persistence_metrics(history, sleeve)
    frame = _sleeve_history(history, sleeve)
    current = metrics["current_score"]
    conflicts: list[str] = []

    def _risk_rising() -> bool:
        delta = _column_delta(frame, "expectations_risk_score", 1)
        return not pd.isna(delta) and delta >= 5.0

    def _catalyst_falling() -> bool:
        delta = _column_delta(frame, "catalyst_score", 2)
        return not pd.isna(delta) and delta <= -5.0

    if pd.isna(current) or int(metrics["report_count"]) < 2:
        return {
            "sleeve": sleeve,
            "readiness": READINESS_INSUFFICIENT,
            "note": "fewer than two scored reports",
            "conflicts": conflicts,
        }

    improving = int(metrics["consecutive_improving"])
    if current < WEAK_THRESHOLD and improving >= 2:
        if _column_delta(frame, "structural_score", 2) < 0:
            conflicts.append("structural thesis not yet confirming the repair")
        return {
            "sleeve": sleeve,
            "readiness": READINESS_REPAIRING,
            "note": f"weak score ({current:.1f}) with {improving} consecutive improving reports",
            "conflicts": conflicts,
        }

    catalyst_3d = _column_delta(frame, "catalyst_score", 2)
    # Breadth is measured directly via 50DMA participation, not the blended
    # market-confirmation score (whose other components could mask narrowing).
    breadth_3d = _column_delta(frame, "breadth_50dma", 2)
    if (
        current >= STRONG_THRESHOLD
        and not pd.isna(catalyst_3d)
        and catalyst_3d <= -5.0
        and not pd.isna(breadth_3d)
        and breadth_3d <= 0
    ):
        return {
            "sleeve": sleeve,
            "readiness": READINESS_EXHAUSTED,
            "note": (
                f"strong score ({current:.1f}) with worsening catalysts "
                f"({catalyst_3d:+.1f} over 3 reports) and narrowing breadth "
                f"({breadth_3d:+.1%} participation)"
            ),
            "conflicts": conflicts,
        }

    if int(metrics["consecutive_above_strong"]) >= 4:
        if _catalyst_falling():
            conflicts.append("catalysts softening beneath persistent strength")
        if _risk_rising():
            conflicts.append("expectations risk rising beneath persistent strength")
        return {
            "sleeve": sleeve,
            "readiness": READINESS_PERSISTENT,
            "note": f"strong score for {metrics['consecutive_above_strong']} consecutive reports",
            "conflicts": conflicts,
        }

    latest_mkt = frame["market_confirmation_score"]
    latest_mkt_value = (
        float(pd.to_numeric(latest_mkt, errors="coerce").iloc[-1])
        if not frame.empty
        else float("nan")
    )
    if improving >= 3 and not pd.isna(latest_mkt_value) and latest_mkt_value >= 50.0:
        if _risk_rising():
            conflicts.append("expectations risk rising while score improves")
        return {
            "sleeve": sleeve,
            "readiness": READINESS_CONFIRMED,
            "note": (
                f"{improving} consecutive improving reports with breadth "
                f"confirmation (market confirmation {latest_mkt_value:.1f})"
            ),
            "conflicts": conflicts,
        }

    if improving >= 2:
        return {
            "sleeve": sleeve,
            "readiness": READINESS_DEVELOPING,
            "note": f"{improving} consecutive improving reports",
            "conflicts": conflicts,
        }
    if improving >= 1:
        return {
            "sleeve": sleeve,
            "readiness": READINESS_EARLY_SIGNAL,
            "note": "one improving report",
            "conflicts": conflicts,
        }
    deteriorating = int(metrics["consecutive_deteriorating"])
    if deteriorating > 0:
        # The spec defines no readiness state for pure deterioration; say so
        # plainly instead of claiming there is no directional signal.
        return {
            "sleeve": sleeve,
            "readiness": READINESS_INSUFFICIENT,
            "note": (
                f"deteriorating for {deteriorating} consecutive report(s) — "
                "the readiness set has no deterioration state; monitoring"
            ),
            "conflicts": conflicts,
        }
    return {
        "sleeve": sleeve,
        "readiness": READINESS_INSUFFICIENT,
        "note": "no persistent directional signal — insufficient evidence for action",
        "conflicts": conflicts,
    }


def build_persistence_table(
    history: pd.DataFrame,
    sleeves: list,
) -> pd.DataFrame:
    """One row per sleeve: persistence metrics + readiness classification."""
    columns = [
        "sleeve",
        "required",
        "current_score",
        "previous_score",
        "score_change",
        "four_report_trend",
        "consecutive_improving",
        "consecutive_deteriorating",
        "consecutive_above_strong",
        "consecutive_below_weak",
        "condition_began",
        "max_severity",
        "second_derivative",
        "readiness",
        "readiness_note",
        "conflicts",
    ]
    sleeve_required = {s.name: bool(s.required) for s in sleeves}
    rows: list[dict[str, object]] = []
    for sleeve in sleeves:
        metrics = compute_persistence_metrics(history, sleeve.name)
        readiness = classify_readiness(history, sleeve.name, metrics)
        current = metrics["current_score"]
        previous = metrics["previous_score"]
        change = (
            float(current - previous)
            if not pd.isna(current) and not pd.isna(previous)
            else float("nan")
        )
        rows.append(
            {
                "sleeve": sleeve.name,
                "required": sleeve_required[sleeve.name],
                "current_score": current,
                "previous_score": previous,
                "score_change": change,
                "four_report_trend": metrics["four_report_trend"],
                "consecutive_improving": metrics["consecutive_improving"],
                "consecutive_deteriorating": metrics["consecutive_deteriorating"],
                "consecutive_above_strong": metrics["consecutive_above_strong"],
                "consecutive_below_weak": metrics["consecutive_below_weak"],
                "condition_began": metrics["condition_began"],
                "max_severity": metrics["max_severity"],
                "second_derivative": metrics["second_derivative"],
                "readiness": readiness["readiness"],
                "readiness_note": readiness["note"],
                "conflicts": "; ".join(readiness["conflicts"]),
            }
        )
    table = pd.DataFrame(rows, columns=columns)
    if not table.empty:
        table = table.sort_values(
            "current_score", ascending=False, na_position="last"
        ).reset_index(drop=True)
    return table


def build_what_changed_lines(history: pd.DataFrame) -> list[str]:
    """Sleeve-level diff between the two most recent report dates."""
    lines: list[str] = []
    if history.empty:
        return ["No history yet — this is the first recorded report."]
    dates = sorted(history["as_of_date"].dropna().unique())
    if len(dates) < 2:
        return ["Only one report in history — nothing to compare yet."]
    previous_date, latest_date = dates[-2], dates[-1]
    prev = history[history["as_of_date"] == previous_date].set_index("sleeve")
    latest = history[history["as_of_date"] == latest_date].set_index("sleeve")

    def _fmt(value: object) -> str:
        parsed = pd.to_numeric(value, errors="coerce")
        return f"{float(parsed):+.1f}" if pd.notna(parsed) else "n/a"

    prev_top3 = set(
        pd.to_numeric(prev["opportunity_score"], errors="coerce")
        .nlargest(3)
        .index.tolist()
    )
    latest_top3 = set(
        pd.to_numeric(latest["opportunity_score"], errors="coerce")
        .nlargest(3)
        .index.tolist()
    )
    new_leaders = sorted(latest_top3 - prev_top3)
    lost_leaders = sorted(prev_top3 - latest_top3)
    if new_leaders:
        lines.append(f"- New leaders: {', '.join(new_leaders)} entered the top 3.")
    if lost_leaders:
        lines.append(f"- Lost leaders: {', '.join(lost_leaders)} dropped out of the top 3.")

    for sleeve in sorted(set(prev.index) | set(latest.index)):
        if sleeve not in prev.index or sleeve not in latest.index:
            lines.append(f"- {sleeve}: newly tracked." if sleeve not in prev.index else f"- {sleeve}: no longer scored.")
            continue
        old_score = pd.to_numeric(prev.loc[sleeve, "opportunity_score"], errors="coerce")
        new_score = pd.to_numeric(latest.loc[sleeve, "opportunity_score"], errors="coerce")
        if pd.notna(old_score) and pd.notna(new_score):
            delta = float(new_score - old_score)
            if abs(delta) >= 5.0:
                direction = "rose" if delta > 0 else "fell"
                lines.append(f"- {sleeve}: opportunity {direction} {_fmt(delta)} points ({float(old_score):.1f} → {float(new_score):.1f}).")
        old_trend = prev.loc[sleeve, "trend"] if "trend" in prev.columns else None
        new_trend = latest.loc[sleeve, "trend"] if "trend" in latest.columns else None
        if pd.notna(old_trend) and pd.notna(new_trend) and str(old_trend) != str(new_trend):
            lines.append(f"- {sleeve}: trend changed ({old_trend} → {new_trend}).")
        old_cat = pd.to_numeric(prev.loc[sleeve, "catalyst_score"], errors="coerce") if "catalyst_score" in prev.columns else float("nan")
        new_cat = pd.to_numeric(latest.loc[sleeve, "catalyst_score"], errors="coerce") if "catalyst_score" in latest.columns else float("nan")
        if pd.notna(old_cat) and pd.notna(new_cat) and abs(float(new_cat - old_cat)) >= 10.0:
            lines.append(f"- {sleeve}: catalyst score {_fmt(new_cat - old_cat)} points.")
        old_verdict = prev.loc[sleeve, "concentration_verdict"] if "concentration_verdict" in prev.columns else None
        new_verdict = latest.loc[sleeve, "concentration_verdict"] if "concentration_verdict" in latest.columns else None
        if pd.notna(old_verdict) and pd.notna(new_verdict) and str(old_verdict) != str(new_verdict):
            lines.append(f"- Leadership concentration: {old_verdict} → {new_verdict}.")

    old_quality = prev["market_data_quality"].iloc[0] if "market_data_quality" in prev.columns and not prev.empty else None
    new_quality = latest["market_data_quality"].iloc[0] if "market_data_quality" in latest.columns and not latest.empty else None
    if pd.notna(old_quality) and pd.notna(new_quality) and str(old_quality) != str(new_quality):
        lines.append(f"- Market data quality: {old_quality} → {new_quality}.")
    old_conf = prev["news_confidence"].iloc[0] if "news_confidence" in prev.columns and not prev.empty else None
    new_conf = latest["news_confidence"].iloc[0] if "news_confidence" in latest.columns and not latest.empty else None
    if pd.notna(old_conf) and pd.notna(new_conf) and str(old_conf) != str(new_conf):
        lines.append(f"- News confidence: {old_conf} → {new_conf}.")

    if not lines:
        lines.append("- No material changes since the previous report.")
    return lines
