"""Tests for the Phase 1 report section builder."""

from __future__ import annotations

import unittest

import pandas as pd

from glp1_watch.reporting import build_confirmation_structure_section


def make_summaries() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sleeve": "Established GLP-1 Leaders",
                "required": True,
                "avg_return_3m": 0.10,
                "status": "confirming",
            },
            {
                "sleeve": "Emerging GLP-1 Challengers",
                "required": True,
                "avg_return_3m": -0.05,
                "status": "deteriorating",
            },
            {
                "sleeve": "AI Infrastructure Enablers",
                "required": False,
                "avg_return_3m": 0.20,
                "status": "confirming",
            },
        ]
    )


def make_snapshot(**overrides) -> dict:
    snapshot = {
        "confirmation_state": "Selectively Confirming",
        "confirmation_reason": "3+ sleeves confirming without broad participation",
        "leader_assessment": "Mixed",
        "stack_assessment": "Selectively confirming",
        "leadership_concentration": {
            "verdict": "selective",
            "confirming_sleeves": ["Established GLP-1 Leaders"],
            "deteriorating_sleeves": ["Emerging GLP-1 Challengers"],
            "pct_above_50dma": 0.6,
            "pct_outperform_xlv": 0.55,
        },
        "sleeve_summaries": make_summaries(),
        "news_event_counts": {
            "unique_events": 4,
            "material_events": 1,
            "multi_source_events": 2,
        },
        "main_positive_evidence": "Leaders confirming",
        "main_negative_evidence": "Challengers weak",
        "main_contradiction": "No material contradiction",
    }
    snapshot.update(overrides)
    return snapshot


class ConfirmationSectionTests(unittest.TestCase):
    def test_legacy_snapshot_omits_section(self) -> None:
        # Snapshots predating Phase 1 keep byte-identical report output.
        self.assertEqual(build_confirmation_structure_section({}), [])
        self.assertEqual(build_confirmation_structure_section({"stance": "Neutral"}), [])

    def test_section_renders_expected_lines(self) -> None:
        lines = build_confirmation_structure_section(make_snapshot())
        text = "\n".join(lines)
        self.assertIn("## Health Stack Confirmation Structure", text)
        self.assertIn("Confirmation state: Selectively Confirming", text)
        self.assertIn("Confirming sleeves: 1 of 7 required", text)
        self.assertIn("Deteriorating sleeves: 1 of 7 required", text)
        self.assertIn("Strongest required sleeve: Established GLP-1 Leaders", text)
        self.assertIn("Weakest required sleeve: Emerging GLP-1 Challengers", text)
        self.assertIn("Supporting sleeve AI Infrastructure Enablers", text)
        self.assertIn("excluded from core breadth counts", text)
        self.assertIn("Unique news events: 4 (1 material, 2 multi-source)", text)

    def test_nan_values_render_as_na_not_nan(self) -> None:
        summaries = make_summaries()
        summaries.loc[:, "avg_return_3m"] = float("nan")
        lines = build_confirmation_structure_section(make_snapshot(sleeve_summaries=summaries))
        text = "\n".join(lines)
        self.assertNotIn("nan%", text)
        self.assertIn("n/a avg 3M", text)

    def test_insufficient_verdict_qualifies_breadth_line(self) -> None:
        snapshot = make_snapshot()
        snapshot["leadership_concentration"] = {
            "verdict": "insufficient data",
            "confirming_sleeves": [],
            "deteriorating_sleeves": [],
            "pct_above_50dma": float("nan"),
            "pct_outperform_xlv": float("nan"),
        }
        lines = build_confirmation_structure_section(snapshot)
        text = "\n".join(lines)
        self.assertIn("insufficient data", text)
        # Must not print a measured-looking 0%.
        self.assertNotIn("0% above 50DMA", text)
