"""Phase 5: decision journal tests — immutability and honest forward fills."""

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from glp1_watch import decision_journal as dj


def entry(entity_type="ticker", name="AAA", **overrides):
    row = {
        "entity_type": entity_type,
        "entity_name": name,
        "methodology_version": "phase5-v1",
        "decision_price": 100.0,
        "decision_price_date": "2026-01-02",
        "recommendation": "INCREASE",
        "recommended_tier": 3,
        "confidence": 70.0,
        "urgency": "Moderate",
        "evidence": "test",
        "upgrade_condition": "up",
        "downgrade_condition": "down",
        "invalidation_condition": "invalid",
    }
    row.update(overrides)
    return row


def price_history(prices, start="2026-01-02"):
    idx = pd.date_range(start=start, periods=len(prices), freq="D")
    return pd.DataFrame({"AAA": prices}, index=idx)


def as_of(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)


class JournalStoreTests(unittest.TestCase):
    def test_append_and_upsert(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = dj.append_journal_entries(tmp, [entry()], as_of("2026-10-11"))
            self.assertEqual(len(first), 1)
            # Same key re-inserted: upsert, not duplicate.
            second = dj.append_journal_entries(tmp, [entry()], as_of("2026-10-11"))
            self.assertEqual(len(second), 1)

    def test_decision_fields_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            dj.append_journal_entries(tmp, [entry(recommendation="INCREASE")], as_of("2026-10-11"))
            # A later run tries to change the recommendation for the same key.
            journal = dj.append_journal_entries(
                tmp, [entry(recommendation="REDUCE")], as_of("2026-10-11")
            )
            self.assertEqual(len(journal), 1)
            self.assertEqual(journal.iloc[0]["recommendation"], "INCREASE")

    def test_unique_key_includes_entity_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = dj.append_journal_entries(
                tmp,
                [entry("sleeve", "Some Sleeve"), entry("ticker", "Some Sleeve")],
                as_of("2026-10-11"),
            )
            self.assertEqual(len(journal), 2)

    def test_future_dates_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "future decision date"):
                dj.append_journal_entries(tmp, [entry()], as_of("2099-01-01"))

    def test_utc_current_date_is_not_rejected_by_local_date_boundary(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            dj, "_utc_today", return_value=date(2026, 11, 3)
        ):
            journal = dj.append_journal_entries(
                tmp, [entry()], datetime(2026, 11, 3, 1, tzinfo=timezone.utc)
            )
            self.assertEqual(len(journal), 1)

    def test_corrupt_journal_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / dj.JOURNAL_FILENAME
            path.write_text("wrong,columns\n1,2\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "refusing to continue"):
                dj.load_journal(tmp)

    def test_atomic_write_no_leftovers(self):
        import pathlib

        with tempfile.TemporaryDirectory() as tmp:
            dj.append_journal_entries(tmp, [entry()], as_of("2026-10-11"))
            leftovers = list(pathlib.Path(tmp).glob("*.tmp"))
            self.assertEqual(leftovers, [])


class ForwardFillTests(unittest.TestCase):
    def test_fills_at_maturity_with_first_close(self):
        # Decision 2026-01-02; 1M matures 2026-02-01. First close on/after.
        journal = pd.DataFrame(
            [{**entry(), "decision_date": "2026-01-02", **{c: pd.NA for c in dj.OUTCOME_FIELDS}}],
            columns=dj.JOURNAL_COLUMNS,
        )
        prices = [100.0] * 30 + [110.0] * 40  # jump after day 30
        filled = dj.fill_forward_outcomes(journal, price_history(prices))
        # maturity 2026-02-01 -> first close on/after is index 30 (Feb 1) = 110.0
        self.assertAlmostEqual(filled.iloc[0]["outcome_1m"], 0.10)
        self.assertEqual(filled.iloc[0]["outcome_1m_date"], "2026-02-01")
        # 3M (Apr 3) not yet matured in a 70-day series -> stays NULL.
        self.assertTrue(pd.isna(filled.iloc[0]["outcome_3m"]))

    def test_never_fills_before_maturity(self):
        journal = pd.DataFrame(
            [{**entry(), "decision_date": "2026-01-02", **{c: pd.NA for c in dj.OUTCOME_FIELDS}}],
            columns=dj.JOURNAL_COLUMNS,
        )
        prices = [100.0 + i for i in range(40)]  # only 40 days
        filled = dj.fill_forward_outcomes(journal, price_history(prices))
        self.assertTrue(pd.isna(filled.iloc[0]["outcome_3m"]))
        self.assertTrue(pd.isna(filled.iloc[0]["outcome_6m"]))

    def test_outcomes_immutable_once_recorded(self):
        journal = pd.DataFrame(
            [
                {
                    **entry(),
                    "decision_date": "2026-01-02",
                    "outcome_1m": 0.05,
                    "outcome_1m_date": "2026-02-01",
                    **{c: pd.NA for c in ["outcome_3m", "outcome_3m_date", "outcome_6m", "outcome_6m_date"]},
                }
            ],
            columns=dj.JOURNAL_COLUMNS,
        )
        prices = [100.0] * 30 + [999.0] * 40  # would change the outcome if recomputed
        filled = dj.fill_forward_outcomes(journal, price_history(prices))
        self.assertAlmostEqual(filled.iloc[0]["outcome_1m"], 0.05)

    def test_sleeve_outcome_is_equal_weight(self):
        journal = pd.DataFrame(
            [
                {
                    **entry("sleeve", "S", decision_price=None, decision_price_date=None),
                    "decision_date": "2026-01-02",
                    **{c: pd.NA for c in dj.OUTCOME_FIELDS},
                }
            ],
            columns=dj.JOURNAL_COLUMNS,
        )
        idx = pd.date_range(start="2026-01-02", periods=35, freq="D")
        prices = pd.DataFrame({"A": [100.0] * 35, "B": [100.0] * 30 + [120.0] * 5}, index=idx)
        filled = dj.fill_forward_outcomes(
            journal, prices, sleeve_members={"S": ["A", "B"]}
        )
        # A: 0%, B: +20% over the first 31 days -> eq-wt +10%.
        self.assertAlmostEqual(filled.iloc[0]["outcome_1m"], 0.10)

    def test_decision_price_uses_last_close_on_or_before(self):
        # Decision on a Sunday: price off Friday's close, never a future close.
        idx = pd.date_range(start="2026-10-05", periods=5, freq="D")  # Mon-Fri
        prices = pd.DataFrame({"AAA": [100.0, 101.0, 102.0, 103.0, 104.0]}, index=idx)
        card = {
            "ticker": "AAA", "recommendation": "HOLD", "tier": None,
            "confidence": 0.0, "urgency": "Low", "reason": "not rated",
            "upgrade_condition": "", "downgrade_condition": "",
            "invalidation_condition": "",
        }
        entries = dj.build_journal_entries(
            decision_cards=[],
            position_cards=[card],
            price_history=prices,
            methodology_version="phase5-v1",
            as_of_dt=as_of("2026-10-11"),  # Sunday
        )
        self.assertEqual(len(entries), 1)
        self.assertAlmostEqual(entries[0]["decision_price"], 104.0)
        self.assertEqual(entries[0]["decision_price_date"], "2026-10-09")

    def test_repair_recomputes(self):
        with tempfile.TemporaryDirectory() as tmp:
            dj.append_journal_entries(tmp, [entry()], as_of("2026-01-02"))
            journal = dj.load_journal(tmp)
            prices = price_history([100.0] * 30 + [110.0] * 40)
            repaired = dj.repair_outcomes(tmp, journal, prices)
            self.assertAlmostEqual(repaired.iloc[0]["outcome_1m"], 0.10)
            # Repair persisted.
            reloaded = dj.load_journal(tmp)
            self.assertAlmostEqual(reloaded.iloc[0]["outcome_1m"], 0.10)


class TimezoneTests(unittest.TestCase):
    """M2: tz-aware and tz-naive price indexes both fill without crashing."""

    def _journal(self):
        return pd.DataFrame(
            [{**entry(), "decision_date": "2026-10-02", **{c: pd.NA for c in dj.OUTCOME_FIELDS}}],
            columns=dj.JOURNAL_COLUMNS,
        )

    def test_tz_naive_index(self):
        idx = pd.bdate_range("2026-09-01", "2026-12-15")
        prices = pd.DataFrame({"AAA": 100.0 + pd.Series(range(len(idx)), index=idx)}, index=idx)
        filled = dj.fill_forward_outcomes(self._journal(), prices)
        self.assertFalse(pd.isna(filled.iloc[0]["outcome_1m"]))

    def test_tz_aware_index(self):
        import datetime

        idx = pd.bdate_range("2026-09-01", "2026-12-15")
        prices = pd.DataFrame({"AAA": 100.0 + pd.Series(range(len(idx)), index=idx)}, index=idx)
        prices.index = prices.index.tz_localize(datetime.timezone(datetime.timedelta(hours=-5)))
        filled = dj.fill_forward_outcomes(self._journal(), prices)
        # Must not raise; fills from the date-normalized index.
        self.assertFalse(pd.isna(filled.iloc[0]["outcome_1m"]))


class SleeveOutcomeTests(unittest.TestCase):
    """M4/M5: sleeve outcome dates are actual trading dates; sleeve base
    uses the same last-close-on-or-before convention as tickers."""

    def _sleeve_journal(self, decision_date="2026-10-11"):
        # Sunday decision; 1M matures Tuesday 2026-11-10.
        return pd.DataFrame(
            [
                {
                    **entry("sleeve", "S", decision_price=None, decision_price_date=None),
                    "decision_date": decision_date,
                    **{c: pd.NA for c in dj.OUTCOME_FIELDS},
                }
            ],
            columns=dj.JOURNAL_COLUMNS,
        )

    def test_sleeve_outcome_date_is_trading_date(self):
        # M4: weekend maturity must not record a Sunday.
        idx = pd.bdate_range("2026-10-01", "2026-11-20")
        prices = pd.DataFrame(
            {"A": 100.0 + pd.Series(range(len(idx)), index=idx).astype(float)}, index=idx
        )
        journal = pd.DataFrame(
            [
                {
                    **entry("sleeve", "S", decision_price=None, decision_price_date=None),
                    "decision_date": "2026-10-02",  # Friday; 1M matures Sun 2026-11-01
                    **{c: pd.NA for c in dj.OUTCOME_FIELDS},
                }
            ],
            columns=dj.JOURNAL_COLUMNS,
        )
        filled = dj.fill_forward_outcomes(journal, prices, sleeve_members={"S": ["A"]})
        date_str = filled.iloc[0]["outcome_1m_date"]
        # First trading close on/after Sun 2026-11-01 is Mon 2026-11-02.
        self.assertEqual(date_str, "2026-11-02")

    def test_sleeve_base_matches_ticker_convention(self):
        # M5: Sunday decision -> sleeve base is Friday's close, like tickers.
        idx = pd.bdate_range("2026-10-01", "2026-11-20")
        # Friday 2026-10-09 close = 100 + (index of 10-09); Monday 10-12 higher.
        vals = []
        for d in idx:
            vals.append(200.0 if d >= pd.Timestamp("2026-10-12") else 100.0)
        prices = pd.DataFrame({"A": vals}, index=idx)
        filled = dj.fill_forward_outcomes(
            self._sleeve_journal("2026-10-11"), prices, sleeve_members={"S": ["A"]}
        )
        # Base Friday 100, maturity Tue 2026-11-10 close 200 -> +100%.
        self.assertAlmostEqual(filled.iloc[0]["outcome_1m"], 1.0)


class JournalBoundaryTests(unittest.TestCase):
    """M7a/M7b: loud duplicate rejection; key normalization."""

    def test_duplicate_keys_rejected_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = pd.DataFrame(
                [entry(), entry()], columns=dj.JOURNAL_COLUMNS,
            )
            rows["decision_date"] = "2026-10-11"
            with self.assertRaisesRegex(ValueError, "duplicate keys rejected"):
                dj.persist_filled_journal(tmp, rows)

    def test_case_insensitive_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = pd.DataFrame(
                [entry("ticker", "AAA"), entry("ticker", "aaa")],
                columns=dj.JOURNAL_COLUMNS,
            )
            rows["decision_date"] = "2026-10-11"
            with self.assertRaisesRegex(ValueError, "duplicate keys rejected"):
                dj.persist_filled_journal(tmp, rows)

    def test_ticker_names_uppercased_at_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = dj.append_journal_entries(
                tmp, [entry("TICKER", "aapl")], as_of("2026-10-11")
            )
            self.assertEqual(journal.iloc[0]["entity_type"], "ticker")
            self.assertEqual(journal.iloc[0]["entity_name"], "AAPL")

    def test_sleeve_names_preserve_canonical_casing(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = dj.append_journal_entries(
                tmp, [entry("sleeve", "Established GLP-1 Leaders")], as_of("2026-10-11")
            )
            self.assertEqual(journal.iloc[0]["entity_name"], "Established GLP-1 Leaders")

    def test_invalid_entity_type_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "invalid entity_type"):
                dj.append_journal_entries(
                    tmp, [entry("bogus", "AAA")], as_of("2026-10-11")
                )

    def test_upsert_skip_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            dj.append_journal_entries(tmp, [entry("ticker", "AAA")], as_of("2026-10-11"))
            journal = dj.append_journal_entries(
                tmp, [entry("ticker", "aaa", recommendation="REDUCE")], as_of("2026-10-11")
            )
            self.assertEqual(len(journal), 1)
            self.assertEqual(journal.iloc[0]["recommendation"], "INCREASE")


if __name__ == "__main__":
    unittest.main()
