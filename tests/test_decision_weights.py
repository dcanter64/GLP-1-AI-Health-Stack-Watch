"""Tests for Phase 2 decision-weights loading and validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glp1_watch.decision_weights import (
    interpret_opportunity,
    load_decision_weights,
)


VALID_YAML = """\
opportunity_weights:
  market_confirmation: 0.35
  structural_thesis: 0.25
  catalyst: 0.20
  expectations_risk: 0.20
market_confirmation_weights:
  absolute_3m: 0.5
  rs_breadth: 0.5
expectations_risk_weights:
  acceleration: 1.0
interpretation_bands:
  - [80, "Strong opportunity"]
  - [0, "Broken or highly speculative"]
catalyst_saturation_per_category: 3
trend_strong_threshold: 65
trend_weak_threshold: 45
recognition_gap_structural_min: 60
recognition_gap_catalyst_min: 60
recognition_gap_market_max: 45
"""


def _write(body: str) -> Path:
    tmp_dir = tempfile.mkdtemp()
    path = Path(tmp_dir) / "weights.yaml"
    path.write_text(body, encoding="utf-8")
    return path


class DecisionWeightsTests(unittest.TestCase):
    def test_loads_bundled_config(self) -> None:
        weights = load_decision_weights()
        self.assertAlmostEqual(sum(weights.opportunity.values()), 1.0)
        self.assertAlmostEqual(sum(weights.market_confirmation.values()), 1.0)
        self.assertAlmostEqual(sum(weights.expectations_risk.values()), 1.0)
        self.assertEqual(weights.catalyst_saturation_per_category, 3)
        self.assertGreater(
            weights.trend_strong_threshold, weights.trend_weak_threshold
        )

    def test_interpretation_bands(self) -> None:
        weights = load_decision_weights()
        self.assertEqual(interpret_opportunity(85, weights), "Strong opportunity")
        self.assertEqual(interpret_opportunity(70, weights), "Attractive")
        self.assertEqual(interpret_opportunity(60, weights), "Selectively attractive")
        self.assertEqual(interpret_opportunity(50, weights), "Neutral")
        self.assertEqual(interpret_opportunity(40, weights), "Weak")
        self.assertEqual(interpret_opportunity(25, weights), "Avoid broad exposure")
        self.assertEqual(interpret_opportunity(10, weights), "Broken or highly speculative")

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_decision_weights("/nonexistent/weights.yaml")

    def test_rejects_negative_weight(self) -> None:
        body = VALID_YAML.replace("market_confirmation: 0.35", "market_confirmation: -0.35")
        with self.assertRaisesRegex(ValueError, "negative"):
            load_decision_weights(_write(body))

    def test_rejects_weights_not_summing_to_one(self) -> None:
        body = VALID_YAML.replace("catalyst: 0.20", "catalyst: 0.50")
        with self.assertRaisesRegex(ValueError, "sums to"):
            load_decision_weights(_write(body))

    def test_rejects_unsorted_bands(self) -> None:
        body = VALID_YAML.replace(
            '- [80, "Strong opportunity"]\n  - [0, "Broken or highly speculative"]',
            '- [0, "Broken or highly speculative"]\n  - [80, "Strong opportunity"]',
        )
        with self.assertRaisesRegex(ValueError, "sorted descending"):
            load_decision_weights(_write(body))

    def test_rejects_bands_not_covering_zero(self) -> None:
        body = VALID_YAML.replace('- [0, "Broken or highly speculative"]', '- [10, "Weak"]')
        with self.assertRaisesRegex(ValueError, "span 0-100"):
            load_decision_weights(_write(body))

    def test_rejects_bad_trend_thresholds(self) -> None:
        body = VALID_YAML.replace("trend_weak_threshold: 45", "trend_weak_threshold: 70")
        with self.assertRaisesRegex(ValueError, "trend_weak_threshold"):
            load_decision_weights(_write(body))

    def test_valid_minimal_config_loads(self) -> None:
        weights = load_decision_weights(_write(VALID_YAML))
        self.assertAlmostEqual(sum(weights.opportunity.values()), 1.0)
        self.assertEqual(interpret_opportunity(90, weights), "Strong opportunity")
        self.assertEqual(interpret_opportunity(50, weights), "Broken or highly speculative")
