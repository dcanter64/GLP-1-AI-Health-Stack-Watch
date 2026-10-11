"""Phase 4: Capital Allocation Decision Layer tests.

Covers the 19 spec'd Phase 4 test items plus history-store guarantees.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd

from glp1_watch import decision_engine as de


CONFIDENCE_WEIGHTS = {
    "signal_persistence": 0.15,
    "price_fundamentals_agreement": 0.12,
    "breadth": 0.12,
    "data_quality": 0.10,
    "catalyst_diversity": 0.08,
    "leadership_concentration": 0.10,
    "time_horizon_agreement": 0.08,
    "conflict_degree": 0.10,
    "historical_stability": 0.15,
}


def make_opp(sleeve="Sleeve A", opportunity=60.0, **overrides):
    row = {
        "sleeve": sleeve,
        "required": True,
        "opportunity_score": opportunity,
        "structural_score": 60.0,
        "market_confirmation_score": 58.0,
        "catalyst_score": 55.0,
        "expectations_risk_score": 30.0,
        "trend": "Neutral and improving",
        "recognition_gap": "none",
    }
    row.update(overrides)
    return row


def make_persist(sleeve="Sleeve A", readiness="Confirmed", **overrides):
    row = {
        "sleeve": sleeve,
        "readiness": readiness,
        "current_score": 60.0,
        "previous_score": 58.0,
        "score_change": 2.0,
        "four_report_trend": "improving",
        "consecutive_improving": 2,
        "consecutive_deteriorating": 0,
        "consecutive_above_strong": 0,
        "consecutive_below_weak": 0,
        "second_derivative": "steady",
        "conflicts": [],
    }
    row.update(overrides)
    return row


def make_sleeve(name="Sleeve A", tickers=("AAA",), required=True):
    return SimpleNamespace(name=name, tickers=tickers, required=required)


def make_card(**overrides):
    persist = make_persist(**overrides.pop("persist", {}))
    opp = make_opp(**overrides.pop("opp", {}))
    params = {
        "sleeve": "Sleeve A",
        "sleeve_tickers": ["AAA"],
        "opp_row": opp,
        "persist_row": persist,
        "prev": None,
        "sleeve_history": pd.DataFrame(),
        "confirmation_state": "Selectively Confirming",
        "concentration": {"verdict": "broad", "pct_above_50dma": 0.6},
        "market_data_quality": {"status": "High"},
        "news_confidence": "High",
        "news_events": pd.DataFrame(),
        "confidence_weights": CONFIDENCE_WEIGHTS,
    }
    params.update(overrides)
    return de.build_decision_card(**params)


def decision_history_frame(rows):
    return pd.DataFrame(rows, columns=de.DECISION_COLUMNS)


class RecommendationThresholdTests(unittest.TestCase):
    def test_target_tier_matrix(self):
        self.assertEqual(de.target_tier("Persistent", 70.0), 4)
        self.assertEqual(de.target_tier("Persistent", 60.0), 3)
        self.assertEqual(de.target_tier("Confirmed", 70.0), 3)
        self.assertEqual(de.target_tier("Confirmed", 50.0), 2)
        self.assertEqual(de.target_tier("Developing", 58.0), 2)
        self.assertEqual(de.target_tier("Developing", 50.0), 1)
        self.assertEqual(de.target_tier("Early Signal", 55.0), 1)
        self.assertEqual(de.target_tier("Early Signal", 40.0), 0)
        self.assertEqual(de.target_tier("Repairing", 40.0), 1)
        self.assertIsNone(de.target_tier("Insufficient Evidence", 60.0))
        self.assertIsNone(de.target_tier("Confirmed", float("nan")))

    def test_recommendation_categories_used(self):
        card = make_card(opp=make_opp(opportunity=70.0), persist=make_persist(readiness="Persistent"))
        self.assertEqual(card["recommendation"], "STRONG INCREASE")
        self.assertEqual(card["recommended_tier"], 4)


class AllocationTierTests(unittest.TestCase):
    def test_tier_names_cover_0_to_4(self):
        self.assertEqual(len(de.TIER_NAMES), 5)
        self.assertEqual(de.TIER_NAMES[0], "Avoid")
        self.assertEqual(de.TIER_NAMES[4], "Maximum-conviction overweight")

    def test_tier_name_none(self):
        self.assertEqual(de.tier_name(None), "not rated")


class TierChangeLimitTests(unittest.TestCase):
    def test_normal_change_limited_to_one_tier(self):
        card = make_card(
            opp=make_opp(opportunity=70.0),
            persist=make_persist(readiness="Confirmed"),
            prev={"recommended_tier": 1, "readiness": "Developing"},
        )
        # Target is 3; limiter allows only 1 -> 2.
        self.assertEqual(card["recommended_tier"], 2)
        self.assertEqual(card["tier_change"], 1)

    def test_severe_break_allows_two_tiers(self):
        history = pd.DataFrame(
            [
                {"sleeve": "Sleeve A", "breadth_50dma": 0.50, "material_event_count": 1, "opportunity_score": 50.0},
                {"sleeve": "Sleeve A", "breadth_50dma": 0.55, "material_event_count": 1, "opportunity_score": 55.0},
                {"sleeve": "Sleeve A", "breadth_50dma": 0.65, "material_event_count": 3, "opportunity_score": 70.0},
            ]
        )
        card = make_card(
            opp=make_opp(opportunity=70.0),
            persist=make_persist(readiness="Confirmed"),
            prev={"recommended_tier": 1, "readiness": "Developing"},
            sleeve_history=history,
        )
        self.assertTrue(card["severe_break"])
        self.assertEqual(card["recommended_tier"], 3)
        self.assertEqual(card["recommendation"], "STRONG INCREASE")

    def test_initialization_has_no_limiter(self):
        card = make_card(
            opp=make_opp(opportunity=70.0),
            persist=make_persist(readiness="Persistent"),
            prev=None,
        )
        self.assertEqual(card["recommended_tier"], 4)


class LeaderStackTests(unittest.TestCase):
    def _cards(self, leader_rec, leader_tier, stack_opps):
        cards = [
            {
                "sleeve": "Established GLP-1 Leaders",
                "required": True,
                "opportunity_score": 70.0,
                "readiness": "Confirmed",
                "recommended_tier": leader_tier,
                "previous_tier": leader_tier,
                "tier_change": 0,
                "recommendation": leader_rec,
                "confidence": 70.0,
                "confidence_band": "High",
                "urgency": "Moderate",
                "rationale": "test",
            }
        ]
        for i, opp in enumerate(stack_opps):
            cards.append(
                {
                    "sleeve": f"Other {i}",
                    "required": True,
                    "opportunity_score": opp,
                    "readiness": "Insufficient Evidence",
                    "recommended_tier": 1,
                    "previous_tier": 1,
                    "tier_change": 0,
                    "recommendation": "HOLD",
                    "confidence": 40.0,
                    "confidence_band": "Moderate",
                    "urgency": "Low",
                    "rationale": "test",
                }
            )
        return cards

    def test_strong_leader_weak_stack_disagree(self):
        cards = self._cards("INCREASE", 3, [40.0, 38.0, 42.0, 39.0, 41.0, 37.0])
        leader = de.build_leader_decision(cards)
        exposure = de.classify_exposure(
            confirmation_state="Narrowly Confirming",
            concentration={"verdict": "concentrated", "pct_above_50dma": 0.3},
            cards=cards,
        )
        stack = de.build_stack_decision(cards, exposure, 42.0)
        self.assertEqual(exposure, "No New Capital")
        self.assertFalse(de.leaders_stack_agree(leader, stack))

    def test_weak_leader_improving_stack_disagree(self):
        cards = self._cards("REDUCE", 1, [58.0, 60.0, 57.0, 62.0, 59.0, 61.0])
        for card in cards[1:]:
            card["recommendation"] = "INCREASE"
        leader = de.build_leader_decision(cards)
        exposure = de.classify_exposure(
            confirmation_state="Broadly Confirming",
            concentration={"verdict": "broad", "pct_above_50dma": 0.65},
            cards=cards,
        )
        stack = de.build_stack_decision(cards, exposure, 58.0)
        self.assertEqual(leader["direction"], "defensive")
        self.assertEqual(stack["stance"], "constructive")
        self.assertFalse(de.leaders_stack_agree(leader, stack))


class ExposureTests(unittest.TestCase):
    def _cards(self, opps):
        return [
            {
                "sleeve": f"S{i}",
                "required": True,
                "opportunity_score": opp,
                "readiness": "Confirmed",
            }
            for i, opp in enumerate(opps)
        ]

    def test_broad_confirmation(self):
        exposure = de.classify_exposure(
            confirmation_state="Broadly Confirming",
            concentration={"verdict": "broad", "pct_above_50dma": 0.6},
            cards=self._cards([60.0] * 7),
        )
        self.assertEqual(exposure, "Broad")

    def test_selective_confirmation(self):
        exposure = de.classify_exposure(
            confirmation_state="Selectively Confirming",
            concentration={"verdict": "moderate", "pct_above_50dma": 0.5},
            cards=self._cards([58.0] * 7),
        )
        self.assertEqual(exposure, "Selective")

    def test_leader_only_exposure(self):
        exposure = de.classify_exposure(
            confirmation_state="Leader-Dependent Confirming",
            concentration={"verdict": "concentrated", "pct_above_50dma": 0.4},
            cards=self._cards([58.0] * 7),
        )
        self.assertEqual(exposure, "Leader-Only")

    def test_empty_cards_default_to_exploratory(self):
        # m2: no sleeves means no evidence for broad exposure.
        self.assertEqual(
            de.classify_exposure(
                confirmation_state="Broadly Confirming",
                concentration={"verdict": "broad", "pct_above_50dma": 0.8},
                cards=[],
            ),
            "Exploratory",
        )


class CatalystWatchTests(unittest.TestCase):
    def test_early_signal_becomes_catalyst_watch(self):
        card = make_card(
            opp=make_opp(opportunity=55.0),
            persist=make_persist(readiness="Early Signal", consecutive_improving=1),
            prev={"recommended_tier": 1, "readiness": "Insufficient Evidence"},
        )
        self.assertEqual(card["recommendation"], "CATALYST-DEPENDENT WATCH")

    def test_weak_early_signal_becomes_watch_for_reentry(self):
        card = make_card(
            opp=make_opp(opportunity=40.0),
            persist=make_persist(readiness="Early Signal", consecutive_improving=1),
            prev={"recommended_tier": 0, "readiness": "Insufficient Evidence"},
        )
        self.assertEqual(card["recommendation"], "WATCH FOR RE-ENTRY")
        self.assertEqual(card["recommended_tier"], 0)


class RecognitionGapTests(unittest.TestCase):
    def test_recognition_gap_surfaced(self):
        card = make_card(opp=make_opp(recognition_gap="unrecognized strength"))
        self.assertIn("recognition gap", card["rationale"])
        risks = de.build_decision_risks(
            [card],
            {"direction": "neutral"},
            {"stance": "neutral", "exposure": "Selective"},
        )
        self.assertTrue(any("recognition gap" in r for r in risks))


class ExpectationsRiskTests(unittest.TestCase):
    def test_high_expectations_risk_tempers_confidence(self):
        base = make_card(opp=make_opp(expectations_risk_score=30.0))
        stressed = make_card(opp=make_opp(expectations_risk_score=75.0))
        self.assertLess(stressed["confidence"], base["confidence"])


class EarlyRepairTests(unittest.TestCase):
    def test_repairing_accumulates_gradually(self):
        card = make_card(
            opp=make_opp(opportunity=42.0),
            persist=make_persist(
                readiness="Repairing",
                consecutive_improving=2,
                four_report_trend="improving",
            ),
            prev={"recommended_tier": 0, "readiness": "Insufficient Evidence"},
        )
        self.assertEqual(card["recommendation"], "ACCUMULATE GRADUALLY")
        self.assertEqual(card["recommended_tier"], 1)


class ConfidenceScoringTests(unittest.TestCase):
    def test_confidence_bounds_and_bands(self):
        self.assertEqual(de.confidence_band(85.0), "Very High")
        self.assertEqual(de.confidence_band(70.0), "High")
        self.assertEqual(de.confidence_band(50.0), "Moderate")
        self.assertEqual(de.confidence_band(20.0), "Low")

    def test_confidence_weighted_score(self):
        inputs = {k: 1.0 for k in CONFIDENCE_WEIGHTS}
        self.assertEqual(de.confidence_score(inputs, CONFIDENCE_WEIGHTS), 100.0)
        inputs = {k: 0.0 for k in CONFIDENCE_WEIGHTS}
        self.assertEqual(de.confidence_score(inputs, CONFIDENCE_WEIGHTS), 0.0)
        inputs = {k: 0.5 for k in CONFIDENCE_WEIGHTS}
        self.assertEqual(de.confidence_score(inputs, CONFIDENCE_WEIGHTS), 50.0)

    def test_confidence_rejects_bad_weights(self):
        inputs = {k: 0.5 for k in CONFIDENCE_WEIGHTS}
        bad = dict(CONFIDENCE_WEIGHTS)
        bad["breadth"] = 0.99
        with self.assertRaises(ValueError):
            de.confidence_score(inputs, bad)


class UrgencyScoringTests(unittest.TestCase):
    def test_urgency_ladder(self):
        base = dict(
            readiness="Confirmed",
            readiness_changed=False,
            tier_change=0,
            second_derivative="steady",
            streak_continuing=False,
        )
        self.assertEqual(de.urgency_for(regulatory_hit=True, **base), "Immediate")
        self.assertEqual(
            de.urgency_for(regulatory_hit=False, readiness_changed=True, **{k: v for k, v in base.items() if k != "readiness_changed"}),
            "High",
        )
        changed = dict(base, readiness_changed=False, streak_continuing=True)
        self.assertEqual(de.urgency_for(regulatory_hit=False, **changed), "Moderate")
        self.assertEqual(de.urgency_for(regulatory_hit=False, **base), "Low")

    def test_exhausted_onset_is_immediate(self):
        self.assertEqual(
            de.urgency_for(
                regulatory_hit=False,
                readiness="Exhausted",
                readiness_changed=True,
                tier_change=-1,
                second_derivative="steady",
                streak_continuing=False,
            ),
            "Immediate",
        )


class TacticalStrategicTests(unittest.TestCase):
    def test_views_agree(self):
        card = make_card(
            opp=make_opp(structural_score=65.0),
            persist=make_persist(four_report_trend="improving"),
        )
        self.assertTrue(card["views_agree"])

    def test_tactical_strategic_disagreement(self):
        card = make_card(
            opp=make_opp(structural_score=70.0),
            persist=make_persist(four_report_trend="deteriorating", consecutive_deteriorating=2, consecutive_improving=0),
        )
        self.assertFalse(card["views_agree"])


class ConditionTests(unittest.TestCase):
    def test_upgrade_condition_measurable(self):
        text = de.upgrade_condition("Confirmed", 2, 58.0)
        self.assertIn("Tier 3", text)
        self.assertIn("55", text)
        self.assertIn("2 consecutive reports", text)
        top_text = de.upgrade_condition("Persistent", 3, 70.0)
        self.assertIn("Tier 4", top_text)
        self.assertIn("65", top_text)

    def test_downgrade_condition_measurable(self):
        text = de.downgrade_condition(2)
        self.assertIn("Tier 1", text)
        self.assertIn("Exhausted", text)

    def test_invalidation_condition_measurable(self):
        text = de.invalidation_condition()
        self.assertIn("40", text)
        self.assertIn("regulatory", text.lower())

    def test_no_upgrade_path_at_max_tier(self):
        self.assertIn("maximum", de.upgrade_condition("Persistent", 4, 70.0).lower())

    def test_upgrade_condition_reports_banked_progress(self):
        # m5: conditions are state-aware, not static text.
        persist = make_persist(consecutive_above_strong=1, consecutive_improving=2)
        text = de.upgrade_condition("Confirmed", 2, 58.0, persist)
        self.assertIn("Now:", text)
        self.assertIn("1 consecutive report(s) above 65", text)


class NoChangeBehaviorTests(unittest.TestCase):
    def test_insufficient_evidence_holds(self):
        card = make_card(
            persist=make_persist(readiness="Insufficient Evidence", consecutive_improving=0),
            prev={"recommended_tier": 2, "readiness": "Insufficient Evidence"},
        )
        self.assertEqual(card["recommendation"], "HOLD")
        self.assertEqual(card["recommended_tier"], 2)
        self.assertEqual(card["tier_change"], 0)

    def test_nan_opportunity_does_not_fabricate(self):
        card = make_card(
            opp=make_opp(opportunity=float("nan")),
            prev={"recommended_tier": 2, "readiness": "Confirmed"},
        )
        self.assertEqual(card["recommendation"], "HOLD")
        self.assertEqual(card["recommended_tier"], 2)


class RegulatoryOverrideTests(unittest.TestCase):
    def _events(self):
        return pd.DataFrame(
            [
                {
                    "themes": "Regulatory Risk",
                    "tickers": "LLY",
                    "material_event": True,
                    "title": "FDA action",
                }
            ]
        )

    def test_override_detected(self):
        self.assertTrue(de.regulatory_override(["LLY", "NVO"], self._events()))
        self.assertFalse(de.regulatory_override(["RXRX"], self._events()))

    def test_override_caps_tier_and_forces_immediate(self):
        card = make_card(
            opp=make_opp(opportunity=70.0),
            persist=make_persist(readiness="Confirmed"),
            prev={"recommended_tier": 3, "readiness": "Confirmed"},
            sleeve_tickers=["LLY"],
            news_events=self._events(),
        )
        self.assertTrue(card["regulatory_override"])
        self.assertLessEqual(card["recommended_tier"], 1)
        self.assertEqual(card["urgency"], "Immediate")
        self.assertEqual(card["implementation_speed"], "Immediate")

    def test_override_does_not_fabricate_tier_on_cold_start(self):
        # M1: no previous tier + inconclusive evidence + regulatory hit
        # must stay unrated, not invent an Exploratory allocation.
        card = make_card(
            opp=make_opp(opportunity=52.0),
            persist=make_persist(readiness="Insufficient Evidence"),
            prev=None,
            sleeve_tickers=["LLY"],
            news_events=self._events(),
        )
        self.assertTrue(card["regulatory_override"])
        self.assertIsNone(card["recommended_tier"])
        self.assertEqual(card["recommendation"], "HOLD")

    def test_override_respects_two_tier_cap(self):
        # m1: a 4 -> 1 derisk must go through the limiter, not around it.
        card = make_card(
            opp=make_opp(opportunity=70.0),
            persist=make_persist(readiness="Persistent", consecutive_above_strong=4),
            prev={"recommended_tier": 4, "readiness": "Persistent"},
            sleeve_tickers=["LLY"],
            news_events=self._events(),
        )
        self.assertTrue(card["severe_break"])
        self.assertEqual(card["recommended_tier"], 2)
        self.assertEqual(card["tier_change"], -2)


class ExhaustionTests(unittest.TestCase):
    def test_exhausted_steps_down_one_tier(self):
        persist = make_persist(readiness="Exhausted")
        persist["_exhausted_streak"] = 0
        card = make_card(
            opp=make_opp(opportunity=70.0),
            persist=persist,
            prev={"recommended_tier": 3, "readiness": "Confirmed"},
        )
        self.assertEqual(card["recommendation"], "REDUCE")
        self.assertEqual(card["recommended_tier"], 2)

    def test_persistent_exhaustion_strong_reduce(self):
        persist = make_persist(readiness="Exhausted")
        persist["_exhausted_streak"] = 2
        card = make_card(
            opp=make_opp(opportunity=70.0),
            persist=persist,
            prev={"recommended_tier": 3, "readiness": "Exhausted"},
        )
        self.assertEqual(card["recommendation"], "STRONG REDUCE")
        self.assertEqual(card["recommended_tier"], 1)

    def test_strong_reduce_at_tier_zero_becomes_avoid(self):
        # m3: tier 0 is "Avoid" — the category must match the taxonomy.
        persist = make_persist(readiness="Exhausted")
        persist["_exhausted_streak"] = 2
        card = make_card(
            opp=make_opp(opportunity=70.0),
            persist=persist,
            prev={"recommended_tier": 1, "readiness": "Exhausted"},
        )
        self.assertEqual(card["recommended_tier"], 0)
        self.assertEqual(card["recommendation"], "AVOID NEW CAPITAL")

    def test_new_exhaustion_with_collapse_steps_two(self):
        # m4: a genuine severe break allows the full two-tier derisk.
        persist = make_persist(readiness="Exhausted", score_change=-16.0)
        persist["_exhausted_streak"] = 0
        card = make_card(
            opp=make_opp(opportunity=54.0),
            persist=persist,
            prev={"recommended_tier": 4, "readiness": "Confirmed"},
        )
        self.assertTrue(card["severe_break"])
        self.assertEqual(card["recommended_tier"], 2)
        self.assertEqual(card["recommendation"], "STRONG REDUCE")

    def test_consecutive_exhausted_counts(self):
        history = decision_history_frame(
            [
                {"as_of_date": "2026-10-01", "sleeve": "S", "readiness": "Confirmed",
                 "previous_tier": 2, "recommended_tier": 3, "tier_change": 1,
                 "recommendation": "INCREASE", "confidence": 60.0, "urgency": "Moderate"},
                {"as_of_date": "2026-10-08", "sleeve": "S", "readiness": "Exhausted",
                 "previous_tier": 3, "recommended_tier": 2, "tier_change": -1,
                 "recommendation": "REDUCE", "confidence": 55.0, "urgency": "Immediate"},
                {"as_of_date": "2026-10-15", "sleeve": "S", "readiness": "Exhausted",
                 "previous_tier": 2, "recommended_tier": 2, "tier_change": 0,
                 "recommendation": "HOLD / STOP ADDING", "confidence": 50.0, "urgency": "High"},
            ]
        )
        self.assertEqual(de.consecutive_exhausted(history, "S"), 2)
        self.assertEqual(de.consecutive_exhausted(history, "Other"), 0)


class DecisionHistoryTests(unittest.TestCase):
    def test_roundtrip_and_upsert(self):
        with tempfile.TemporaryDirectory() as tmp:
            cards = [make_card()]
            as_of = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
            first = de.append_decision_history(tmp, cards, as_of)
            self.assertEqual(len(first), 1)
            # Same-day rewrite upserts instead of duplicating.
            second = de.append_decision_history(tmp, cards, as_of)
            self.assertEqual(len(second), 1)
            loaded = de.load_decision_history(tmp)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded.iloc[0]["recommendation"], cards[0]["recommendation"])

    def test_future_dates_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            as_of = datetime(2099, 1, 1, tzinfo=timezone.utc)
            with self.assertRaisesRegex(ValueError, "future report date"):
                de.append_decision_history(tmp, [make_card()], as_of)

    def test_previous_decision_lookup(self):
        history = decision_history_frame(
            [
                {"as_of_date": "2026-10-01", "sleeve": "S", "readiness": "Confirmed",
                 "previous_tier": 1, "recommended_tier": 2, "tier_change": 1,
                 "recommendation": "INCREASE", "confidence": 60.0, "urgency": "Moderate"},
            ]
        )
        prev = de.previous_decision(history, "S")
        self.assertEqual(int(prev["recommended_tier"]), 2)
        self.assertIsNone(de.previous_decision(history, "Missing"))
        self.assertIsNone(de.previous_decision(pd.DataFrame(), "S"))


if __name__ == "__main__":
    unittest.main()
