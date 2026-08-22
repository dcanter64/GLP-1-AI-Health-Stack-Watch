from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from glp1_watch.app import apply_source_filter, metric_text, report_paths, source_options
from glp1_watch.market_data import MarketSnapshot
from glp1_watch.market_data import build_performance_table
from glp1_watch.news import NewsSnapshot
from glp1_watch.pipeline import build_dashboard_snapshot, build_market_data_quality, format_percent_or_unknown, top_names


class AppHelperTests(unittest.TestCase):
    def test_source_options_includes_unknown_and_sorts(self) -> None:
        snapshot = {
            "articles": pd.DataFrame([{"source": "Reuters"}, {"source": ""}]),
            "rejected_articles": pd.DataFrame([{"source": "Bloomberg"}]),
        }

        self.assertEqual(source_options(snapshot), ["Bloomberg", "Reuters", "Unknown"])

    def test_apply_source_filter_respects_unknown_label(self) -> None:
        frame = pd.DataFrame([{"source": "Reuters", "title": "a"}, {"source": "", "title": "b"}])

        filtered_known = apply_source_filter(frame, ["Reuters"])
        filtered_unknown = apply_source_filter(frame, ["Unknown"])

        self.assertEqual(filtered_known["title"].tolist(), ["a"])
        self.assertEqual(filtered_unknown["title"].tolist(), ["b"])

    def test_format_percent_or_unknown_handles_missing_values(self) -> None:
        self.assertEqual(format_percent_or_unknown(float("nan")), "Unknown")
        self.assertEqual(format_percent_or_unknown(None), "Unknown")
        self.assertEqual(format_percent_or_unknown(-0.031), "-3.1%")



    def test_top_names_ignores_missing_returns(self) -> None:
        performance_table = pd.DataFrame(
            [
                {"ticker": "LLY", "return_3m": float("nan"), "group": "Core GLP-1 Leaders"},
                {"ticker": "NVO", "return_3m": 0.12, "group": "Core GLP-1 Leaders"},
            ]
        )

        self.assertEqual(top_names(performance_table, ["Core GLP-1 Leaders"]), "NVO (12.0%)")


    def test_metric_text_handles_missing_values(self) -> None:
        self.assertEqual(metric_text(None), "Unknown")
        self.assertEqual(metric_text(float("nan")), "Unknown")
        self.assertEqual(metric_text(0.123), "12.3%")

    def test_report_paths_returns_saved_markdown_reports(self) -> None:
        snapshot = {
            "written_files": [
                r"output\classified\ticker_performance_20260726T120000Z.csv",
                r"output\reports\glp1_ai_health_stack_watch_20260726T120000Z.md",
                r"output\validation\validation_20260726T120000Z.md",
            ]
        }

        self.assertEqual(
            report_paths(snapshot),
            [r"output\reports\glp1_ai_health_stack_watch_20260726T120000Z.md"],
        )

    def test_build_market_data_quality_flags_partial_runs(self) -> None:
        performance_table = pd.DataFrame(
            [
                {"ticker": "LLY", "price": 100.0, "return_3m": float("nan"), "rs_vs_xlv": float("nan"), "rs_vs_qqq": float("nan"), "rs_vs_spy": float("nan")},
                {"ticker": "NVO", "price": 80.0, "return_3m": 0.12, "rs_vs_xlv": 0.01, "rs_vs_qqq": 0.02, "rs_vs_spy": 0.03},
            ]
        )

        quality = build_market_data_quality(performance_table)

        self.assertEqual(quality["status"], "Partial")
        self.assertEqual(quality["return_3m_count"], 1)
        self.assertIn("Treat market confirmation as incomplete", quality["note"])

    def test_build_performance_table_computes_52w_drawdown_with_shorter_history(self) -> None:
        dates = pd.date_range("2026-01-01", periods=120, freq="D")
        columns = pd.MultiIndex.from_product([["Close"], ["LLY", "XLV", "QQQ", "SPY"]])
        prices = pd.DataFrame(
            {
                ("Close", "LLY"): list(range(100, 220)),
                ("Close", "XLV"): list(range(80, 200)),
                ("Close", "QQQ"): list(range(90, 210)),
                ("Close", "SPY"): list(range(95, 215)),
            },
            index=dates,
            columns=columns,
        )

        performance = build_performance_table(prices)
        lly = performance.loc[performance["ticker"] == "LLY"].iloc[0]

        self.assertEqual(lly["distance_from_52w_high"], 0.0)

