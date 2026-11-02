"""Phase 5: backtest tests — Track A math and Track B honesty."""

import unittest
from types import SimpleNamespace

import pandas as pd

from glp1_watch import backtest as bt
from glp1_watch import decision_journal as dj


def prices_frame(tickers_prices, start="2025-01-02"):
    n = len(next(iter(tickers_prices.values())))
    idx = pd.date_range(start=start, periods=n, freq="D")
    return pd.DataFrame(tickers_prices, index=idx)


def sleeves(names_tickers):
    return [
        SimpleNamespace(name=name, tickers=tickers, required=True)
        for name, tickers in names_tickers
    ]


class TrackAMathTests(unittest.TestCase):
    def test_total_return_and_drawdown(self):
        # 10% up then back to flat: total ~0 (minus inception cost), max DD < 0.
        prices = prices_frame({"A": [100, 110, 100, 100, 100] * 12})
        result = bt.run_track_a(prices, {"strat": ["A"]})
        res = result["results"]["strat"]
        self.assertAlmostEqual(res["total_return"], 0.0, places=2)
        self.assertLess(res["max_drawdown"], 0)

    def test_equal_weight_math(self):
        # A doubles, B flat: monthly-rebalanced eq-wt lands ~+45% before costs.
        n = 63
        prices = prices_frame({"A": [100 * (2 ** (i / (n - 1))) for i in range(n)],
                               "B": [100.0] * n})
        result = bt.run_track_a(prices, {"strat": ["A", "B"]})
        res = result["results"]["strat"]
        self.assertGreater(res["total_return"], 0.40)
        self.assertLess(res["total_return"], 0.60)

    def test_weights_drift_between_monthly_rebalances(self):
        # A round-trips 100 -> 200 -> 100 while B stays flat. Buy-and-hold
        # equal weight is flat before inception cost; daily equal weighting
        # would incorrectly earn +12.5% from volatility pumping.
        prices = prices_frame({"A": [100.0, 200.0, 100.0], "B": [100.0] * 3})
        result = bt.run_track_a(prices, {"strat": ["A", "B"]})
        res = result["results"]["strat"]
        self.assertLess(res["total_return"], 0.0)
        self.assertGreater(res["total_return"], -0.002)
        self.assertEqual(res["turnover"], 1.0)

    def test_monthly_rebalance_charges_drift_turnover(self):
        n = 44
        prices = prices_frame(
            {
                "A": [100.0 * (1.03**i) for i in range(n)],
                "B": [100.0] * n,
            }
        )
        result = bt.run_track_a(prices, {"strat": ["A", "B"]})
        self.assertGreater(result["results"]["strat"]["turnover"], 1.0)

    def test_metadata_always_present(self):
        prices = prices_frame({"A": [100.0] * 63, "SPY": [100.0] * 63})
        result = bt.run_track_a(prices, {"strat": ["A"]}, benchmarks=["SPY"])
        self.assertIn("period", result)
        self.assertIn("n_days", result)
        self.assertIn("rebalance_frequency", result)
        self.assertIn("transaction_cost_assumption", result)
        self.assertIn("unavailable", result)
        self.assertTrue(len(result["unavailable"]) > 0)
        self.assertIn("EXPLORATORY", result["label"])
        self.assertIn("survivorship", result["label"].lower())

    def test_annualized_flagged_unreliable_under_two_years(self):
        prices = prices_frame({"A": [100.0] * 400})
        result = bt.run_track_a(prices, {"strat": ["A"]})
        self.assertFalse(result["results"]["strat"]["annualized_reliable"])

    def test_excess_return_vs_benchmarks(self):
        n = 63
        prices = prices_frame({"A": [100 + i for i in range(n)],
                               "SPY": [100.0] * n})
        result = bt.run_track_a(prices, {"strat": ["A"]}, benchmarks=["SPY"])
        excess = result["results"]["strat"]["excess_return_vs_benchmarks"]["SPY"]
        self.assertGreater(excess, 0)

    def test_empty_history(self):
        result = bt.run_track_a(pd.DataFrame(), {"strat": ["A"]})
        self.assertEqual(result["status"], "no data")


class TrackBTests(unittest.TestCase):
    def test_awaiting_first_decision(self):
        status = bt.track_b_status(pd.DataFrame(columns=dj.JOURNAL_COLUMNS))
        self.assertEqual(status["status"], "awaiting first live decision")
        self.assertIsNone(status["first_decision"])

    def test_walk_forward_after_first_decision(self):
        journal = pd.DataFrame(
            [{"decision_date": "2026-10-11", "entity_type": "sleeve",
              "entity_name": "S"}],
            columns=dj.JOURNAL_COLUMNS,
        )
        status = bt.track_b_status(journal)
        self.assertEqual(status["status"], "walk-forward")
        self.assertEqual(status["first_decision"], "2026-10-11")
        self.assertIn("reconstruct", status["note"].lower())

    def test_strategies_built_from_sleeves(self):
        sl = sleeves([("Established GLP-1 Leaders", ["LLY", "NVO"]),
                      ("Other", ["AAA"])])
        strategies = bt.track_a_strategies(sl)
        self.assertEqual(strategies["leader_only"], ["LLY", "NVO"])
        self.assertIn("AAA", strategies["equal_weight_stack"])


if __name__ == "__main__":
    unittest.main()
