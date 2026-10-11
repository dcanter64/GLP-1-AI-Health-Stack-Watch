from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from glp1_watch import reporting


def make_snapshot() -> dict:
    articles = pd.DataFrame(
        [
            {
                "title": "Lilly expands Zepbound manufacturing â€“ and whatâ€™s next",
                "source": "",
                "published_at": "2026-07-09T15:06:41+00:00",
                "theme": "Manufacturing / Supply",
                "sentiment_label": "Positive",
                "sentiment_score": 0.4,
                "tickers": "LLY",
                "url": "https://example.com/lly-story",
            }
        ]
    )
    rejected_articles = pd.DataFrame(
        [
            {
                "title": "Generic macro market roundup",
                "rejection_stage": "relevance_gate",
                "rejection_reason": "Missing healthcare evidence.",
            }
        ]
    )
    performance_table = pd.DataFrame([{"ticker": "LLY"}, {"ticker": "NVO"}])
    accepted_by_theme = pd.DataFrame([{"theme": "GLP-1 Demand", "story_count": 3}])
    accepted_by_ticker = pd.DataFrame([{"ticker": "LLY", "story_count": 2}])

    return {
        "as_of_date": "2026-07-09 15:06 UTC",
        "performance_table": performance_table,
        "articles": articles,
        "rejected_articles": rejected_articles,
        "accepted_by_theme": accepted_by_theme,
        "accepted_by_ticker": accepted_by_ticker,
        "fetch_errors": ["rss timeout"],
        "market_error": None,
        "ticker_diagnostics": {
            "exceptions": [
                {
                    "ticker": "EXAI",
                    "replacement": None,
                    "action": "drop",
                    "reason": "Went private.",
                }
            ]
        },
        "written_files": [Path("output/reports/example.md"), Path("output/validation/example.md")],
        "news_stats": {
            "total_fetched": 20,
            "rejected_by_relevance_gate": 5,
            "rejected_by_exclusion_filter": 1,
            "accepted": 14,
            "qualified": 8,
        },
        "stance": "Bullish",
        "overall_score": 72.5,
        "news_confidence": "High",
        "market_data_quality": {
            "status": "Partial",
            "ticker_rows": 2,
            "price_count": 1,
            "return_3m_count": 1,
            "rs_cell_count": 2,
            "rs_cell_total": 6,
            "note": "1 of 2 tickers have usable 3M returns.",
        },
        "interpretation": "The setup remains constructive.",
        "positive_drivers": ["LLY momentum (95.0/100)"],
        "negative_drivers": ["Competition (42.0/100)"],
        "lly_summary": "3M RS vs XLV 10.0%",
        "lly_trend_status": "Above 50DMA: Yes | Above 200DMA: Yes | Drawdown from 52W high: -3.0%",
        "lly_news_summary": "2 LLY-tagged stories",
        "lly_ai_trade_score": 91.0,
        "glp1_winners": "LLY (20.0%), NVO (15.0%)",
        "glp1_losers": "VKTX (-4.0%), ALT (-6.0%)",
        "glp1_themes": "GLP-1 Demand (3)",
        "ai_winners": "ABCL (10.0%), SDGR (8.0%)",
        "ai_losers": "CRSP (-5.0%), NTLA (-6.0%)",
        "ai_themes": "AI Drug Discovery (2)",
        "accepted_ticker_summary": "LLY (2)",
        "news_confidence_note": "Breadth is healthy.",
        "investor_interpretation": "Drivers remain supportive overall.",
    }


