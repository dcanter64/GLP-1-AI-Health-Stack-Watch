"""Tests for the Phase 2 Expectations Risk Score."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from glp1_watch.decision_weights import load_decision_weights
from glp1_watch.expectations_risk import compute_expectations_risk
from glp1_watch.health_stack_sleeves import Sleeve


def make_sleeves() -> list[Sleeve]:
    return [
        Sleeve(name="Established GLP-1 Leaders", tickers=("LLY", "NVO"), required=True),
        Sleeve(name="AI Drug-Discovery Platforms", tickers=("RXRX", "SDGR"), required=True),
    ]


def perf_row(ticker: str, r1m: float, r3m: float, drawdown: float) -> dict:
    return {
        "ticker": ticker,
        "price": 100.0,
        "return_1m": r1m,
        "return_3m": r3m,
        "distance_from_52w_high": drawdown,
    }


def price_history(tickers: list[str], drift: float, days: int = 120) -> pd.DataFrame:
    dates = pd.date_range("2026-06-01", periods=days, freq="D")
    data = {}
    rng = np.random.default_rng(11)
    for ticker in tickers:
        noise = rng.normal(0, 0.008, days)
        data[("Close", ticker)] = 100 * np.exp(np.cumsum(drift + noise))
    frame = pd.DataFrame(data, index=dates)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)
    return frame


def articles(rows: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"tickers": ticker, "sentiment_score": sentiment} for ticker, sentiment in rows]
    )


class ExpectationsRiskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.weights = load_decision_weights()

    def test_extended_accelerating_sleeve_is_risky(self) -> None:
        performance = pd.DataFrame(
            [
                perf_row("LLY", 0.20, 0.15, -0.01),
                perf_row("NVO", 0.18, 0.12, -0.02),
            ]
        )
        prices = price_history(["LLY", "NVO"], drift=0.004)
        news = articles([("LLY", 0.8)] * 12)
        result = compute_expectations_risk(
            performance, prices, news, make_sleeves(), self.weights
        ).set_index("sleeve")
        risk = result.loc["Established GLP-1 Leaders", "expectations_risk_score"]
        self.assertGreater(risk, 50)

    def test_calm_sleeve_is_low_risk(self) -> None:
        performance = pd.DataFrame(
            [
                perf_row("RXRX", 0.01, 0.02, -0.30),
                perf_row("SDGR", -0.01, 0.01, -0.35),
            ]
        )
        prices = price_history(["RXRX", "SDGR"], drift=0.0)
        news = articles([("RXRX", 0.0)] * 3)
        result = compute_expectations_risk(
            performance, prices, news, make_sleeves(), self.weights
        ).set_index("sleeve")
        risk = result.loc["AI Drug-Discovery Platforms", "expectations_risk_score"]
        self.assertLess(risk, 40)

    def test_confidence_capped_without_valuation_data(self) -> None:
        performance = pd.DataFrame(
            [
                perf_row("LLY", 0.05, 0.10, -0.05),
                perf_row("NVO", 0.04, 0.09, -0.06),
            ]
        )
        prices = price_history(["LLY", "NVO"], drift=0.001)
        result = compute_expectations_risk(
            performance, prices, pd.DataFrame(), make_sleeves(), self.weights
        ).set_index("sleeve")
        row = result.loc["Established GLP-1 Leaders"]
        self.assertFalse(pd.isna(row["expectations_risk_score"]))
        # Valuation/revision data are unavailable: never High confidence.
        self.assertNotEqual(row["confidence"], "High")
        self.assertIn("valuation", row["note"].lower())

    def test_insufficient_coverage_gives_no_score(self) -> None:
        performance = pd.DataFrame([perf_row("LLY", 0.05, 0.10, -0.05)])
        result = compute_expectations_risk(
            performance, pd.DataFrame(), pd.DataFrame(), make_sleeves(), self.weights
        ).set_index("sleeve")
        row = result.loc["AI Drug-Discovery Platforms"]
        self.assertTrue(pd.isna(row["expectations_risk_score"]))

    def test_comma_space_tickers_do_not_crash(self) -> None:
        # Regression: live data writes "LLY, NVO" (space after comma); the
        # sleeve lookup must normalize before indexing, not just for the
        # membership test.
        performance = pd.DataFrame(
            [
                perf_row("LLY", 0.05, 0.10, -0.05),
                perf_row("NVO", 0.04, 0.09, -0.06),
            ]
        )
        news = articles([("LLY, NVO", 0.8), ("NVO, LLY", 0.7)])
        result = compute_expectations_risk(
            performance, pd.DataFrame(), news, make_sleeves(), self.weights
        ).set_index("sleeve")
        row = result.loc["Established GLP-1 Leaders"]
        self.assertFalse(pd.isna(row["expectations_risk_score"]))

    def test_score_bounds(self) -> None:
        performance = pd.DataFrame(
            [
                perf_row("LLY", 5.0, 10.0, 0.0),
                perf_row("NVO", -5.0, -10.0, -0.99),
            ]
        )
        prices = price_history(["LLY", "NVO"], drift=0.02)
        news = articles([("LLY", 1.0)] * 50 + [("NVO", -1.0)] * 50)
        result = compute_expectations_risk(
            performance, prices, news, make_sleeves(), self.weights
        )
        scores = result["expectations_risk_score"].dropna()
        self.assertTrue(((scores >= 0) & (scores <= 100)).all())
