from __future__ import annotations

import unittest

import pandas as pd

from glp1_watch.pipeline import build_news_confidence
from glp1_watch.scoring import (
    compute_lly_ai_trade_components,
    compute_lly_ai_trade_score,
    compute_score_snapshot,
    qualified_scoring_articles,
)


class ScoringTests(unittest.TestCase):
    def test_compute_score_snapshot_with_empty_market_data(self) -> None:
        snapshot = compute_score_snapshot(pd.DataFrame(), pd.DataFrame())
        self.assertEqual(snapshot.overall_score, 0.0)
        self.assertEqual(snapshot.stance, "Bearish")
        self.assertEqual(snapshot.lly_ai_trade_score, 0.0)
        self.assertFalse(snapshot.component_scores.empty)


    def test_compute_score_snapshot_does_not_reward_missing_market_values(self) -> None:
        performance_table = pd.DataFrame(
            [
                {
                    "ticker": "LLY",
                    "return_3m": float("nan"),
                    "distance_from_52w_high": float("nan"),
                    "above_50dma": False,
                    "above_200dma": False,
                    "rs_vs_xlv": float("nan"),
                    "rs_vs_qqq": float("nan"),
                    "group": "Core GLP-1 Leaders",
                    "is_benchmark": False,
                },
                {
                    "ticker": "NVO",
                    "return_3m": float("nan"),
                    "group": "Core GLP-1 Leaders",
                    "is_benchmark": False,
                },
                {
                    "ticker": "XBI",
                    "return_3m": float("nan"),
                    "group": "Healthcare Benchmarks",
                    "is_benchmark": True,
                },
            ]
        )

        snapshot = compute_score_snapshot(performance_table, pd.DataFrame())

        component_scores = snapshot.component_scores.set_index("component")["score"]

        self.assertEqual(component_scores["LLY price momentum"], 0.0)
        self.assertEqual(component_scores["LLY relative strength vs XLV"], 0.0)
        self.assertEqual(component_scores["LLY vs NVO pair-relative strength"], 0.0)
        self.assertEqual(component_scores["Biotech risk appetite"], 0.0)
        self.assertEqual(snapshot.lly_ai_trade_score, 0.0)
        self.assertLess(snapshot.overall_score, 20.0)
    def test_compute_lly_ai_trade_score_with_market_and_news_support(self) -> None:
        performance_table = pd.DataFrame(
            [
                {
                    "ticker": "LLY",
                    "return_3m": 0.22,
                    "distance_from_52w_high": -0.03,
                    "above_50dma": True,
                    "above_200dma": True,
                    "rs_vs_xlv": 0.11,
                    "rs_vs_qqq": 0.07,
                },
                {
                    "ticker": "NVO",
                    "return_3m": 0.12,
                    "distance_from_52w_high": -0.08,
                    "above_50dma": True,
                    "above_200dma": True,
                    "rs_vs_xlv": 0.05,
                    "rs_vs_qqq": 0.02,
                },
            ]
        )
        articles_df = pd.DataFrame(
            [
                {"tickers": "LLY", "sentiment_score": 0.6, "theme": "GLP-1 Demand", "title": "story-1"},
                {"tickers": "LLY, NVO", "sentiment_score": 0.4, "theme": "AI Drug Discovery", "title": "story-2"},
            ]
        )

        score = compute_lly_ai_trade_score(performance_table, articles_df)
        self.assertGreater(score, 60.0)

    def test_lly_pair_relative_score_is_capped_when_broad_rs_is_negative(self) -> None:
        performance = pd.DataFrame(
            [
                {
                    "ticker": "LLY",
                    "return_3m": -0.05,
                    "distance_from_52w_high": -0.08,
                    "above_50dma": True,
                    "above_200dma": True,
                    "rs_vs_xlv": -0.06,
                    "rs_vs_qqq": -0.05,
                    "rs_vs_spy": -0.04,
                },
                {"ticker": "NVO", "return_3m": -0.25},
            ]
        )

        components = compute_lly_ai_trade_components(performance, pd.DataFrame())
        pair = components.set_index("component").loc["LLY vs NVO pair-relative strength"]

        self.assertEqual(pair["score"], 50.0)
        self.assertIn("Capped at neutral", pair["note"])

    def test_lly_component_budget_is_exactly_100_without_hidden_clamp(self) -> None:
        performance = pd.DataFrame(
            [
                {
                    "ticker": "LLY",
                    "return_3m": 0.30,
                    "distance_from_52w_high": 0.0,
                    "above_50dma": True,
                    "above_200dma": True,
                    "rs_vs_xlv": 0.15,
                    "rs_vs_qqq": 0.15,
                    "rs_vs_spy": 0.15,
                },
                {"ticker": "NVO", "return_3m": -0.20},
            ]
        )
        articles = pd.DataFrame(
            [
                {
                    "theme": "GLP-1 Demand",
                    "tickers": "LLY",
                    "target_ticker": "LLY",
                    "relevance_score": 1.0,
                    "published_at": "2026-10-01",
                    "sentiment_score": 0.5,
                }
                for _ in range(4)
            ]
        )
        components = compute_lly_ai_trade_components(performance, articles)
        self.assertEqual(components["max_points"].sum(), 100.0)
        self.assertLessEqual(components["contribution"].sum(), 100.0)
        self.assertEqual(
            compute_lly_ai_trade_score(performance, articles),
            round(components["contribution"].sum(), 1),
        )

    def test_qualified_scoring_articles_caps_per_primary_ticker_theme_and_excludes_other(self) -> None:
        articles_df = pd.DataFrame(
            [
                {
                    "tickers": "LLY",
                    "target_ticker": "LLY",
                    "theme": "GLP-1 Demand",
                    "relevance_score": 0.9 - (idx * 0.01),
                    "published_at": f"2026-07-{9-idx:02d}T12:00:00+00:00",
                    "sentiment_score": 0.2,
                }
                for idx in range(6)
            ]
            + [
                {
                    "tickers": "LLY",
                    "target_ticker": "LLY",
                    "theme": "AI Drug Discovery",
                    "relevance_score": 0.7 - (idx * 0.01),
                    "published_at": f"2026-06-{30-idx:02d}T12:00:00+00:00",
                    "sentiment_score": 0.1,
                }
                for idx in range(3)
            ]
            + [
                {
                    "tickers": "LLY",
                    "target_ticker": "LLY",
                    "theme": "Other",
                    "relevance_score": 0.95,
                    "published_at": "2026-07-09T13:00:00+00:00",
                    "sentiment_score": 0.0,
                }
            ]
        )

        qualified = qualified_scoring_articles(articles_df)
        self.assertEqual(len(qualified), 4)
        self.assertTrue((qualified["theme"] != "Other").all())
        theme_counts = qualified["theme"].value_counts().to_dict()
        self.assertEqual(theme_counts.get("GLP-1 Demand"), 2)
        self.assertEqual(theme_counts.get("AI Drug Discovery"), 2)

    def test_build_news_confidence_uses_qualified_story_count(self) -> None:
        articles_df = pd.DataFrame(
            [
                {
                    "tickers": "LLY",
                    "target_ticker": "LLY",
                    "theme": "GLP-1 Demand",
                    "relevance_score": 0.9,
                    "published_at": "2026-07-09T12:00:00+00:00",
                    "sentiment_score": 0.2,
                },
                {
                    "tickers": "NVO",
                    "target_ticker": "NVO",
                    "theme": "AI Drug Discovery",
                    "relevance_score": 0.8,
                    "published_at": "2026-07-09T11:00:00+00:00",
                    "sentiment_score": 0.1,
                },
                {
                    "tickers": "CRSP",
                    "target_ticker": "CRSP",
                    "theme": "Other",
                    "relevance_score": 0.99,
                    "published_at": "2026-07-09T10:00:00+00:00",
                    "sentiment_score": 0.0,
                },
            ]
        )

        confidence, note = build_news_confidence(articles_df)
        self.assertEqual(confidence, "Low")
        self.assertIn("qualified non-Other stories", note)


if __name__ == "__main__":
    unittest.main()