class ReportingTests(unittest.TestCase):
    def test_write_report_includes_key_sections_and_unknown_source_fallback(self) -> None:
        snapshot = make_snapshot()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch.object(reporting, "REPORTS_DIR", tmp_path / "reports"), patch.object(
                reporting, "CLASSIFIED_DIR", tmp_path / "classified"
            ), patch.object(reporting, "HISTORY_DIR", tmp_path / "history"), patch.object(
                reporting, "VALIDATION_DIR", tmp_path / "validation"
            ):
                path = reporting.write_report(snapshot, "20260709T150641Z")
                contents = path.read_text(encoding="utf-8")
                self.assertTrue(path.exists())
        self.assertIn("# GLP-1 AI Health Stack Watch", contents)
        self.assertIn("## Flywheel Score: Change Since Prior Run", contents)
        self.assertIn("- Prior snapshot: None available", contents)
        self.assertIn("- Qualified scoring stories: 8", contents)
        self.assertIn("- Market data quality: Partial", contents)
        self.assertIn("- Scoring coverage: 8 of 14 accepted stories qualified for scoring", contents)
        self.assertIn("Lilly expands Zepbound manufacturing - and what's next", contents)
        self.assertIn("Source: Unknown", contents)
        self.assertIn("Date: 2026-07-09 15:06 UTC", contents)
        self.assertIn("Drivers remain supportive overall.", contents)

    def test_write_report_includes_change_vs_prior_snapshot(self) -> None:
        snapshot = make_snapshot()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            history_dir = tmp_path / "history"
            history_dir.mkdir()
            (history_dir / "dashboard_scores.jsonl").write_text(
                '{"as_of_date":"2026-07-08 15:06 UTC","overall_score":70.0,"stance":"Neutral","lly_ai_trade_score":80.0,"article_count":10,"accepted_story_count":12,"qualified_story_count":6}\n',
                encoding="utf-8",
            )
            with patch.object(reporting, "REPORTS_DIR", tmp_path / "reports"), patch.object(
                reporting, "CLASSIFIED_DIR", tmp_path / "classified"
            ), patch.object(reporting, "HISTORY_DIR", history_dir), patch.object(
                reporting, "VALIDATION_DIR", tmp_path / "validation"
            ):
                path = reporting.write_report(snapshot, "20260709T150641Z")
                contents = path.read_text(encoding="utf-8")

        self.assertIn("- Prior snapshot: 2026-07-08 15:06 UTC | Neutral | score 70.0", contents)
        self.assertIn("- Score change: +2.5", contents)
        self.assertIn("- Stance change: Neutral -> Bullish", contents)
        self.assertIn("- Accepted stories change: +2", contents)
        self.assertIn("- Qualified scoring stories change: +2", contents)

    def test_select_key_stories_limits_repeated_legal_cluster_and_theme(self) -> None:
        rows = []
        for idx in range(5):
            rows.append(
                {
                    "title": f"Novo Nordisk seeks court order against Eli Lilly weight-loss ads part {idx}",
                    "theme": "GLP-1 Demand",
                    "tickers": "LLY, NVO",
                }
            )
        for idx in range(4):
            rows.append(
                {
                    "title": f"AI drug discovery platform update {idx}",
                    "theme": "AI Drug Discovery",
                    "tickers": "RXRX",
                }
            )
        articles = pd.DataFrame(rows)

        selected = reporting.select_key_stories(articles, limit=6)

        legal_count = selected["title"].str.contains("court order").sum()
        self.assertLessEqual(int(legal_count), 2)
        self.assertLessEqual(int((selected["theme"] == "GLP-1 Demand").sum()), 3)
        self.assertIn("AI Drug Discovery", selected["theme"].tolist())

    def test_write_validation_file_includes_errors_counts_and_exceptions(self) -> None:
        snapshot = make_snapshot()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch.object(reporting, "REPORTS_DIR", tmp_path / "reports"), patch.object(
                reporting, "CLASSIFIED_DIR", tmp_path / "classified"
            ), patch.object(reporting, "HISTORY_DIR", tmp_path / "history"), patch.object(
                reporting, "VALIDATION_DIR", tmp_path / "validation"
            ):
                path = reporting.write_validation_file(snapshot, "20260709T150641Z")
                contents = path.read_text(encoding="utf-8")
                self.assertTrue(path.exists())
        self.assertIn("- Accepted stories: 14", contents)
        self.assertIn("- Qualified scoring stories: 8", contents)
        self.assertIn("- Market data quality: Partial", contents)
        self.assertIn("- Scoring coverage: 8 of 14 accepted stories qualified for scoring", contents)
        self.assertIn("- RSS errors: 1", contents)
        self.assertIn("- EXAI | action=drop | reason=Went private.", contents)
        self.assertIn("- Generic macro market roundup | stage=relevance_gate | reason=Missing healthcare evidence.", contents)
        self.assertIn("- rss timeout", contents)

    def test_csv_and_history_writers_emit_expected_files(self) -> None:
        snapshot = make_snapshot()
        articles = snapshot["articles"]
        performance_table = pd.DataFrame([{"ticker": "LLY", "return_3m": 0.2}])

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch.object(reporting, "REPORTS_DIR", tmp_path / "reports"), patch.object(
                reporting, "CLASSIFIED_DIR", tmp_path / "classified"
            ), patch.object(reporting, "HISTORY_DIR", tmp_path / "history"), patch.object(
                reporting, "VALIDATION_DIR", tmp_path / "validation"
            ):
                performance_path = reporting.write_performance_csv(performance_table, "20260709T150641Z")
                articles_path = reporting.write_articles_csv(articles, "20260709T150641Z")
                history_path = reporting.append_score_history(snapshot)

                self.assertTrue(performance_path.exists())
                self.assertTrue(articles_path.exists())
                self.assertTrue(history_path.exists())
                performance_contents = performance_path.read_text(encoding="utf-8")
                articles_contents = articles_path.read_text(encoding="utf-8")
                history_lines = history_path.read_text(encoding="utf-8").strip().splitlines()

        self.assertIn("ticker,return_3m", performance_contents)
        self.assertIn("Lilly expands Zepbound manufacturing", articles_contents)
        entry = json.loads(history_lines[0])
        self.assertEqual(entry["as_of_date"], "2026-07-09 15:06 UTC")
        self.assertEqual(entry["overall_score"], 72.5)
        self.assertEqual(entry["article_count"], 1)
        self.assertEqual(entry["accepted_story_count"], 14)
        self.assertEqual(entry["qualified_story_count"], 8)

    def test_append_score_history_skips_same_minute_duplicate(self) -> None:
        snapshot = make_snapshot()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch.object(reporting, "REPORTS_DIR", tmp_path / "reports"), patch.object(
                reporting, "CLASSIFIED_DIR", tmp_path / "classified"
            ), patch.object(reporting, "HISTORY_DIR", tmp_path / "history"), patch.object(
                reporting, "VALIDATION_DIR", tmp_path / "validation"
            ):
                history_path = reporting.append_score_history(snapshot)
                duplicate = make_snapshot()
                duplicate["as_of_date"] = "2026-07-09 15:06 UTC"
                reporting.append_score_history(duplicate)
                history_lines = history_path.read_text(encoding="utf-8").strip().splitlines()

        self.assertEqual(len(history_lines), 1)

    def test_append_score_history_preserves_same_minute_metric_change(self) -> None:
        snapshot = make_snapshot()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch.object(reporting, "REPORTS_DIR", tmp_path / "reports"), patch.object(
                reporting, "CLASSIFIED_DIR", tmp_path / "classified"
            ), patch.object(reporting, "HISTORY_DIR", tmp_path / "history"), patch.object(
                reporting, "VALIDATION_DIR", tmp_path / "validation"
            ):
                history_path = reporting.append_score_history(snapshot)
                changed = make_snapshot()
                changed["as_of_date"] = "2026-07-09 15:06 UTC"
                changed["overall_score"] = 73.0
                reporting.append_score_history(changed)
                history_lines = history_path.read_text(encoding="utf-8").strip().splitlines()

        self.assertEqual(len(history_lines), 2)

if __name__ == "__main__":
    unittest.main()





