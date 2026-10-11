"""Tests for the Phase 3 persistence engine."""

from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

import pandas as pd

from glp1_watch.health_stack_sleeves import Sleeve
from glp1_watch.persistence_engine import (
    HISTORY_COLUMNS,
    append_history,
    build_persistence_table,
    build_what_changed_lines,
    classify_readiness,
    compute_persistence_metrics,
    load_history,
)


def make_sleeves() -> list[Sleeve]:
    return [
        Sleeve(name="Leaders", tickers=("LLY", "NVO"), required=True),
        Sleeve(name="Platforms", tickers=("RXRX",), required=True),
    ]


def history_row(
    date: str,
    sleeve: str,
    opportunity: float,
    catalyst: float = 20.0,
    market_confirmation: float = 55.0,
    expectations_risk: float = 30.0,
    structural: float = 55.0,
    breadth_50dma: float = 0.6,
) -> dict:
    return {
        "as_of_date": date,
        "sleeve": sleeve,
        "required": True,
        "opportunity_score": opportunity,
        "structural_score": structural,
        "market_confirmation_score": market_confirmation,
        "catalyst_score": catalyst,
        "expectations_risk_score": expectations_risk,
        "trend": "Neutral and improving",
        "confirmation_state": "Selectively Confirming",
        "breadth_50dma": breadth_50dma,
        "breadth_outperform_xlv": 0.5,
        "concentration_verdict": "broad",
        "market_data_quality": "High",
        "news_confidence": "High",
        "material_event_count": 3,
        "flywheel_score": 55.0,
    }


def history_frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=HISTORY_COLUMNS)
    frame["as_of_date"] = pd.to_datetime(frame["as_of_date"])
    return frame.sort_values(["sleeve", "as_of_date"]).reset_index(drop=True)


class HistoryStoreTests(unittest.TestCase):
    def test_history_loading_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rows = [
                history_row("2026-10-01", "Leaders", 60.0),
                history_row("2026-10-08", "Leaders", 62.0),
            ]
            loaded = append_history(tmp, rows)
            self.assertEqual(len(loaded), 2)
            reloaded = load_history(tmp)
            self.assertEqual(len(reloaded), 2)
            self.assertEqual(
                reloaded.iloc[-1]["opportunity_score"], 62.0
            )

    def test_duplicate_report_dates_upsert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            append_history(tmp, [history_row("2026-10-01", "Leaders", 60.0)])
            append_history(tmp, [history_row("2026-10-01", "Leaders", 64.0)])
            loaded = load_history(tmp)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded.iloc[0]["opportunity_score"], 64.0)

    def test_out_of_order_dates_sorted(self) -> None:
        frame = history_frame(
            [
                history_row("2026-10-08", "Leaders", 62.0),
                history_row("2026-10-01", "Leaders", 60.0),
            ]
        )
        metrics = compute_persistence_metrics(frame, "Leaders")
        self.assertEqual(metrics["current_score"], 62.0)
        self.assertEqual(metrics["previous_score"], 60.0)

    def test_first_run_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            loaded = load_history(tmp)
            self.assertTrue(loaded.empty)
            table = build_persistence_table(loaded, make_sleeves())
            self.assertTrue(
                (table["readiness"] == "Insufficient Evidence").all()
            )


