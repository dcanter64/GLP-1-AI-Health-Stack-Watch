"""Tests for Phase 1 confirmation-state classification."""

from __future__ import annotations

import unittest

from glp1_watch.confirmation_state import (
    ALL_STATES,
    STATE_BROADLY_CONFIRMING,
    STATE_DETERIORATING,
    STATE_EARLY_REPAIR,
    STATE_FAILING,
    STATE_FRAGMENTING,
    STATE_INSUFFICIENT_EVIDENCE,
    STATE_LEADER_DEPENDENT,
    STATE_SELECTIVELY_CONFIRMING,
    assess_leader,
    assess_stack,
    build_contradiction,
    classify_confirmation_state,
)


def base_inputs(**overrides) -> dict:
    inputs = {
        "overall_score": 55.0,
        "confirming_count": 2,
        "deteriorating_count": 1,
        "breadth_50dma": 0.55,
        "concentration_verdict": "selective",
        "leader_status": "mixed",
        "market_data_quality": "High",
        "core_coverage": 0.9,
    }
    inputs.update(overrides)
    return inputs


class ConfirmationStateTests(unittest.TestCase):
    def test_all_eight_states_reachable(self) -> None:
        seen = {
            classify_confirmation_state(**base_inputs(market_data_quality="Low"))["state"],
            classify_confirmation_state(
                **base_inputs(
                    overall_score=75,
                    confirming_count=5,
                    breadth_50dma=0.7,
                    concentration_verdict="broad",
                )
            )["state"],
            classify_confirmation_state(
                **base_inputs(
                    concentration_verdict="leader-dependent",
                    leader_status="confirming",
                    confirming_count=1,
                )
            )["state"],
            classify_confirmation_state(**base_inputs(confirming_count=3))["state"],
            classify_confirmation_state(
                **base_inputs(overall_score=25, deteriorating_count=5, confirming_count=0)
            )["state"],
            classify_confirmation_state(
                **base_inputs(deteriorating_count=4, confirming_count=0)
            )["state"],
            classify_confirmation_state(
                **base_inputs(
                    overall_score=50,
                    deteriorating_count=0,
                    confirming_count=1,
                    breadth_50dma=0.6,
                )
            )["state"],
            classify_confirmation_state(
                **base_inputs(confirming_count=1, deteriorating_count=1)
            )["state"],
        }
        self.assertEqual(seen, set(ALL_STATES))

    def test_insufficient_evidence_on_low_data_quality(self) -> None:
        result = classify_confirmation_state(**base_inputs(market_data_quality="Low"))
        self.assertEqual(result["state"], STATE_INSUFFICIENT_EVIDENCE)
        self.assertIn("reason", result)

    def test_insufficient_evidence_on_thin_coverage(self) -> None:
        result = classify_confirmation_state(**base_inputs(core_coverage=0.3))
        self.assertEqual(result["state"], STATE_INSUFFICIENT_EVIDENCE)

    def test_broadly_confirming(self) -> None:
        result = classify_confirmation_state(
            **base_inputs(
                overall_score=75,
                confirming_count=5,
                breadth_50dma=0.7,
                concentration_verdict="broad",
            )
        )
        self.assertEqual(result["state"], STATE_BROADLY_CONFIRMING)

    def test_broadly_does_not_mask_leader_dependence(self) -> None:
        # Strong headline numbers with concentrated gains must not read as
        # broad health: the concentration signal wins.
        result = classify_confirmation_state(
            **base_inputs(
                overall_score=75,
                confirming_count=5,
                deteriorating_count=0,
                breadth_50dma=0.65,
                concentration_verdict="leader-dependent",
                leader_status="confirming",
            )
        )
        self.assertEqual(result["state"], STATE_LEADER_DEPENDENT)

    def test_broadly_requires_broad_concentration(self) -> None:
        # Same headline numbers with merely selective concentration fall
        # through to Selectively Confirming, not Broadly Confirming.
        result = classify_confirmation_state(
            **base_inputs(
                overall_score=75,
                confirming_count=5,
                breadth_50dma=0.65,
                concentration_verdict="selective",
            )
        )
        self.assertEqual(result["state"], STATE_SELECTIVELY_CONFIRMING)

    def test_leader_dependent_beats_selective(self) -> None:
        # 3 confirming sleeves would be "selectively confirming", but the
        # leader-dependent concentration takes precedence.
        result = classify_confirmation_state(
            **base_inputs(
                concentration_verdict="leader-dependent",
                leader_status="confirming",
                confirming_count=3,
            )
        )
        self.assertEqual(result["state"], STATE_LEADER_DEPENDENT)

    def test_failing(self) -> None:
        result = classify_confirmation_state(
            **base_inputs(overall_score=25, deteriorating_count=5, confirming_count=0)
        )
        self.assertEqual(result["state"], STATE_FAILING)

    def test_deteriorating(self) -> None:
        result = classify_confirmation_state(
            **base_inputs(deteriorating_count=4, confirming_count=0)
        )
        self.assertEqual(result["state"], STATE_DETERIORATING)

    def test_early_repair(self) -> None:
        result = classify_confirmation_state(
            **base_inputs(
                overall_score=50,
                deteriorating_count=0,
                confirming_count=1,
                breadth_50dma=0.6,
            )
        )
        self.assertEqual(result["state"], STATE_EARLY_REPAIR)

    def test_fragmenting_catch_all(self) -> None:
        result = classify_confirmation_state(
            **base_inputs(confirming_count=1, deteriorating_count=1)
        )
        self.assertEqual(result["state"], STATE_FRAGMENTING)


class AssessmentTests(unittest.TestCase):
    def test_assess_leader(self) -> None:
        self.assertEqual(assess_leader("confirming", 70.0), "Confirming")
        self.assertEqual(assess_leader("confirming", 50.0), "Mixed")
        self.assertEqual(assess_leader("deteriorating", 70.0), "Deteriorating")
        self.assertEqual(assess_leader("mixed", 30.0), "Deteriorating")
        self.assertEqual(assess_leader("insufficient data", 70.0), "Unknown")
        self.assertEqual(assess_leader("confirming", None), "Unknown")

    def test_assess_stack_covers_all_states(self) -> None:
        for state in ALL_STATES:
            self.assertNotEqual(assess_stack(state), "")
        self.assertEqual(assess_stack(STATE_BROADLY_CONFIRMING), "Broadly confirming")
        self.assertEqual(assess_stack(STATE_INSUFFICIENT_EVIDENCE), "Unknown")

    def test_contradiction_leader_dependent_state(self) -> None:
        # A confirming leader in a leader-dependent stack IS carrying the
        # stack; the risk is concentration, not absence.
        text = build_contradiction("Confirming", "Narrow - dependent on leaders")
        self.assertIn("fragile if leadership falters", text)
        self.assertNotIn("not carrying the stack", text)

    def test_contradiction_leader_vs_stack(self) -> None:
        text = build_contradiction("Confirming", "Fragmented")
        self.assertIn("not carrying the stack", text)
        text = build_contradiction("Confirming", "Broadly confirming")
        self.assertIn("agree", text)
        text = build_contradiction("Unknown", "Fragmented")
        self.assertIn("insufficient evidence", text)
        text = build_contradiction("Deteriorating", "Selectively confirming")
        self.assertIn("without its historical leader", text)
