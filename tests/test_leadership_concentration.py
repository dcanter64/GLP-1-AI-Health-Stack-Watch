"""Tests for Phase 1 sleeve summaries and leadership concentration."""

from __future__ import annotations

import unittest

import pandas as pd

from glp1_watch.health_stack_sleeves import Sleeve, load_sleeve_config
from glp1_watch.leadership_concentration import (
    CONCENTRATION_BROAD,
    CONCENTRATION_INSUFFICIENT,
    CONCENTRATION_LEADER_DEPENDENT,
    CONCENTRATION_SELECTIVE,
    SLEEVE_STATUS_CONFIRMING,
    SLEEVE_STATUS_DETERIORATING,
    SLEEVE_STATUS_INSUFFICIENT,
    SLEEVE_STATUS_MIXED,
    build_sleeve_summaries,
    compute_leadership_concentration,
)


def make_sleeves() -> list[Sleeve]:
    return [
        Sleeve(name="Established GLP-1 Leaders", tickers=("LLY", "NVO"), required=True),
        Sleeve(name="Emerging GLP-1 Challengers", tickers=("AMGN", "VKTX"), required=True),
        Sleeve(name="AI Infrastructure Enablers", tickers=("NVDA",), required=False),
    ]


def make_performance(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def strong_row(ticker: str, ret: float = 0.25) -> dict:
    return {
        "ticker": ticker,
        "price": 100.0,
        "return_3m": ret,
        "rs_vs_xlv": 0.10,
        "rs_vs_spy": 0.08,
        "above_50dma": True,
        "above_200dma": True,
    }


def weak_row(ticker: str, ret: float = -0.20) -> dict:
    return {
        "ticker": ticker,
        "price": 100.0,
        "return_3m": ret,
        "rs_vs_xlv": -0.10,
        "rs_vs_spy": -0.08,
        "above_50dma": False,
        "above_200dma": False,
    }


class SleeveSummaryTests(unittest.TestCase):
    def test_statuses_confirming_mixed_deteriorating(self) -> None:
        sleeves = make_sleeves()
        performance = make_performance(
            [
                strong_row("LLY", 0.30),
                strong_row("NVO", 0.25),
                strong_row("AMGN", 0.20),
                weak_row("VKTX", -0.25),
                strong_row("NVDA", 0.40),
            ]
        )
        summaries = build_sleeve_summaries(performance, sleeves).set_index("sleeve")
        self.assertEqual(
            summaries.loc["Established GLP-1 Leaders", "status"], SLEEVE_STATUS_CONFIRMING
        )
        # One strong, one weak: mixed.
        self.assertEqual(
            summaries.loc["Emerging GLP-1 Challengers", "status"], SLEEVE_STATUS_MIXED
        )
        self.assertEqual(
            summaries.loc["AI Infrastructure Enablers", "status"], SLEEVE_STATUS_CONFIRMING
        )
        self.assertEqual(summaries.loc["Established GLP-1 Leaders", "best_ticker"], "LLY")
        self.assertEqual(summaries.loc["Established GLP-1 Leaders", "worst_ticker"], "NVO")

    def test_deteriorating_sleeve(self) -> None:
        sleeves = make_sleeves()
        performance = make_performance([weak_row("LLY"), weak_row("NVO")])
        summaries = build_sleeve_summaries(performance, sleeves).set_index("sleeve")
        self.assertEqual(
            summaries.loc["Established GLP-1 Leaders", "status"], SLEEVE_STATUS_DETERIORATING
        )

    def test_insufficient_data_when_names_missing(self) -> None:
        sleeves = make_sleeves()
        performance = make_performance([strong_row("LLY")])  # NVO missing entirely
        summaries = build_sleeve_summaries(performance, sleeves).set_index("sleeve")
        # 1 of 2 names = 0.5 coverage, not below the 0.5 threshold.
        self.assertNotEqual(
            summaries.loc["Established GLP-1 Leaders", "status"], SLEEVE_STATUS_INSUFFICIENT
        )
        empty = build_sleeve_summaries(pd.DataFrame(), sleeves).set_index("sleeve")
        self.assertEqual(
            empty.loc["Established GLP-1 Leaders", "status"], SLEEVE_STATUS_INSUFFICIENT
        )

    def test_bundled_config_summaries_cover_all_sleeves(self) -> None:
        sleeves = load_sleeve_config()
        performance = make_performance(
            [strong_row("LLY"), strong_row("TEM"), weak_row("NVDA")]
        )
        summaries = build_sleeve_summaries(performance, sleeves)
        self.assertEqual(len(summaries), 8)
        # Sleeves with no data at all report insufficient data, never crash.
        gene = summaries.set_index("sleeve").loc["Gene Editing and Precision Medicine"]
        self.assertEqual(gene["status"], SLEEVE_STATUS_INSUFFICIENT)


class ConcentrationTests(unittest.TestCase):
    def test_breadth_excludes_supporting_sleeve(self) -> None:
        sleeves = make_sleeves()
        # Every required name is weak and below its 50DMA; only NVDA (supporting) is strong.
        performance = make_performance(
            [
                weak_row("LLY"),
                weak_row("NVO"),
                weak_row("AMGN"),
                weak_row("VKTX"),
                strong_row("NVDA", 0.50),
            ]
        )
        summaries = build_sleeve_summaries(performance, sleeves)
        concentration = compute_leadership_concentration(performance, summaries, sleeves)
        # Semiconductor strength must not leak into core breadth.
        self.assertEqual(concentration["pct_above_50dma"], 0.0)
        self.assertEqual(concentration["pct_outperform_xlv"], 0.0)

    def test_leader_dependent_verdict(self) -> None:
        sleeves = make_sleeves()
        performance = make_performance(
            [
                strong_row("LLY", 0.60),
                weak_row("NVO", -0.05),
                weak_row("AMGN"),
                weak_row("VKTX"),
            ]
        )
        summaries = build_sleeve_summaries(performance, sleeves)
        concentration = compute_leadership_concentration(performance, summaries, sleeves)
        self.assertEqual(concentration["verdict"], CONCENTRATION_LEADER_DEPENDENT)
        self.assertEqual(concentration["leader_sleeve_status"], SLEEVE_STATUS_MIXED)
        # LLY dominates positive evidence: top1 share is high.
        self.assertGreaterEqual(concentration["top1_share"], 0.5)

    def test_broad_verdict(self) -> None:
        sleeves = [
            Sleeve(name="S1", tickers=("A", "B"), required=True),
            Sleeve(name="S2", tickers=("C", "D"), required=True),
            Sleeve(name="S3", tickers=("E", "F"), required=True),
            Sleeve(name="S4", tickers=("G", "H"), required=True),
        ]
        performance = make_performance(
            [
                strong_row("A", 0.10),
                strong_row("B", 0.10),
                strong_row("C", 0.10),
                strong_row("D", 0.10),
                strong_row("E", 0.10),
                strong_row("F", 0.10),
                strong_row("G", 0.10),
                strong_row("H", 0.10),
            ]
        )
        summaries = build_sleeve_summaries(performance, sleeves)
        concentration = compute_leadership_concentration(performance, summaries, sleeves)
        self.assertEqual(concentration["verdict"], CONCENTRATION_BROAD)
        self.assertEqual(concentration["confirming_count"], 4)

    def test_selective_verdict(self) -> None:
        sleeves = make_sleeves()
        # Leaders mixed (one strong, one weak); challengers confirming; no dominance.
        performance = make_performance(
            [
                strong_row("LLY", 0.15),
                weak_row("NVO", -0.02),
                strong_row("AMGN", 0.12),
                strong_row("VKTX", 0.12),
            ]
        )
        summaries = build_sleeve_summaries(performance, sleeves)
        concentration = compute_leadership_concentration(performance, summaries, sleeves)
        self.assertEqual(concentration["verdict"], CONCENTRATION_SELECTIVE)
        self.assertEqual(concentration["confirming_count"], 1)

    def test_lly_contribution_none_when_missing(self) -> None:
        sleeves = make_sleeves()
        performance = make_performance([strong_row("NVO"), strong_row("AMGN")])
        summaries = build_sleeve_summaries(performance, sleeves)
        concentration = compute_leadership_concentration(performance, summaries, sleeves)
        self.assertIsNone(concentration["lly_contribution"])

    def test_missing_rs_columns_give_insufficient_not_deteriorating(self) -> None:
        # Without relative-strength data the sleeve must not fabricate a
        # "deteriorating" signal from a defaulted 0.0 share.
        sleeves = make_sleeves()
        performance = pd.DataFrame(
            [
                {"ticker": "LLY", "price": 100.0, "return_3m": -0.10},
                {"ticker": "NVO", "price": 100.0, "return_3m": -0.12},
            ]
        )
        summaries = build_sleeve_summaries(performance, sleeves).set_index("sleeve")
        self.assertEqual(
            summaries.loc["Established GLP-1 Leaders", "status"], SLEEVE_STATUS_INSUFFICIENT
        )

    def test_empty_performance_gives_insufficient_verdict(self) -> None:
        sleeves = make_sleeves()
        summaries = build_sleeve_summaries(pd.DataFrame(), sleeves)
        concentration = compute_leadership_concentration(pd.DataFrame(), summaries, sleeves)
        self.assertEqual(concentration["verdict"], CONCENTRATION_INSUFFICIENT)
        self.assertEqual(concentration["core_names_with_data"], 0)
