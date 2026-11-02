from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from glp1_watch import news
from glp1_watch.news import build_articles_frame, classify_theme, derive_source_name, keyword_candidate_has_evidence, score_sentiment, yahoo_ticker_rss_url


def _published_at(days_ago: float) -> str:
    """Fixture timestamp relative to now.

    Relevance tests use fixed 2026-07 dates that aged out of the 21-day news
    window, so every fixture was rejected as stale before classification ran.
    Relative dates keep these tests about classification, not the calendar.
    """
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


class NewsClassificationTests(unittest.TestCase):
    def test_fetch_failures_are_reported_in_snapshot_diagnostics(self) -> None:
        with patch.object(news, "NEWS_QUERIES", ["test query"]), patch.object(
            news, "NEWS_TICKERS", ["LLY"]
        ), patch.object(
            news.requests,
            "get",
            side_effect=news.requests.Timeout("simulated timeout"),
        ):
            snapshot = news.fetch_news_snapshot(write_raw_json=False)

        self.assertEqual(len(snapshot.fetch_errors), 2)
        self.assertIn("test query", snapshot.fetch_errors[0])
        self.assertIn("ticker:LLY", snapshot.fetch_errors[1])
        self.assertTrue(all("timeout" in error.lower() for error in snapshot.fetch_errors))

    def test_classify_theme_for_glp1_story(self) -> None:
        theme = classify_theme("Eli Lilly reported positive tirzepatide obesity trial data for Zepbound demand.")
        self.assertEqual(theme, "GLP-1 Demand")

    def test_build_articles_frame_accepts_specific_healthcare_story(self) -> None:
        accepted, rejected = build_articles_frame(
            [
                {
                    "query": "Eli Lilly Zepbound obesity",
                    "feed_url": "https://example.com/rss",
                    "title": "Eli Lilly says Zepbound obesity demand rises after positive trial update",
                    "summary": "The tirzepatide program showed positive data and supply expansion for obesity care.",
                    "url": "https://example.com/story-1",
                    "source": "Reuters",
                    "rss_metadata": "Reuters | Healthcare",
                    "published_at": _published_at(2),
                }
            ]
        )

        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(rejected), 0)
        self.assertEqual(accepted.iloc[0]["theme"], "GLP-1 Demand")
        self.assertIn("LLY", accepted.iloc[0]["tickers"])
        self.assertGreaterEqual(float(accepted.iloc[0]["relevance_score"]), 0.45)

    def test_build_articles_frame_rejects_generic_ai_story(self) -> None:
        accepted, rejected = build_articles_frame(
            [
                {
                    "query": "Eli Lilly AI drug discovery",
                    "feed_url": "https://example.com/rss",
                    "title": "Amazon raises bond sale for AI infrastructure",
                    "summary": "The company is investing in generic AI expansion and cloud capex.",
                    "url": "https://example.com/story-2",
                    "source": "Yahoo Finance",
                    "rss_metadata": "Yahoo Finance | Technology",
                    "published_at": _published_at(2),
                }
            ]
        )

        self.assertEqual(len(accepted), 0)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected.iloc[0]["rejection_stage"], "relevance_gate")
        self.assertLess(float(rejected.iloc[0]["relevance_score"]), 0.45)

    def test_ticker_feed_context_boosts_relevant_company_story(self) -> None:
        accepted, rejected = build_articles_frame(
            [
                {
                    "query": "ticker:LLY",
                    "feed_url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=LLY",
                    "feed_kind": "ticker",
                    "target_ticker": "LLY",
                    "title": "Eli Lilly expands Zepbound manufacturing capacity",
                    "summary": "The company said demand remains strong for its obesity drug.",
                    "url": "https://example.com/story-3",
                    "source": "Reuters",
                    "rss_metadata": "Reuters | Healthcare",
                    "published_at": _published_at(2),
                }
            ]
        )

        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(rejected), 0)
        self.assertEqual(accepted.iloc[0]["feed_kind"], "ticker")
        self.assertEqual(accepted.iloc[0]["target_ticker"], "LLY")

    def test_keyword_candidate_prefilter_rejects_unrelated_search_result(self) -> None:
        article = {
            "query": "Eli Lilly Zepbound obesity",
            "title": "Wall Street ticks up as tech hopes offset Middle East worries",
            "summary": "",
            "source": "Reuters",
            "rss_metadata": "Reuters",
        }

        self.assertFalse(keyword_candidate_has_evidence(article))

    def test_keyword_candidate_prefilter_keeps_query_overlap(self) -> None:
        article = {
            "query": "Eli Lilly Zepbound obesity",
            "title": "Eli Lilly expands Zepbound access",
            "summary": "",
            "source": "Reuters",
            "rss_metadata": "Reuters",
        }

        self.assertTrue(keyword_candidate_has_evidence(article))

    def test_yahoo_ticker_rss_url_uses_headline_endpoint(self) -> None:
        self.assertEqual(
            yahoo_ticker_rss_url("LLY"),
            "https://feeds.finance.yahoo.com/rss/2.0/headline?s=LLY&region=US&lang=en-US",
        )

    def test_derive_source_name_maps_known_domains(self) -> None:
        self.assertEqual(
            derive_source_name("https://www.thestreet.com/health/gallup-ozempic-glp-1-use-soars?.tsrc=rss"),
            "TheStreet",
        )
        self.assertEqual(
            derive_source_name("https://www.proactiveinvestors.com/companies/news/example"),
            "Proactive Investors",
        )

    def test_build_articles_frame_derives_source_when_missing(self) -> None:
        accepted, _ = build_articles_frame(
            [
                {
                    "query": "ticker:NVO",
                    "feed_url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=NVO",
                    "feed_kind": "ticker",
                    "target_ticker": "NVO",
                    "title": "GLP-1 weight-loss drug popularity reaches new heights with Americans",
                    "summary": "Semaglutide and Wegovy adoption continue to rise.",
                    "url": "https://www.thestreet.com/health/gallup-ozempic-glp-1-use-soars?.tsrc=rss",
                    "source": "",
                    "rss_metadata": "",
                    "published_at": _published_at(2),
                }
            ]
        )

        self.assertEqual(accepted.iloc[0]["source"], "TheStreet")

    def test_build_articles_frame_rejects_stale_story(self) -> None:
        accepted, rejected = build_articles_frame(
            [
                {
                    "query": "ticker:GPCR",
                    "feed_url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GPCR",
                    "feed_kind": "ticker",
                    "target_ticker": "GPCR",
                    "title": "Does Phase 2b Oral GLP-1 Data on Aleniglipron Change The Bull Case For Structure Therapeutics (GPCR)?",
                    "summary": "Positive obesity trial data for aleniglipron.",
                    "url": "https://finance.yahoo.com/sectors/healthcare/articles/does-phase-2b-oral-glp-131837224.html?.tsrc=rss",
                    "source": "",
                    "rss_metadata": "",
                    "published_at": _published_at(30),
                }
            ]
        )

        self.assertEqual(len(accepted), 0)
        self.assertEqual(len(rejected), 1)
        self.assertIn("exceeds the 21-day news window", rejected.iloc[0]["rejection_reason"])

    def test_build_articles_frame_rejects_generic_other_ticker_story(self) -> None:
        accepted, rejected = build_articles_frame(
            [
                {
                    "query": "ticker:LLY",
                    "feed_url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=LLY",
                    "feed_kind": "ticker",
                    "target_ticker": "LLY",
                    "title": "Is It Too Late to Buy Eli Lilly?",
                    "summary": "The stock has soared 400% in recent years.",
                    "url": "https://www.fool.com/investing/2026/07/08/is-it-too-late-to-buy-eli-lilly/?.tsrc=rss",
                    "source": "",
                    "rss_metadata": "",
                    "published_at": _published_at(2),
                }
            ]
        )

        self.assertEqual(len(accepted), 0)
        self.assertEqual(len(rejected), 1)
        self.assertIn("lacked a strong thesis-specific catalyst", rejected.iloc[0]["rejection_reason"])

    def test_legal_dispute_headline_is_not_scored_positive_by_theme_bias(self) -> None:
        score, explanation = score_sentiment(
            "Novo Nordisk seeks injunction against Eli Lilly weight-loss drug ads",
            "GLP-1 Demand",
        )

        self.assertLessEqual(score, -0.1)
        self.assertIn("legal dispute terms", explanation)


if __name__ == "__main__":
    unittest.main()