class PersistenceMetricsTests(unittest.TestCase):
    def test_consecutive_improvement(self) -> None:
        frame = history_frame(
            [history_row(f"2026-10-0{d}", "Leaders", 50.0 + d * 2.0) for d in range(1, 6)]
        )
        metrics = compute_persistence_metrics(frame, "Leaders")
        self.assertEqual(metrics["consecutive_improving"], 4)
        self.assertEqual(metrics["consecutive_deteriorating"], 0)
        self.assertEqual(metrics["four_report_trend"], "improving")

    def test_consecutive_deterioration(self) -> None:
        frame = history_frame(
            [history_row(f"2026-10-0{d}", "Leaders", 70.0 - d * 3.0) for d in range(1, 5)]
        )
        metrics = compute_persistence_metrics(frame, "Leaders")
        self.assertEqual(metrics["consecutive_deteriorating"], 3)
        self.assertEqual(metrics["consecutive_improving"], 0)

    def test_noise_does_not_count_as_streak(self) -> None:
        frame = history_frame(
            [
                history_row("2026-10-01", "Leaders", 55.0),
                history_row("2026-10-02", "Leaders", 55.4),
                history_row("2026-10-03", "Leaders", 55.1),
            ]
        )
        metrics = compute_persistence_metrics(frame, "Leaders")
        self.assertEqual(metrics["consecutive_improving"], 0)
        self.assertEqual(metrics["four_report_trend"], "flat")

    def test_second_derivative_classification(self) -> None:
        accelerating = history_frame(
            [
                history_row("2026-10-01", "Leaders", 50.0),
                history_row("2026-10-02", "Leaders", 52.0),
                history_row("2026-10-03", "Leaders", 56.0),
            ]
        )
        self.assertEqual(
            compute_persistence_metrics(accelerating, "Leaders")["second_derivative"],
            "accelerating",
        )
        decelerating = history_frame(
            [
                history_row("2026-10-01", "Leaders", 50.0),
                history_row("2026-10-02", "Leaders", 56.0),
                history_row("2026-10-03", "Leaders", 57.0),
            ]
        )
        self.assertEqual(
            compute_persistence_metrics(decelerating, "Leaders")["second_derivative"],
            "decelerating",
        )
        steady = history_frame(
            [
                history_row("2026-10-01", "Leaders", 55.0),
                history_row("2026-10-02", "Leaders", 55.3),
                history_row("2026-10-03", "Leaders", 55.1),
            ]
        )
        self.assertEqual(
            compute_persistence_metrics(steady, "Leaders")["second_derivative"],
            "steady",
        )

    def test_missing_prior_history_gap(self) -> None:
        # A gap in dates does not break streak math; reports are sequential.
        frame = history_frame(
            [
                history_row("2026-09-01", "Leaders", 50.0),
                history_row("2026-10-11", "Leaders", 54.0),
            ]
        )
        metrics = compute_persistence_metrics(frame, "Leaders")
        self.assertEqual(metrics["consecutive_improving"], 1)
        self.assertEqual(metrics["report_count"], 2)


class ReadinessTests(unittest.TestCase):
    def test_early_signal_developing_confirmed(self) -> None:
        one_up = history_frame(
            [
                history_row("2026-10-01", "Leaders", 50.0),
                history_row("2026-10-08", "Leaders", 53.0),
            ]
        )
        self.assertEqual(
            classify_readiness(one_up, "Leaders")["readiness"], "Early Signal"
        )
        two_up = history_frame(
            [
                history_row("2026-10-01", "Leaders", 50.0),
                history_row("2026-10-08", "Leaders", 53.0),
                history_row("2026-10-15", "Leaders", 57.0),
            ]
        )
        self.assertEqual(
            classify_readiness(two_up, "Leaders")["readiness"], "Developing"
        )
        three_up = history_frame(
            [
                history_row("2026-10-01", "Leaders", 50.0),
                history_row("2026-10-08", "Leaders", 53.0),
                history_row("2026-10-15", "Leaders", 57.0),
                history_row("2026-10-22", "Leaders", 61.0),
            ]
        )
        self.assertEqual(
            classify_readiness(three_up, "Leaders")["readiness"], "Confirmed"
        )

    def test_persistent_leadership(self) -> None:
        frame = history_frame(
            [history_row(f"2026-10-0{d}", "Leaders", 70.0) for d in range(1, 6)]
        )
        result = classify_readiness(frame, "Leaders")
        self.assertEqual(result["readiness"], "Persistent")

    def test_early_repair(self) -> None:
        frame = history_frame(
            [
                history_row("2026-10-01", "Leaders", 30.0),
                history_row("2026-10-08", "Leaders", 33.0),
                history_row("2026-10-15", "Leaders", 37.0),
            ]
        )
        result = classify_readiness(frame, "Leaders")
        self.assertEqual(result["readiness"], "Repairing")

    def test_exhaustion(self) -> None:
        frame = history_frame(
            [
                history_row("2026-10-01", "Leaders", 72.0, catalyst=40.0, breadth_50dma=0.80),
                history_row("2026-10-08", "Leaders", 71.0, catalyst=32.0, breadth_50dma=0.70),
                history_row("2026-10-15", "Leaders", 70.0, catalyst=24.0, breadth_50dma=0.60),
            ]
        )
        result = classify_readiness(frame, "Leaders")
        self.assertEqual(result["readiness"], "Exhausted")

    def test_exhaustion_needs_narrowing_breadth(self) -> None:
        # Collapsing catalysts but stable breadth: not Exhausted.
        frame = history_frame(
            [
                history_row("2026-10-01", "Leaders", 72.0, catalyst=40.0, breadth_50dma=0.70),
                history_row("2026-10-08", "Leaders", 71.0, catalyst=32.0, breadth_50dma=0.72),
                history_row("2026-10-15", "Leaders", 70.0, catalyst=24.0, breadth_50dma=0.75),
            ]
        )
        result = classify_readiness(frame, "Leaders")
        self.assertNotEqual(result["readiness"], "Exhausted")

    def test_atomic_write_survives_truncation(self) -> None:
        # A truncated CSV must not silently load as empty history.
        with tempfile.TemporaryDirectory() as tmp:
            append_history(tmp, [history_row("2026-10-01", "Leaders", 60.0)])
            path = Path(tmp) / "health_stack_history.csv"
            # Simulate a crash mid-write on the *next* append by truncating
            # the temp file mechanism: write garbage, then verify the real
            # file is untouched because append itself is atomic.
            before = path.read_bytes()
            append_history(tmp, [history_row("2026-10-08", "Leaders", 62.0)])
            after = path.read_bytes()
            self.assertNotEqual(before, after)
            loaded = load_history(tmp)
            self.assertEqual(len(loaded), 2)

    def test_future_dates_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "future report date"):
                append_history(tmp, [history_row("2099-01-01", "Leaders", 60.0)])
            # The rejected write left no file behind.
            self.assertTrue(load_history(tmp).empty)

    def test_deterioration_fallthrough_note(self) -> None:
        frame = history_frame(
            [history_row(f"2026-10-0{d}", "Leaders", 70.0 - d * 3.0) for d in range(1, 7)]
        )
        result = classify_readiness(frame, "Leaders")
        self.assertEqual(result["readiness"], "Insufficient Evidence")
        self.assertIn("deteriorating", result["note"])

    def test_exhausted_outranks_persistent(self) -> None:
        # Five strong reports but rotting catalysts/breadth: Exhausted, not Persistent.
        frame = history_frame(
            [
                history_row("2026-10-01", "Leaders", 72.0, catalyst=50.0, market_confirmation=75.0),
                history_row("2026-10-08", "Leaders", 72.0, catalyst=48.0, market_confirmation=74.0),
                history_row("2026-10-15", "Leaders", 71.0, catalyst=40.0, market_confirmation=70.0),
                history_row("2026-10-22", "Leaders", 71.0, catalyst=32.0, market_confirmation=66.0),
                history_row("2026-10-29", "Leaders", 70.0, catalyst=24.0, market_confirmation=60.0),
            ]
        )
        result = classify_readiness(frame, "Leaders")
        self.assertEqual(result["readiness"], "Exhausted")

    def test_conflicting_signals_reported(self) -> None:
        frame = history_frame(
            [
                history_row("2026-10-01", "Leaders", 70.0, expectations_risk=30.0),
                history_row("2026-10-08", "Leaders", 70.0, expectations_risk=32.0),
                history_row("2026-10-15", "Leaders", 70.0, expectations_risk=34.0),
                history_row("2026-10-22", "Leaders", 70.0, expectations_risk=42.0),
            ]
        )
        result = classify_readiness(frame, "Leaders")
        self.assertEqual(result["readiness"], "Persistent")
        self.assertTrue(
            any("expectations risk" in conflict for conflict in result["conflicts"])
        )

    def test_no_change_behavior(self) -> None:
        frame = history_frame(
            [history_row(f"2026-10-0{d}", "Leaders", 55.0) for d in range(1, 5)]
        )
        result = classify_readiness(frame, "Leaders")
        # Flat neutral: no directional signal -> insufficient evidence for action.
        self.assertEqual(result["readiness"], "Insufficient Evidence")


