"""Phase 5: position-level decision tests."""

import unittest

import pandas as pd

from glp1_watch import position_engine as pe
from glp1_watch.decision_engine import (
    REC_ACCUMULATE,
    REC_AVOID,
    REC_CATALYST_WATCH,
    REC_HOLD,
    REC_REDUCE,
    REC_STRONG_REDUCE,
)


def make_perf(ticker="AAA", **overrides):
    row = {
        "ticker": ticker,
        "return_1m": 0.02,
        "return_3m": 0.05,
        "rs_vs_spy": 0.03,
        "rs_vs_xlv": 0.02,
        "above_50dma": True,
        "above_200dma": True,
        "distance_from_52w_high": -0.05,
    }
    row.update(overrides)
    return row


def make_sleeve_card(sleeve="Some Sleeve", **overrides):
    card = {
        "sleeve": sleeve,
        "recommendation": REC_HOLD,
        "recommended_tier": 2,
        "readiness": "Confirmed",
        "confidence": 60.0,
        "urgency": "Low",
        "expectations_risk": 30.0,
        "recognition_gap": "none",
        "invalidation_condition": "structural < 40",
    }
    card.update(overrides)
    return card


def classify(perf, card, rs_vs_sleeve=0.03, rank=3):
    return pe.classify_position_status(
        perf_row=perf,
        sleeve_card=card,
        rs_vs_sleeve=rs_vs_sleeve,
        sleeve_rank_by_rs=rank,
    )


class PositionStatusTests(unittest.TestCase):
    """One fixture per status."""

    def test_core_leader(self):
        self.assertEqual(
            classify(make_perf(), make_sleeve_card("Established GLP-1 Leaders", recommended_tier=3)),
            "Core leader",
        )

    def test_tactical_leader(self):
        self.assertEqual(
            classify(make_perf(), make_sleeve_card("Established GLP-1 Leaders", recommended_tier=2)),
            "Tactical leader",
        )

    def test_emerging_leader(self):
        self.assertEqual(
            classify(make_perf(), make_sleeve_card(recommended_tier=2)),
            "Emerging leader",
        )

    def test_early_accumulation(self):
        self.assertEqual(
            classify(
                make_perf(above_200dma=False, rs_vs_spy=-0.02),
                make_sleeve_card(readiness="Developing", recommended_tier=1, recommendation=REC_ACCUMULATE),
                rs_vs_sleeve=-0.02,
            ),
            "Early accumulation",
        )

    def test_catalyst_dependent(self):
        self.assertEqual(
            classify(
                make_perf(above_200dma=False),
                make_sleeve_card(recommendation=REC_CATALYST_WATCH, recommended_tier=1),
                rs_vs_sleeve=-0.02,
            ),
            "Catalyst-dependent",
        )

    def test_recognition_gap(self):
        self.assertEqual(
            classify(
                make_perf(),
                make_sleeve_card(recognition_gap="unrecognized strength"),
                rs_vs_sleeve=0.08,
            ),
            "Recognition gap",
        )

    def test_expectations_risk_leader(self):
        self.assertEqual(
            classify(
                make_perf(),
                make_sleeve_card(expectations_risk=75.0),
                rank=1,
            ),
            "Expectations-risk leader",
        )

    def test_thesis_intact_price_broken(self):
        self.assertEqual(
            classify(
                make_perf(above_200dma=False),
                make_sleeve_card(recommended_tier=3),
                rs_vs_sleeve=-0.04,
            ),
            "Thesis intact / price broken",
        )

    def test_price_intact_thesis_weakening(self):
        self.assertEqual(
            classify(
                make_perf(rs_vs_spy=0.04),
                make_sleeve_card(recommended_tier=1, recommendation=REC_REDUCE),
            ),
            "Price intact / thesis weakening",
        )

    def test_recovery_candidate(self):
        self.assertEqual(
            classify(
                make_perf(rs_vs_spy=-0.02),
                make_sleeve_card(readiness="Repairing", recommended_tier=1),
            ),
            "Recovery candidate",
        )

    def test_rotation_source(self):
        self.assertEqual(
            classify(
                make_perf(),
                make_sleeve_card(readiness="Exhausted", recommended_tier=2),
            ),
            "Rotation source",
        )

    def test_avoid_new_capital(self):
        self.assertEqual(
            classify(
                make_perf(),
                make_sleeve_card(recommended_tier=0, recommendation=REC_AVOID),
            ),
            "Avoid new capital",
        )

    def test_exit_candidate(self):
        self.assertEqual(
            classify(
                make_perf(above_200dma=False),
                make_sleeve_card(recommendation=REC_STRONG_REDUCE, recommended_tier=1),
                rs_vs_sleeve=-0.05,
            ),
            "Exit candidate",
        )

    def test_insufficient_evidence_missing_technicals(self):
        perf = make_perf()
        del perf["return_3m"]
        self.assertEqual(
            classify(perf, make_sleeve_card()),
            "Insufficient Evidence / Not Rated",
        )

    def test_insufficient_evidence_missing_sleeve_card(self):
        self.assertEqual(
            classify(make_perf(), None),
            "Insufficient Evidence / Not Rated",
        )

    def test_insufficient_evidence_unrated_sleeve(self):
        self.assertEqual(
            classify(make_perf(), make_sleeve_card(recommended_tier=None)),
            "Insufficient Evidence / Not Rated",
        )


