"""Tests for the Phase 2 Market Confirmation Score."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from glp1_watch.decision_weights import load_decision_weights
from glp1_watch.health_stack_sleeves import Sleeve
from glp1_watch.market_confirmation import compute_market_confirmation


def make_sleeves() -> list[Sleeve]:
    return [
        Sleeve(name="Established GLP-1 Leaders", tickers=("LLY", "NVO"), required=True),
        Sleeve(name="AI Drug-Discovery Platforms", tickers=("RXRX", "SDGR"), required=True),
    ]


def perf_row(
    ticker: str,
    r1m: float,
    r3m: float,
    rs: float = 0.05,
    above: bool = True,
    drawdown: float = -0.05,
) -> dict:
    return {
        "ticker": ticker,
        "price": 100.0,
        "return_1m": r1m,
        "return_3m": r3m,
        "rs_vs_xlv": rs,
        "rs_vs_spy": rs,
        "rs_vs_qqq": rs,
        "above_50dma": above,
        "above_200dma": above,
        "distance_from_52w_high": drawdown,
    }


def price_history(tickers: list[str], drift: float = 0.001, days: int = 120) -> pd.DataFrame:
    dates = pd.date_range("2026-06-01", periods=days, freq="D")
    data = {}
    rng = np.random.default_rng(7)
    for ticker in tickers:
        noise = rng.normal(0, 0.01, days)
        prices = 100 * np.exp(np.cumsum(drift + noise))
        data[("Close", ticker)] = prices
    frame = pd.DataFrame(data, index=dates)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)
    return frame


class MarketConfirmationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.weights = load_decision_weights()

    def test_strong_sleeve_scores_high(self) -> None:
        performance = pd.DataFrame(
            [
                perf_row("LLY", 0.08, 0.25, rs=0.10, above=True, drawdown=-0.02),
                perf_row("NVO", 0.07, 0.22, rs=0.09, above=True, drawdown=-0.03),
                perf_row("RXRX", -0.05, -0.15, rs=-0.08, above=False, drawdown=-0.40),
                perf_row("SDGR", -0.04, -0.12, rs=-0.07, above=False, drawdown=-0.35),
            ]
        )
        prices = price_history(["LLY", "NVO", "RXRX", "SDGR"])
        result = compute_market_confirmation(
            performance, prices, make_sleeves(), self.weights
        ).set_index("sleeve")
        leaders = result.loc["Established GLP-1 Leaders", "market_confirmation_score"]
        platforms = result.loc["AI Drug-Discovery Platforms", "market_confirmation_score"]
        self.assertGreater(leaders, 70)
        self.assertLess(platforms, 40)
        self.assertGreater(leaders, platforms)

    def test_insufficient_coverage_gives_no_score(self) -> None:
        performance = pd.DataFrame([perf_row("LLY", 0.08, 0.25)])
        result = compute_market_confirmation(
            performance, pd.DataFrame(), make_sleeves(), self.weights
        ).set_index("sleeve")
        row = result.loc["AI Drug-Discovery Platforms"]
        self.assertTrue(pd.isna(row["market_confirmation_score"]))
        self.assertEqual(row["confidence"], "Low")

    def test_score_bounds(self) -> None:
        performance = pd.DataFrame(
            [
                perf_row("LLY", 2.0, 5.0, rs=2.0, above=True, drawdown=0.0),
                perf_row("NVO", -0.9, -0.95, rs=-2.0, above=False, drawdown=-0.95),
            ]
        )
        prices = price_history(["LLY", "NVO"])
        result = compute_market_confirmation(
            performance, prices, make_sleeves(), self.weights
        )
        scores = result["market_confirmation_score"].dropna()
        self.assertTrue(((scores >= 0) & (scores <= 100)).all())

    def test_missing_components_renormalize(self) -> None:
        # No RS columns and no price history: score still computes from the
        # remaining components and notes what was missing.
        performance = pd.DataFrame(
            [
                {
                    "ticker": "LLY",
                    "return_1m": 0.05,
                    "return_3m": 0.15,
                    "above_50dma": True,
                    "above_200dma": True,
                    "distance_from_52w_high": -0.05,
                },
                {
                    "ticker": "NVO",
                    "return_1m": 0.04,
                    "return_3m": 0.12,
                    "above_50dma": True,
                    "above_200dma": True,
                    "distance_from_52w_high": -0.06,
                },
            ]
        )
        result = compute_market_confirmation(
            performance, pd.DataFrame(), make_sleeves(), self.weights
        ).set_index("sleeve")
        row = result.loc["Established GLP-1 Leaders"]
        self.assertFalse(pd.isna(row["market_confirmation_score"]))
        self.assertIn("missing components", row["note"])
