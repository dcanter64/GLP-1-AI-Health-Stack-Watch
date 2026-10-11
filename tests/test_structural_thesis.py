"""Tests for the Phase 2 Structural Thesis Score."""

from __future__ import annotations

import unittest

import pandas as pd

from glp1_watch.health_stack_sleeves import Sleeve
from glp1_watch.structural_thesis import compute_structural_thesis


def make_sleeves() -> list[Sleeve]:
    return [
        Sleeve(name="Established GLP-1 Leaders", tickers=("LLY", "NVO"), required=True),
        Sleeve(name="AI Drug-Discovery Platforms", tickers=("RXRX", "SDGR"), required=True),
    ]


def make_article(tickers: str, theme: str, sentiment: float) -> dict:
    return {
        "title": f"{theme} story",
        "tickers": tickers,
        "theme": theme,
        "sentiment_score": sentiment,
        "relevance_score": 0.8,
    }


class StructuralThesisTests(unittest.TestCase):
    def test_positive_evidence_scores_high(self) -> None:
        articles = pd.DataFrame(
            [make_article("LLY", "GLP-1 Demand", 0.6) for _ in range(12)]
        )
        result = compute_structural_thesis(articles, make_sleeves()).set_index("sleeve")
        score = result.loc["Established GLP-1 Leaders", "structural_score"]
        self.assertGreater(score, 80)
        self.assertEqual(result.loc["Established GLP-1 Leaders", "confidence"], "High")

    def test_negative_evidence_scores_low(self) -> None:
        articles = pd.DataFrame(
            [make_article("LLY", "Side Effects / Safety", -0.6) for _ in range(12)]
        )
        result = compute_structural_thesis(articles, make_sleeves()).set_index("sleeve")
        score = result.loc["Established GLP-1 Leaders", "structural_score"]
        self.assertLess(score, 20)

    def test_no_evidence_is_neutral_not_zero(self) -> None:
        result = compute_structural_thesis(pd.DataFrame(), make_sleeves()).set_index("sleeve")
        row = result.loc["Established GLP-1 Leaders"]
        self.assertEqual(row["structural_score"], 50.0)
        self.assertEqual(row["confidence"], "Low")

    def test_mixed_theme_counts_by_sentiment_sign(self) -> None:
        articles = pd.DataFrame(
            [
                make_article("LLY", "Obesity Policy / Pricing", 0.5),
                make_article("LLY", "Obesity Policy / Pricing", 0.5),
                make_article("LLY", "Obesity Policy / Pricing", 0.5),
                make_article("LLY", "Obesity Policy / Pricing", 0.5),
                make_article("NVO", "Obesity Policy / Pricing", -0.5),
            ]
        )
        result = compute_structural_thesis(articles, make_sleeves()).set_index("sleeve")
        # 4 pos, 1 neg -> 100 * (4 - 1 + 2) / (5 + 4) = 55.6 > 50
        self.assertGreater(result.loc["Established GLP-1 Leaders", "structural_score"], 50)

    def test_unrelated_sleeve_unaffected(self) -> None:
        articles = pd.DataFrame(
            [make_article("LLY", "GLP-1 Demand", 0.6) for _ in range(12)]
        )
        result = compute_structural_thesis(articles, make_sleeves()).set_index("sleeve")
        # AI Drug Discovery tickers untouched: neutral at Low confidence.
        row = result.loc["AI Drug-Discovery Platforms"]
        self.assertEqual(row["structural_score"], 50.0)
        self.assertEqual(row["confidence"], "Low")

    def test_score_bounds(self) -> None:
        articles = pd.DataFrame(
            [make_article("LLY", "GLP-1 Demand", 1.0) for _ in range(100)]
            + [make_article("NVO", "Side Effects / Safety", -1.0) for _ in range(100)]
        )
        result = compute_structural_thesis(articles, make_sleeves())
        self.assertTrue(((result["structural_score"] >= 0) & (result["structural_score"] <= 100)).all())
