from __future__ import annotations

import unittest

import pandas as pd

from glp1_watch.market_data import build_performance_table


class PerformanceTableTests(unittest.TestCase):
    def test_short_history_returns_partial_metrics_without_crashing(self) -> None:
        index = pd.date_range("2026-01-02", periods=30, freq="B")
        columns = pd.MultiIndex.from_product(
            [["Close"], ["LLY", "XLV", "QQQ", "SPY"]]
        )
        prices = pd.DataFrame(100.0, index=index, columns=columns)

        result = build_performance_table(prices).set_index("ticker")

        self.assertEqual(len(result), 4)
        self.assertTrue(pd.isna(result.loc["LLY", "return_3m"]))
        self.assertTrue(pd.isna(result.loc["LLY", "rs_vs_xlv"]))
        self.assertEqual(result.loc["LLY", "return_1m"], 0.0)


if __name__ == "__main__":
    unittest.main()
