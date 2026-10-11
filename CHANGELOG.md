# Changelog

## Unreleased

### Added (Phase 1, 2026-10-11)

- `config/health_stack_sleeves.yaml`: eight configurable health-stack sleeves (seven required + supporting AI Infrastructure Enablers) with operator-approved rosters.
- `glp1_watch/health_stack_sleeves.py`: YAML loader with loud validation — unknown tickers, duplicate membership across sleeves, comparator tickers (XLV/QQQ/SPY) as members, and a wrong required-sleeve set all raise `ValueError`.
- `glp1_watch/leadership_concentration.py`: sleeve-level market summaries (3M return, RS vs XLV/SPY, 50/200DMA participation, best/worst names, confirming/mixed/deteriorating/insufficient-data status) and leadership-concentration analysis (broad/selective/leader-dependent). Core breadth counts use the seven required sleeves only.
- `glp1_watch/confirmation_state.py`: precedence-ordered eight-state confirmation classifier (Broadly Confirming, Selectively Confirming, Leader-Dependent, Fragmenting, Early Repair, Deteriorating, Failing, Insufficient Evidence), separate leader/stack assessments, and a leader-vs-stack contradiction line.
- `glp1_watch/news_event_clustering.py`: heuristic news-event clustering with unique-event, independent-source, and material-event counts (documented as directional, not precise).
- New report section `Health Stack Confirmation Structure` (after Executive Summary) plus a matching Streamlit expander; legacy snapshots without Phase 1 keys keep byte-identical report output.
- 57 new tests across `test_health_stack_sleeves.py`, `test_leadership_concentration.py`, `test_confirmation_state.py`, `test_news_event_clustering.py`, and `test_confirmation_section.py`.
- Added `pyyaml>=6.0` to `requirements.txt`.

### Added (Phase 2, 2026-10-11)

- `config/decision_weights.yaml`: operator-tunable weights for all Phase 2 scores, interpretation bands (80/65/55/45/35/20/0), catalyst per-category saturation, trend thresholds, and recognition-gap thresholds.
- `glp1_watch/decision_weights.py`: loud-validating loader — negative weights, weight groups not summing to 1.0, unsorted/incomplete interpretation bands, and bad thresholds all raise `ValueError`.
- `glp1_watch/structural_thesis.py`: per-sleeve Structural Thesis Score (0-100) from qualified-story sentiment across thesis-relevant themes (Bayesian-smoothed; no evidence = 50 neutral at Low confidence, never 0). Explicitly a news-evidence proxy — no fundamentals feed exists.
- `glp1_watch/market_confirmation.py`: per-sleeve Market Confirmation Score (0-100) from 3M returns, RS vs XLV/SPY/QQQ breadth, 50/200DMA position, 52w-high proximity, 1M-vs-3M momentum pace, price-history volatility, and within-sleeve concentration. Missing components are skipped with weights renormalized and the gap noted.
- `glp1_watch/catalyst_score.py`: per-sleeve Catalyst Score (0-100) from unique material events mapped to six catalyst categories (commercial, clinical, regulatory, partnership, M&A, policy), signed by event sentiment, saturated per category so raw counts cannot dominate.
- `glp1_watch/expectations_risk.py`: per-sleeve Expectations Risk Score (0-100, higher = riskier) from price acceleration, 50DMA extension, absence of drawdown, narrow leadership, and positive-news saturation. Valuation and earnings-revision data are unavailable, so confidence is capped at Medium and the gap is reported, never invented.
- `glp1_watch/opportunity.py`: per-sleeve Opportunity Score (0-100) blending the four components (0.35/0.25/0.20/0.20, expectations risk inverted); missing components or <50% coverage yield no score rather than a partial blend. Six trend labels (Strong/Neutral/Weak × improving/decelerating-deteriorating) using a stateless 1M-vs-3M pace proxy (documented; real persistence is Phase 3). Recognition-gap flag (strong thesis + strong catalysts, weak market confirmation).
- Overall score renamed to `Health Stack Flywheel Score` in report and dashboard labels (the `overall_score` snapshot key is unchanged for history compatibility).
- New report section `Health Stack Opportunity Ranking` (after Confirmation Structure) with the ranked table, decision-neutral strongest/weakest-evidence interpretation, recognition-gap flags, and documented data limitations; plus a matching Streamlit expander.
- 42 new tests across `test_decision_weights.py`, `test_structural_thesis.py`, `test_market_confirmation.py`, `test_catalyst_score.py`, `test_expectations_risk.py`, `test_opportunity.py`, and `test_opportunity_section.py`.

### Planned

- Phase 3 (persistence, history, recommendation readiness) is gated: do not begin until Phase 2 is reviewed, live-validated, merged, and explicitly approved.
- Later phases are gated and will not begin until the prior phase has been reviewed and approved.
- Preserve the full Phase 1-5 upgrade specification in `DECISION_LAYER_UPGRADE_SPEC.md`.

### Recent Baseline

- Latest documented live run: 2026-07-26 13:34 UTC.
- Current documented tests: 38 passing (pre-Phase-1 baseline).
- Review fixes (2026-10-11, same branch): real fuzzy event clustering (theme + ticker overlap + title Jaccard >= 0.3 + 72h window) replacing exact key grouping; `qualified_theme_count` and `news_top_ticker_share` wired into the classifier as downward-only constraints (catalyst breadth, news breadth, news-on-leader concentration); AI Infrastructure Enablers as an explicit classifier input (a deteriorating supporting sleeve blocks Broadly Confirming; it can never upgrade the read).
- Phase 1 test state: 95 tests total — 91 passing, including all 57 new Phase 1 tests. Four `test_news.py` failures are pre-existing date-window artifacts (hardcoded 2026-07-08 fixtures aged past the 21-day news window as of 2026-10-11); they fail on master too and are unrelated to Phase 1.
- Current project status: v1 dashboard and Phase 1 complete and merged; Phase 1 adversarial review findings were fixed and live validation passed on Windows 2026-10-11. Phase 2 approved 2026-10-11 and implemented on branch `muse/phase-2-opportunity-scoring`, pending separate-agent adversarial review and live validation.
- Phase 2 test state: 137 tests total — 133 passing, including all 42 new Phase 2 tests. The same four `test_news.py` failures are pre-existing date-window artifacts (hardcoded 2026-07-08 fixtures aged past the 21-day news window as of 2026-10-11); they fail on master too and are unrelated to Phase 2.
