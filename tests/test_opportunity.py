"""Tests for Phase 2 Sleeve Opportunity Scores, trends, and ranking."""

from __future__ import annotations

import unittest

import pandas as pd

from glp1_watch.decision_weights import load_decision_weights
from glp1_watch.health_stack_sleeves import Sleeve
from glp1_watch.opportunity import compute_opportunity_scores


def make_sleeves() -> list[Sleeve]:
    return [
        Sleeve(name="Established GLP-1 Leaders", tickers=("LLY", "NVO"), required=True),
        Sleeve(name="AI Drug-Discovery Platforms", tickers=("RXRX", "SDGR"), required=True),
    ]


def frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def summaries() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"sleeve": "Established GLP-1 Leaders", "coverage": 1.0, "avg_return_3m": 0.20},
            {"sleeve": "AI Drug-Discovery Platforms", "coverage": 1.0, "avg_return_3m": -0.10},
        ]
    )


def component(sleeve: str, score: float, confidence: str = "High") -> dict:
    return {"sleeve": sleeve, "confidence": confidence}


class OpportunityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.weights = load_decision_weights()
        self.market = frame(
            [
                {
                    **component("Established GLP-1 Leaders", 0),
                    "market_confirmation_score": 80.0,
                    "avg_return_1m": 0.08,
                    "avg_return_3m": 0.20,
                },
                {
                    **component("AI Drug-Discovery Platforms", 0),
                    "market_confirmation_score": 30.0,
                    "avg_return_1m": -0.05,
                    "avg_return_3m": -0.10,
                },
            ]
        )
        self.structural = frame(
            [
                {**component("Established GLP-1 Leaders", 0), "structural_score": 70.0},
                {**component("AI Drug-Discovery Platforms", 0), "structural_score": 40.0},
            ]
        )
        self.catalyst = frame(
            [
                {**component("Established GLP-1 Leaders", 0), "catalyst_score": 60.0},
                {**component("AI Drug-Discovery Platforms", 0), "catalyst_score": 20.0},
            ]
        )
        self.risk = frame(
            [
                {**component("Established GLP-1 Leaders", 0), "expectations_risk_score": 30.0},
                {**component("AI Drug-Discovery Platforms", 0), "expectations_risk_score": 60.0},
            ]
        )

    def _compute(self) -> pd.DataFrame:
        return compute_opportunity_scores(
            self.market,
            self.structural,
            self.catalyst,
            self.risk,
            summaries(),
            make_sleeves(),
            self.weights,
        ).set_index("sleeve")

    def test_weighted_blend(self) -> None:
        result = self._compute()
        # Leaders: .35*80 + .25*70 + .20*60 + .20*(100-30) = 28+17.5+12+14 = 71.5
        self.assertAlmostEqual(
            result.loc["Established GLP-1 Leaders", "opportunity_score"], 71.5, places=1
        )
        # Platforms: .35*30 + .25*40 + .20*20 + .20*(100-60) = 10.5+10+4+8 = 32.5
        self.assertAlmostEqual(
            result.loc["AI Drug-Discovery Platforms", "opportunity_score"], 32.5, places=1
        )

    def test_ranking_order(self) -> None:
        result = compute_opportunity_scores(
            self.market,
            self.structural,
            self.catalyst,
            self.risk,
            summaries(),
            make_sleeves(),
            self.weights,
        )
        self.assertEqual(result.iloc[0]["sleeve"], "Established GLP-1 Leaders")
        self.assertEqual(result.iloc[0]["rank"], 1.0)

    def test_interpretation_bands(self) -> None:
        result = self._compute()
        self.assertEqual(
            result.loc["Established GLP-1 Leaders", "interpretation"], "Attractive"
        )
        self.assertEqual(
            result.loc["AI Drug-Discovery Platforms", "interpretation"],
            "Avoid broad exposure",
        )

    def test_trend_labels(self) -> None:
        result = self._compute()
        # Leaders: 71.5 -> Strong; 1M pace 0.08 >= 3M pace 0.0667 -> improving
        self.assertEqual(
            result.loc["Established GLP-1 Leaders", "trend"], "Strong and improving"
        )
        # Platforms: 32.5 -> Weak; 1M -0.05 < 3M pace -0.033 -> deteriorating
        self.assertEqual(
            result.loc["AI Drug-Discovery Platforms", "trend"], "Weak and deteriorating"
        )

    def test_recognition_gap_flag(self) -> None:
        structural = frame(
            [{**component("AI Drug-Discovery Platforms", 0), "structural_score": 65.0}]
        )
        catalyst = frame(
            [{**component("AI Drug-Discovery Platforms", 0), "catalyst_score": 65.0}]
        )
        market = frame(
            [
                {
                    **component("AI Drug-Discovery Platforms", 0),
                    "market_confirmation_score": 30.0,
                    "avg_return_1m": -0.02,
                    "avg_return_3m": -0.05,
                }
            ]
        )
        risk = frame(
            [{**component("AI Drug-Discovery Platforms", 0), "expectations_risk_score": 40.0}]
        )
        result = compute_opportunity_scores(
            market, structural, catalyst, risk, summaries(), make_sleeves(), self.weights
        ).set_index("sleeve")
        self.assertTrue(result.loc["AI Drug-Discovery Platforms", "recognition_gap"])

    def test_missing_component_gives_no_score(self) -> None:
        catalyst = frame(
            [{**component("Established GLP-1 Leaders", 0), "catalyst_score": float("nan")}]
        )
        result = compute_opportunity_scores(
            self.market,
            self.structural,
            catalyst,
            self.risk,
            summaries(),
            make_sleeves(),
            self.weights,
        ).set_index("sleeve")
        row = result.loc["Established GLP-1 Leaders"]
        self.assertTrue(pd.isna(row["opportunity_score"]))
        self.assertEqual(row["interpretation"], "Insufficient data")

    def test_low_coverage_gives_no_score(self) -> None:
        thin = pd.DataFrame(
            [
                {"sleeve": "Established GLP-1 Leaders", "coverage": 0.2, "avg_return_3m": 0.20},
                {"sleeve": "AI Drug-Discovery Platforms", "coverage": 1.0, "avg_return_3m": -0.10},
            ]
        )
        result = compute_opportunity_scores(
            self.market,
            self.structural,
            self.catalyst,
            self.risk,
            thin,
            make_sleeves(),
            self.weights,
        ).set_index("sleeve")
        self.assertTrue(pd.isna(result.loc["Established GLP-1 Leaders", "opportunity_score"]))

    def test_score_bounds(self) -> None:
        hot = frame(
            [
                {
                    **component("Established GLP-1 Leaders", 0),
                    "market_confirmation_score": 100.0,
                    "avg_return_1m": 0.5,
                    "avg_return_3m": 1.0,
                },
            ]
        )
        struct = frame(
            [{**component("Established GLP-1 Leaders", 0), "structural_score": 100.0}]
        )
        cat = frame([{**component("Established GLP-1 Leaders", 0), "catalyst_score": 100.0}])
        risk = frame(
            [{**component("Established GLP-1 Leaders", 0), "expectations_risk_score": 0.0}]
        )
        result = compute_opportunity_scores(
            hot, struct, cat, risk, summaries(), make_sleeves(), self.weights
        )
        scores = result["opportunity_score"].dropna()
        self.assertTrue(((scores >= 0) & (scores <= 100)).all())
        self.assertEqual(result.iloc[0]["interpretation"], "Strong opportunity")

    def test_strong_leader_weak_stack_scenario(self) -> None:
        # Leaders strong on market, platforms weak: ranking must separate them
        # and the weak sleeve must not inherit the leader's score.
        result = self._compute()
        leaders = result.loc["Established GLP-1 Leaders", "opportunity_score"]
        platforms = result.loc["AI Drug-Discovery Platforms", "opportunity_score"]
        self.assertGreater(leaders - platforms, 30)
