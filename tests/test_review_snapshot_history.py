from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from review_snapshot_history import latest_validation_metrics, load_score_history, summarize_history, summarize_validation


class ReviewSnapshotHistoryTests(unittest.TestCase):
    def test_load_score_history_backfills_new_story_count_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "dashboard_scores.jsonl"
            history_path.write_text(
                "\n".join(
                    [
                        '{"as_of_date":"2026-07-08 15:06 UTC","overall_score":60.0,"stance":"Neutral","lly_ai_trade_score":70.0,"article_count":12}',
                        '{"as_of_date":"2026-07-09 15:06 UTC","overall_score":72.5,"stance":"Bullish","lly_ai_trade_score":91.0,"article_count":14,"accepted_story_count":14,"qualified_story_count":8}',
                    ]
                ),
                encoding="utf-8",
            )

            with patch("review_snapshot_history.HISTORY_PATH", history_path):
                history = load_score_history()

        self.assertEqual(len(history), 2)
        self.assertEqual(int(history.iloc[0]["accepted_story_count"]), 12)
        self.assertTrue(pd.isna(history.iloc[0]["qualified_story_count"]))
        self.assertEqual(int(history.iloc[1]["qualified_story_count"]), 8)

    def test_latest_validation_metrics_reads_latest_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            validation_dir = Path(tmpdir)
            (validation_dir / "validation_20260708T150641Z.md").write_text(
                "# Validation Audit\n\n- Accepted stories: 10\n",
                encoding="utf-8",
            )
            (validation_dir / "validation_20260709T150641Z.md").write_text(
                "# Validation Audit\n\n- Accepted stories: 14\n- Qualified scoring stories: 8\n- News confidence: High\n",
                encoding="utf-8",
            )

            with patch("review_snapshot_history.VALIDATION_DIR", validation_dir):
                metrics = latest_validation_metrics()

        self.assertEqual(metrics["file"], "validation_20260709T150641Z.md")
        self.assertEqual(metrics["Accepted stories"], "14")
        self.assertEqual(metrics["Qualified scoring stories"], "8")

    def test_summarize_history_reports_accepted_and_qualified_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "dashboard_scores.jsonl"
            history_path.write_text(
                "\n".join(
                    [
                        '{"as_of_date":"2026-07-08 15:06 UTC","overall_score":60.0,"stance":"Neutral","lly_ai_trade_score":70.0,"article_count":12,"accepted_story_count":12,"qualified_story_count":5}',
                        '{"as_of_date":"2026-07-09 15:06 UTC","overall_score":72.5,"stance":"Bullish","lly_ai_trade_score":91.0,"article_count":14,"accepted_story_count":14,"qualified_story_count":8}',
                    ]
                ),
                encoding="utf-8",
            )

            with patch("review_snapshot_history.HISTORY_PATH", history_path):
                history = load_score_history()

        summary = summarize_history(history)
        self.assertIn("Latest accepted-story count: 14", summary)
        self.assertIn("Latest qualified-story count: 8", summary)
        self.assertIn("Average qualified-story count: 6.5", summary)
        self.assertIn("Change vs prior snapshot: score +12.5, accepted stories +2", summary)
        self.assertIn("Change vs prior snapshot: qualified stories +3", summary)

    def test_summarize_validation_includes_scoring_coverage(self) -> None:
        metrics = {
            "file": "validation_20260709T150641Z.md",
            "Ticker rows": "38",
            "Total stories fetched": "248",
            "Stories rejected by relevance gate": "76",
            "Stories rejected by exclusion filter": "0",
            "Accepted stories": "85",
            "Qualified scoring stories": "34",
            "Scoring coverage": "34 of 85 accepted stories qualified for scoring",
            "News confidence": "Moderate",
            "Market data error": "None",
            "Ticker exceptions applied": "1",
        }

        summary = summarize_validation(metrics)
        self.assertIn("Qualified scoring stories: 34", summary)
        self.assertIn("Scoring coverage: 34 of 85 accepted stories qualified for scoring", summary)


if __name__ == "__main__":
    unittest.main()
