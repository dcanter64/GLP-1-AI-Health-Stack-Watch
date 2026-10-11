# Session Handoff

## Current State

The project is a working Streamlit dashboard that writes market, news, report, validation, and history artifacts under `output/`.

The current documented live baseline is:

- Date: 2026-07-26 13:34 UTC
- Stance: Neutral
- Health Stack Flywheel Score: 59.0
- LLY AI trade score: 66.8
- Ticker rows: 38
- Accepted stories: 77
- Qualified scoring stories: 24
- Market data quality: High
- RSS errors: 0
- Tests: 38 passing (pre-Phase-1 baseline)

## Phase 1 Status (2026-10-11)

Phase 1 is implemented on branch `muse/phase-1-confirmation-structure` and is NOT merged to master.

What was built (per the operator's 2026-10-11 decisions):

- Eight sleeves per the approved rosters; AI Infrastructure Enablers (NVDA, TSM, AVGO, SMH, SOXX) kept as a supporting eighth sleeve — explicit classifier input, reported, but excluded from core health-stack breadth counts.
- `config/health_stack_sleeves.yaml` + loud-validation loader (`glp1_watch/health_stack_sleeves.py`).
- Sleeve summaries + leadership concentration (`glp1_watch/leadership_concentration.py`).
- Precedence-ordered eight-state confirmation classifier + leader/stack assessments (`glp1_watch/confirmation_state.py`).
- Heuristic news-event clustering (`glp1_watch/news_event_clustering.py`).
- Pipeline wiring, `Health Stack Confirmation Structure` report section, Streamlit expander.
- 38 new tests, all passing. Full suite: 72 passed, 4 failed — the 4 failures are pre-existing `test_news.py` date-window artifacts (fail on master too).
- Documented Phase 1 limitations: two-name Health Data and Clinical AI sleeve; heuristic clustering.

Remaining before Phase 1 is considered complete:

1. Adversarial review of the branch by a separate agent (operator requirement), with findings fixed.
2. Live validation run from a normal Windows shell: `python generate_snapshot.py` (Yahoo/RSS unreachable from sandbox/VM), confirm the new report section renders on real data and no existing outputs regress.
3. Merge to master after review + live run.

## Phase Gate

Phase 2 (sleeve-level opportunity scoring) is gated: do not begin until Phase 1 is reviewed, live-validated, merged, and explicitly approved.

The full Phase 1-5 instructions are preserved in `DECISION_LAYER_UPGRADE_SPEC.md`. Use that file as the durable source for later-phase requirements after Phase 1 is complete.

## Important Guardrails

- Preserve existing market-data collection, ticker baskets, relative-strength calculations, price-trend analysis,
  news ingestion, theme classification, scoring, reporting, validation, and command-line workflows.
- `TICKER_GROUPS` and existing market-data behavior were not changed by Phase 1; sleeves are a separate analytical layer.
- XLV, QQQ, and SPY remain comparators, not sleeve members (enforced by the loader).
- No allocation tiers or portfolio recommendations until Phase 4, and only with explicit approval.