class SnapshotControlTests(unittest.TestCase):
    @patch("glp1_watch.pipeline.fetch_news_snapshot")
    @patch("glp1_watch.pipeline.load_market_snapshot")
    def test_build_dashboard_snapshot_passes_lookback_and_refresh(
        self,
        mock_load_market_snapshot,
        mock_fetch_news_snapshot,
    ) -> None:
        mock_load_market_snapshot.return_value = MarketSnapshot(
            price_history=pd.DataFrame(),
            performance_table=pd.DataFrame(),
            layer_performance=pd.DataFrame(),
            ticker_diagnostics={"requested_count": 2, "active_tickers": ["LLY", "NVO"], "exceptions": []},
        )
        mock_fetch_news_snapshot.return_value = NewsSnapshot(
            articles=pd.DataFrame(),
            rejected_articles=pd.DataFrame(),
            theme_summary=pd.DataFrame(columns=["theme", "story_count", "avg_sentiment"]),
            sentiment_summary=pd.DataFrame(columns=["sentiment_label", "story_count"]),
            fetch_errors=[],
            raw_payload_path=None,
            total_fetched=0,
            rejected_by_relevance_gate=0,
            rejected_by_exclusion_filter=0,
            accepted_story_count=0,
            accepted_by_theme=pd.DataFrame(columns=["theme", "story_count"]),
            accepted_by_ticker=pd.DataFrame(columns=["ticker", "story_count"]),
        )

        snapshot = build_dashboard_snapshot(write_outputs=False, lookback_days=252, force_market_refresh=True)

        mock_load_market_snapshot.assert_called_once_with(lookback_days=252, force_refresh=True)
        self.assertEqual(snapshot["lookback_days"], 252)
        self.assertTrue(snapshot["force_market_refresh"])

    @patch("glp1_watch.pipeline.fetch_news_snapshot")
    @patch("glp1_watch.pipeline.load_market_snapshot")
    def test_build_dashboard_snapshot_tracks_qualified_story_stats_and_written_files(
        self,
        mock_load_market_snapshot,
        mock_fetch_news_snapshot,
    ) -> None:
        mock_load_market_snapshot.return_value = MarketSnapshot(
            price_history=pd.DataFrame(),
            performance_table=pd.DataFrame(
                [
                    {
                        "ticker": "LLY",
                        "return_3m": 0.22,
                        "above_50dma": True,
                        "above_200dma": True,
                        "distance_from_52w_high": -0.03,
                        "rs_vs_xlv": 0.11,
                        "rs_vs_qqq": 0.07,
                        "rs_vs_spy": 0.05,
                        "group": "Core GLP-1 Leaders",
                        "is_benchmark": False,
                    },
                    {
                        "ticker": "NVO",
                        "return_3m": 0.12,
                        "above_50dma": True,
                        "above_200dma": True,
                        "distance_from_52w_high": -0.04,
                        "rs_vs_xlv": 0.06,
                        "rs_vs_qqq": 0.03,
                        "rs_vs_spy": 0.02,
                        "group": "Core GLP-1 Leaders",
                        "is_benchmark": False,
                    },
                    {
                        "ticker": "XBI",
                        "return_3m": 0.01,
                        "above_50dma": False,
                        "above_200dma": False,
                        "distance_from_52w_high": -0.1,
                        "rs_vs_xlv": 0.0,
                        "rs_vs_qqq": 0.0,
                        "rs_vs_spy": 0.0,
                        "group": "Healthcare Benchmarks",
                        "is_benchmark": True,
                    },
                ]
            ),
            layer_performance=pd.DataFrame(
                [{"group": "Core GLP-1 Leaders", "return_5d": 0.01, "return_1m": 0.02, "return_3m": 0.03, "return_6m": 0.04}]
            ),
            ticker_diagnostics={"requested_count": 2, "active_tickers": ["LLY", "NVO"], "exceptions": []},
        )
        mock_fetch_news_snapshot.return_value = NewsSnapshot(
            articles=pd.DataFrame(
                [
                    {
                        "title": "Lilly expands Zepbound demand",
                        "tickers": "LLY",
                        "target_ticker": "LLY",
                        "theme": "GLP-1 Demand",
                        "relevance_score": 0.9,
                        "published_at": "2026-07-09T12:00:00+00:00",
                        "sentiment_score": 0.3,
                    },
                    {
                        "title": "Novo semaglutide update",
                        "tickers": "NVO",
                        "target_ticker": "NVO",
                        "theme": "GLP-1 Demand",
                        "relevance_score": 0.85,
                        "published_at": "2026-07-09T11:00:00+00:00",
                        "sentiment_score": 0.2,
                    },
                    {
                        "title": "Macro stock profile",
                        "tickers": "LLY",
                        "target_ticker": "LLY",
                        "theme": "Other",
                        "relevance_score": 0.99,
                        "published_at": "2026-07-09T10:00:00+00:00",
                        "sentiment_score": 0.0,
                    },
                ]
            ),
            rejected_articles=pd.DataFrame(),
            theme_summary=pd.DataFrame(
                [{"theme": "GLP-1 Demand", "story_count": 2, "avg_sentiment": 0.25}, {"theme": "Other", "story_count": 1, "avg_sentiment": 0.0}]
            ),
            sentiment_summary=pd.DataFrame(columns=["sentiment_label", "story_count"]),
            fetch_errors=[],
            raw_payload_path=None,
            total_fetched=3,
            rejected_by_relevance_gate=0,
            rejected_by_exclusion_filter=0,
            accepted_story_count=3,
            accepted_by_theme=pd.DataFrame([{"theme": "GLP-1 Demand", "story_count": 2}]),
            accepted_by_ticker=pd.DataFrame([{"ticker": "LLY", "story_count": 2}]),
        )

        snapshot = build_dashboard_snapshot(write_outputs=False)

        self.assertEqual(snapshot["news_stats"]["accepted"], 3)
        self.assertEqual(snapshot["news_stats"]["qualified"], 2)
        self.assertEqual(snapshot["accepted_ticker_summary"], "LLY (2)")
        self.assertIn("2 of 3 accepted stories qualified for scoring", snapshot["driver_interpretation"])
        self.assertEqual(snapshot["written_files"], [])


if __name__ == "__main__":
    unittest.main()



