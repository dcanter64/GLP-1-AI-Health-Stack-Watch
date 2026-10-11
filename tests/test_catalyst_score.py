"""Tests for the Phase 2 Catalyst Score."""

from __future__ import annotations

import unittest

import pandas as pd

from glp1_watch.catalyst_score import compute_catalyst_score
from glp1_watch.health_stack_sleeves import Sleeve


def make_sleeves() -> list[Sleeve]:
    return [
        Sleeve(name="Established GLP-1 Leaders", tickers=("LLY", "NVO"), required=True),
        Sleeve(name="AI Drug-Discovery Platforms", tickers=("RXRX", "SDGR"), required=True),
    ]


def make_event(event_id: str, tickers: str, theme: str) -> dict:
    return {
        "event_id": event_id,
        "tickers": tickers,
        "themes": theme,
        "story_count": 2,
        "independent_sources": 2,
        "max_relevance": 0.8,
        "material": True,
    }


def articles_for(events: list[str], sentiments: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event_id": event_id,
                "sentiment_score": sentiment,
                "title": f"story {i}",
            }
            for i, (event_id, sentiment) in enumerate(zip(events, sentiments))
        ]
    )


class CatalystScoreTests(unittest.TestCase):
    def test_events_drive_score(self) -> None:
        events = pd.DataFrame(
            [
                make_event("EVT-001", "LLY", "GLP-1 Demand"),
                make_event("EVT-002", "LLY, NVO", "Lilly M&A / IP Acquisition"),
                make_event("EVT-003", "NVO", "Obesity Policy / Pricing"),
            ]
        )
        articles = articles_for(["EVT-001", "EVT-002", "EVT-003"], [0.5, 0.4, 0.3])
        result = compute_catalyst_score(events, articles, make_sleeves()).set_index("sleeve")
        leaders = result.loc["Established GLP-1 Leaders"]
        # 4 categories at 1/3 saturation each -> 100 * (4/3) / 6 = 22.2
        self.assertAlmostEqual(leaders["catalyst_score"], 100 * 4 / 18, places=1)
        self.assertEqual(leaders["confidence"], "High")
        # Untouched sleeve scores zero at Low confidence.
        platforms = result.loc["AI Drug-Discovery Platforms"]
        self.assertEqual(platforms["catalyst_score"], 0.0)
        self.assertEqual(platforms["confidence"], "Low")

    def test_raw_count_does_not_dominate(self) -> None:
        # Ten commercial events saturate one category: breadth still matters.
        events = pd.DataFrame(
            [make_event(f"EVT-{i:03d}", "LLY", "GLP-1 Demand") for i in range(1, 11)]
        )
        articles = articles_for([f"EVT-{i:03d}" for i in range(1, 11)], [0.5] * 10)
        result = compute_catalyst_score(events, articles, make_sleeves()).set_index("sleeve")
        score = result.loc["Established GLP-1 Leaders", "catalyst_score"]
        # Only commercial saturates: 1/6 categories -> ~16.7, not ~100.
        self.assertAlmostEqual(score, 100 / 6, places=1)

    def test_negative_sentiment_subtracts(self) -> None:
        events = pd.DataFrame(
            [
                make_event("EVT-001", "LLY", "GLP-1 Demand"),
                make_event("EVT-002", "LLY", "Regulatory Risk"),
            ]
        )
        articles = articles_for(["EVT-001", "EVT-002"], [0.5, -0.5])
        result = compute_catalyst_score(events, articles, make_sleeves()).set_index("sleeve")
        counts = result.loc["Established GLP-1 Leaders", "category_counts"]
        self.assertEqual(counts["commercial"], 1)
        self.assertEqual(counts["regulatory"], -1)
        # regulatory net -1 clips to 0 contribution; commercial at 1/3 saturation.
        self.assertAlmostEqual(
            result.loc["Established GLP-1 Leaders", "catalyst_score"], 100 / 18, places=1
        )

    def test_unmapped_theme_contributes_nothing(self) -> None:
        events = pd.DataFrame([make_event("EVT-001", "LLY", "GLP-1 Competition")])
        articles = articles_for(["EVT-001"], [0.5])
        result = compute_catalyst_score(events, articles, make_sleeves()).set_index("sleeve")
        self.assertEqual(result.loc["Established GLP-1 Leaders", "catalyst_score"], 0.0)

    def test_unsigned_event_does_not_inflate_confidence(self) -> None:
        # A mapped-theme event with no articles (sign 0) moves no category and
        # must not lift confidence to Medium on a 0.0 score.
        events = pd.DataFrame([make_event("EVT-001", "LLY", "GLP-1 Demand")])
        result = compute_catalyst_score(
            events, pd.DataFrame(), make_sleeves()
        ).set_index("sleeve")
        row = result.loc["Established GLP-1 Leaders"]
        self.assertEqual(row["catalyst_score"], 0.0)
        self.assertEqual(row["confidence"], "Low")

    def test_empty_events(self) -> None:
        result = compute_catalyst_score(
            pd.DataFrame(), pd.DataFrame(), make_sleeves()
        ).set_index("sleeve")
        self.assertEqual(result.loc["Established GLP-1 Leaders", "catalyst_score"], 0.0)
        self.assertEqual(result.loc["Established GLP-1 Leaders", "confidence"], "Low")
