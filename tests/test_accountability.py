"""Phase 5: accountability metric tests."""

import unittest

import pandas as pd

from glp1_watch import accountability as ac
from glp1_watch import decision_journal as dj


def journal_row(entity_type, name, rec, outcome_3m, **overrides):
    row = {
        "decision_date": "2026-01-02",
        "entity_type": entity_type,
        "entity_name": name,
        "methodology_version": "phase5-v1",
        "decision_price": 100.0,
        "decision_price_date": "2026-01-02",
        "recommendation": rec,
        "recommended_tier": 3,
        "confidence": 70.0,
        "confidence_band": "High",
        "urgency": "Moderate",
        "evidence": "test",
        "upgrade_condition": "up",
        "downgrade_condition": "down",
        "invalidation_condition": "inv",
        "outcome_1m": None,
        "outcome_1m_date": None,
        "outcome_3m": outcome_3m,
        "outcome_3m_date": "2026-04-03",
        "outcome_6m": None,
        "outcome_6m_date": None,
    }
    row.update(overrides)
    return row


def make_journal(rows):
    return pd.DataFrame(rows, columns=dj.JOURNAL_COLUMNS)


def flat_prices():
    idx = pd.date_range(start="2026-01-02", periods=120, freq="D")
    return pd.DataFrame(
        {"AAA": [100.0] * 120, "BBB": [100.0] * 120, "SPY": [100.0] * 120},
        index=idx,
    )


class ErrorRateTests(unittest.TestCase):
    def test_absolute_false_positive(self):
        # 3 increases: 2 negative 3M -> FP rate 2/3.
        journal = make_journal(
            [
                journal_row("ticker", "AAA", "INCREASE", -0.05),
                journal_row("ticker", "BBB", "INCREASE", -0.02),
                journal_row("ticker", "CCC", "INCREASE", 0.08),
            ]
        )
        m = ac.compute_accountability(journal, flat_prices(), min_n_rates=2, min_n_avg=2)
        fp = m["false_positive_rate_absolute"]
        self.assertEqual(fp["status"], "ok")
        self.assertAlmostEqual(fp["value"], 2 / 3)
        self.assertEqual(fp["n"], 3)

    def test_absolute_false_negative(self):
        journal = make_journal(
            [
                journal_row("ticker", "AAA", "REDUCE", 0.06),
                journal_row("ticker", "BBB", "AVOID NEW CAPITAL", -0.03),
            ]
        )
        m = ac.compute_accountability(journal, flat_prices(), min_n_rates=2, min_n_avg=2)
        fn = m["false_negative_rate_absolute"]
        self.assertEqual(fn["status"], "ok")
        self.assertAlmostEqual(fn["value"], 0.5)

    def test_relative_labels_separate_from_absolute(self):
        # Absolute positive but underperforms SPY -> relative FP, not absolute.
        idx = pd.date_range(start="2026-01-02", periods=120, freq="D")
        prices = pd.DataFrame(
            {"AAA": [100.0] * 120, "SPY": [100.0 + i * 0.5 for i in range(120)]},
            index=idx,
        )
        journal = make_journal(
            [
                journal_row("ticker", "AAA", "INCREASE", 0.02),
                journal_row("ticker", "AAB", "INCREASE", 0.03),
            ]
        )
        m = ac.compute_accountability(journal, prices, min_n_rates=2, min_n_avg=2)
        self.assertAlmostEqual(m["false_positive_rate_absolute"]["value"], 0.0)
        # Both underperformed SPY over the window -> relative FP = 1.0.
        self.assertAlmostEqual(m["false_positive_rate_vs_spy"]["value"], 1.0)


class GatingTests(unittest.TestCase):
    def test_insufficient_history_not_a_verdict(self):
        journal = make_journal([journal_row("ticker", "AAA", "INCREASE", -0.50)])
        m = ac.compute_accountability(journal, flat_prices(), min_n_rates=10, min_n_avg=5)
        fp = m["false_positive_rate_absolute"]
        self.assertEqual(fp["status"], "insufficient history")
        self.assertEqual(fp["n"], 1)
        # A terrible number with too little data is not reported as a rate.
        self.assertNotIn("value", fp)

    def test_n_always_shown(self):
        journal = make_journal([journal_row("ticker", "AAA", "INCREASE", 0.10)])
        m = ac.compute_accountability(journal, flat_prices(), min_n_rates=1, min_n_avg=1)
        self.assertEqual(m["false_positive_rate_absolute"]["n"], 1)
        self.assertEqual(m["avg_3m_after_increase"]["n"], 1)

    def test_empty_journal(self):
        m = ac.compute_accountability(
            pd.DataFrame(columns=dj.JOURNAL_COLUMNS), flat_prices()
        )
        self.assertEqual(m["n_with_3m_outcome"]["n"], 0)
        self.assertEqual(m["false_positive_rate_absolute"]["status"], "insufficient history")

    def test_summarize_separates_history_from_performance(self):
        journal = make_journal([journal_row("ticker", "AAA", "INCREASE", -0.50)])
        m = ac.compute_accountability(journal, flat_prices(), min_n_rates=10, min_n_avg=5)
        lines = ac.summarize_accountability(m)
        self.assertTrue(any("insufficient history" in line for line in lines))
        self.assertTrue(any("not a performance verdict" in line for line in lines))


class CommitteePointerTests(unittest.TestCase):
    def test_pointer_material(self):
        divergences = [{"ticker": "AAA"}]
        metrics = {
            "n_with_3m_outcome": {"n": 0},
            "false_positive_rate_absolute": {"status": "insufficient history", "n": 0},
        }
        pointer = ac.build_committee_pointer(divergences, metrics)
        self.assertIn("AAA", pointer)
        self.assertIn("§9", pointer)

    def test_pointer_quiet_when_nothing_material(self):
        pointer = ac.build_committee_pointer(
            [], {"n_with_3m_outcome": {"n": 0}}
        )
        self.assertEqual(pointer, "")

    def test_pointer_silent_on_below_minimum_data(self):
        # M1 regression: outcomes exist but nothing is gradable -> silence.
        # §10 still reports "insufficient history (n=X)"; §1 must not amplify it.
        journal = make_journal(
            [
                journal_row("ticker", f"T{i}", "HOLD", 0.05)
                for i in range(3)
            ]
        )
        m = ac.compute_accountability(journal, flat_prices())
        self.assertEqual(m["n_with_3m_outcome"]["n"], 3)
        gradable = [
            v for k, v in m.items()
            if k != "n_with_3m_outcome" and isinstance(v, dict) and v.get("status") == "ok"
        ]
        self.assertEqual(gradable, [])
        self.assertEqual(ac.build_committee_pointer([], m), "")

    def test_pointer_fires_on_gradable_metrics(self):
        journal = make_journal(
            [journal_row("ticker", f"T{i}", "INCREASE", 0.05) for i in range(12)]
        )
        m = ac.compute_accountability(journal, flat_prices())
        pointer = ac.build_committee_pointer([], m)
        self.assertIn("§10", pointer)


if __name__ == "__main__":
    unittest.main()