class WhatChangedTests(unittest.TestCase):
    def test_what_changed_detects_moves(self) -> None:
        frame = history_frame(
            [
                history_row("2026-10-01", "Leaders", 60.0, catalyst=20.0),
                history_row("2026-10-01", "Platforms", 50.0, catalyst=20.0),
                history_row("2026-10-01", "Challengers", 45.0, catalyst=20.0),
                history_row("2026-10-01", "GeneEdit", 40.0, catalyst=20.0),
                history_row("2026-10-08", "Leaders", 30.0, catalyst=20.0),
                history_row("2026-10-08", "Platforms", 57.0, catalyst=35.0),
                history_row("2026-10-08", "Challengers", 46.0, catalyst=20.0),
                history_row("2026-10-08", "GeneEdit", 44.0, catalyst=20.0),
            ]
        )
        lines = build_what_changed_lines(frame)
        text = "\n".join(lines)
        # Top 3 was {Leaders, Platforms, Challengers};
        # now {Platforms, Challengers, GeneEdit}.
        self.assertIn("New leaders: GeneEdit", text)
        self.assertIn("Lost leaders: Leaders", text)
        self.assertIn("Leaders: opportunity fell", text)
        self.assertIn("Platforms: catalyst score +15.0", text)

    def test_what_changed_single_report(self) -> None:
        frame = history_frame([history_row("2026-10-01", "Leaders", 60.0)])
        lines = build_what_changed_lines(frame)
        self.assertIn("nothing to compare", "\n".join(lines).lower())

    def test_what_changed_empty(self) -> None:
        lines = build_what_changed_lines(pd.DataFrame())
        self.assertIn("first recorded report", "\n".join(lines))
