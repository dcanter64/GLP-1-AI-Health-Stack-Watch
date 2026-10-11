"""Tests for the Phase 2 Health Stack Opportunity Ranking report section."""

from __future__ import annotations

import unittest

import pandas as pd

from glp1_watch.reporting import build_opportunity_ranking_section


def ranking_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "rank": 1.0,
                "sleeve": "Established GLP-1 Leaders",
                "required": True,
                "opportunity_score": 71.5,
                "interpretation": "Attractive",
                "trend": "Strong and improving",
                "recognition_gap": False,
                "structural_score": 70.0,
                "market_confirmation_score": 80.0,
                "catalyst_score": 60.0,
                "expectations_risk_score": 30.0,
            },
            {
                "rank": 2.0,
                "sleeve": "AI Infrastructure Enablers",
                "required": False,
                "opportunity_score": 55.0,
                "interpretation": "Selectively attractive",
                "trend": "Neutral and improving",
                "recognition_gap": True,
                "structural_score": 65.0,
                "market_confirmation_score": 40.0,
                "catalyst_score": 65.0,
                "expectations_risk_score": 50.0,
            },
            {
                "rank": float("nan"),
                "sleeve": "Health Data and Clinical AI",
                "required": True,
                "opportunity_score": float("nan"),
                "interpretation": "Insufficient data",
                "trend": "Unknown",
                "recognition_gap": False,
                "structural_score": float("nan"),
                "market_confirmation_score": float("nan"),
                "catalyst_score": float("nan"),
                "expectations_risk_score": float("nan"),
            },
        ]
    )


class OpportunitySectionTests(unittest.TestCase):
    def test_section_renders_table(self) -> None:
        lines = build_opportunity_ranking_section({"opportunity_ranking": ranking_frame()})
        text = "\n".join(lines)
        self.assertIn("## Health Stack Opportunity Ranking", text)
        self.assertIn("| Rank | Sleeve | Opportunity Score |", text)
        self.assertIn("Established GLP-1 Leaders", text)
        self.assertIn("71.5", text)
        # Supporting sleeve is flagged.
        self.assertIn("AI Infrastructure Enablers (supporting)", text)
        # Missing scores render as n/a, not nan%.
        self.assertIn("n/a", text)
        self.assertNotIn("nan", text.lower().replace("n/a", ""))

    def test_section_interprets_evidence(self) -> None:
        lines = build_opportunity_ranking_section({"opportunity_ranking": ranking_frame()})
        text = "\n".join(lines)
        self.assertIn("Strongest evidence: Established GLP-1 Leaders", text)
        self.assertIn("Recognition gap: AI Infrastructure Enablers", text)
        self.assertIn("no allocation tiers", text)

    def test_section_handles_missing_ranking(self) -> None:
        lines = build_opportunity_ranking_section({})
        self.assertIn("## Health Stack Opportunity Ranking", "\n".join(lines))
        self.assertIn("unavailable", "\n".join(lines))

    def test_weakest_evidence_uses_required_sleeves_only(self) -> None:
        # Weakest-evidence line must come from required sleeves, not the
        # supporting sleeve.
        lines = build_opportunity_ranking_section({"opportunity_ranking": ranking_frame()})
        text = "\n".join(lines)
        self.assertNotIn("Weakest evidence: AI Infrastructure Enablers", text)