class PrecedenceTests(unittest.TestCase):
    """Defensive states and hard invalidations beat constructive ones."""

    def test_defensive_beats_constructive(self):
        # Tier 3 leader sleeve, but price broken -> defensive status wins.
        status = classify(
            make_perf(above_200dma=False),
            make_sleeve_card("Established GLP-1 Leaders", recommended_tier=3),
            rs_vs_sleeve=-0.04,
        )
        self.assertEqual(status, "Thesis intact / price broken")

    def test_hard_exit_beats_avoid(self):
        status = classify(
            make_perf(above_200dma=False),
            make_sleeve_card(recommendation=REC_STRONG_REDUCE, recommended_tier=0),
            rs_vs_sleeve=-0.06,
        )
        self.assertEqual(status, "Exit candidate")

    def test_rotation_source_beats_emerging_leader(self):
        status = classify(
            make_perf(),
            make_sleeve_card(readiness="Exhausted", recommended_tier=2),
            rs_vs_sleeve=0.05,
        )
        self.assertEqual(status, "Rotation source")


class TickerTierTests(unittest.TestCase):
    def _card(self, **overrides):
        perf = make_perf(**overrides.pop("perf", {}))
        card = make_sleeve_card(**overrides.pop("card", {}))
        tickers = overrides.pop("tickers", ["AAA", "BBB"])
        returns = overrides.pop("returns", {"AAA": 0.05, "BBB": 0.05})
        return pe.build_position_card(
            ticker="AAA",
            perf_row=perf,
            sleeve_card=card,
            sleeve_tickers=tickers,
            sleeve_returns_3m=returns,
            ticker_material_events=0,
        )

    def test_broken_technicals_step_down_tier(self):
        card = self._card(
            perf={"above_200dma": False, "return_3m": -0.02},
            card={"recommended_tier": 3},
            returns={"AAA": -0.02, "BBB": 0.06},
        )
        self.assertEqual(card["tier"], 2)
        self.assertEqual(card["sleeve_tier"], 3)

    def test_tier_floored_at_zero(self):
        card = self._card(
            perf={"above_200dma": False, "return_3m": -0.02},
            card={"recommended_tier": 0},
            returns={"AAA": -0.02, "BBB": 0.06},
        )
        self.assertEqual(card["tier"], 0)

    def test_never_above_sleeve_tier(self):
        # Strong price action: tier stays, recognition via confidence/status.
        card = self._card(
            perf={"above_200dma": True, "rs_vs_spy": 0.10, "return_3m": 0.15},
            card={"recommended_tier": 2, "confidence": 60.0},
            returns={"AAA": 0.15, "BBB": 0.02},
        )
        self.assertEqual(card["tier"], 2)
        self.assertGreaterEqual(card["confidence"], 60.0)

    def test_below_200dma_but_outperforming_keeps_tier(self):
        # Both conditions required for the step-down.
        card = self._card(
            perf={"above_200dma": False, "return_3m": 0.08},
            card={"recommended_tier": 2},
            returns={"AAA": 0.08, "BBB": 0.02},
        )
        self.assertEqual(card["tier"], 2)

    def test_recommendation_never_more_aggressive_than_sleeve(self):
        card = self._card(
            perf={"above_200dma": False, "return_3m": -0.05},
            card={"recommendation": REC_ACCUMULATE, "recommended_tier": 2},
            returns={"AAA": -0.05, "BBB": 0.05},
        )
        sleeve_idx = pe.AGGRESSIVENESS.index(REC_ACCUMULATE)
        ticker_idx = pe.AGGRESSIVENESS.index(card["recommendation"])
        self.assertGreaterEqual(ticker_idx, sleeve_idx)

    def test_sleeve_relative_strength_definition(self):
        rs = pe.sleeve_relative_strength(0.10, [0.04, 0.06])
        self.assertAlmostEqual(rs, 0.05)
        self.assertIsNone(pe.sleeve_relative_strength(None, [0.04]))
        self.assertIsNone(pe.sleeve_relative_strength(0.10, []))

    def test_not_rated_card(self):
        card = pe.build_position_card(
            ticker="ZZZ",
            perf_row={"ticker": "ZZZ"},
            sleeve_card=None,
            sleeve_tickers=["ZZZ"],
            sleeve_returns_3m={},
            ticker_material_events=0,
        )
        self.assertEqual(card["status"], "Insufficient Evidence / Not Rated")
        self.assertIsNone(card["tier"])
        # M3: HOLD is an actionable call; not-rated cards say NOT RATED.
        self.assertEqual(card["recommendation"], pe.REC_NOT_RATED)

    def test_safe_bool_degrades_to_none(self):
        # M6: missing scalar values degrade to Not Rated, never crash.
        self.assertIsNone(pe._safe_bool(pd.NA))
        self.assertIsNone(pe._safe_bool(None))
        self.assertIsNone(pe._safe_bool(float("nan")))
        self.assertTrue(pe._safe_bool(True))
        self.assertFalse(pe._safe_bool(False))

    def test_pd_na_technicals_yield_not_rated(self):
        perf = make_perf(above_200dma=pd.NA)
        self.assertEqual(
            classify(perf, make_sleeve_card()),
            "Insufficient Evidence / Not Rated",
        )


if __name__ == "__main__":
    unittest.main()
