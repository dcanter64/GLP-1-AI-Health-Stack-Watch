"""Tests for Phase 1 heuristic news-event clustering."""

from __future__ import annotations

import unittest

import pandas as pd

from glp1_watch.news_event_clustering import cluster_news_events, summarize_event_counts


def make_article(
    title: str,
    source: str = "Source A",
    theme: str = "GLP-1 Demand",
    tickers: str = "LLY",
    relevance: float = 0.5,
    published: str = "2026-10-01 12:00:00+00:00",
) -> dict:
    return {
        "title": title,
        "summary": title,
        "url": f"https://example.com/{abs(hash(title)) % 100000}",
        "source": source,
        "published_at": published,
        "theme": theme,
        "tickers": tickers,
        "relevance_score": relevance,
    }


class EventClusteringTests(unittest.TestCase):
    def test_same_event_multiple_sources_is_one_event(self) -> None:
        title = "Eli Lilly sues Novo Nordisk over weight loss advertisements in federal court"
        articles = pd.DataFrame(
            [
                make_article(title, source="Source A", tickers="LLY, NVO"),
                make_article(title, source="Source B", tickers="LLY, NVO"),
                make_article(title, source="Source C", tickers="LLY, NVO"),
            ]
        )
        clustered, events = cluster_news_events(articles)
        self.assertEqual(len(events), 1)
        self.assertEqual(events.iloc[0]["independent_sources"], 3)
        self.assertEqual(events.iloc[0]["story_count"], 3)
        # Three independent sources make it material.
        self.assertTrue(events.iloc[0]["material"])
        # Every article carries the event id.
        self.assertEqual(clustered["event_id"].nunique(), 1)

    def test_distinct_events_same_ticker_stay_separate(self) -> None:
        articles = pd.DataFrame(
            [
                make_article("FDA approves Lilly obesity drug for expanded use", tickers="LLY"),
                make_article(
                    "Lilly announces new manufacturing plant expansion in Indiana", tickers="LLY"
                ),
            ]
        )
        _, events = cluster_news_events(articles)
        self.assertEqual(len(events), 2)
        self.assertEqual(summarize_event_counts(events)["unique_events"], 2)

    def test_material_theme_flags_single_story_event(self) -> None:
        articles = pd.DataFrame(
            [
                make_article(
                    "FDA places clinical hold on Lilly trial after safety signal",
                    theme="Regulatory Risk",
                    relevance=0.3,
                )
            ]
        )
        _, events = cluster_news_events(articles)
        self.assertEqual(len(events), 1)
        self.assertTrue(events.iloc[0]["material"])

    def test_non_material_single_story(self) -> None:
        articles = pd.DataFrame(
            [make_article("Lilly opens community wellness center", theme="GLP-1 Demand", relevance=0.2)]
        )
        _, events = cluster_news_events(articles)
        self.assertEqual(len(events), 1)
        self.assertFalse(events.iloc[0]["material"])

    def test_empty_articles_give_empty_frames(self) -> None:
        clustered, events = cluster_news_events(pd.DataFrame())
        self.assertTrue(clustered.empty)
        self.assertTrue(events.empty)
        self.assertIn("event_id", clustered.columns)
        counts = summarize_event_counts(events)
        self.assertEqual(counts, {"unique_events": 0, "material_events": 0, "multi_source_events": 0})

    def test_source_count_is_case_insensitive(self) -> None:
        title = "Eli Lilly sues Novo Nordisk over weight loss advertisements in federal court"
        articles = pd.DataFrame(
            [
                make_article(title, source="Reuters", tickers="LLY, NVO"),
                make_article(title, source="reuters", tickers="LLY, NVO"),
            ]
        )
        _, events = cluster_news_events(articles)
        self.assertEqual(events.iloc[0]["independent_sources"], 1)

    def test_event_tickers_union_and_headline(self) -> None:
        title = "Eli Lilly sues Novo Nordisk over weight loss advertisements in federal court"
        articles = pd.DataFrame(
            [
                make_article(title, source="Source A", tickers="LLY"),
                make_article(title, source="Source B", tickers="NVO"),
            ]
        )
        clustered, events = cluster_news_events(articles)
        self.assertEqual(events.iloc[0]["tickers"], "LLY, NVO")
        self.assertIn("sues", events.iloc[0]["headline"].lower())
        self.assertTrue((clustered["event_id"] == events.iloc[0]["event_id"]).all())
