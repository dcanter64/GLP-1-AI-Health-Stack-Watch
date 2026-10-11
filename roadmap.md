# Roadmap

## Environment Setup

Add a project-local Python `.venv` before running the Streamlit dashboard:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Run the dashboard and project tests with the `.venv` activated.

## Current Status

GLP-1 AI Health Stack Watch v1 is finished as of 2026-07-19 and runnable as a Streamlit dashboard.

The next major effort is a phased upgrade toward a GLP-1 and AI-Health Capital Allocation Decision Layer. This upgrade must proceed one phase at a time. Phase 1 is the only approved next implementation scope unless the user explicitly approves a later phase.

Completed:

- Created a modular Python project under `glp1_watch/`.
- Added the Streamlit dashboard shell with tabs for executive summary, Eli Lilly AI trade, baskets, news, theme scores, and diagnostics.
- Added yfinance market-data ingestion with workspace-local caching.
- Added Yahoo Finance RSS ingestion, story deduplication, theme classification, ticker detection, and rules-based sentiment scoring.
- Added GLP-1 Flywheel Score and Eli Lilly AI-trade confirmation score.
- Added Markdown, CSV, JSON, JSONL, and validation/audit outputs under `output/`.
- Added graceful fallback behavior when Yahoo data is unavailable inside the Codex sandbox.
- Removed `EXAI` from the ticker universe because Exscientia went private.
- Added `start_dashboard.bat` for easy Windows startup.
- Added a strict healthcare relevance gate so unrelated Yahoo Finance stories are rejected before classification, ticker tagging, sentiment, and scoring.
- Added rejection diagnostics, accepted/rejected story counts, news confidence, and top rejected-story reasons to the audit flow.
- Added Yahoo ticker headline feeds and a keyword prefilter so broad Yahoo Finance search noise is discarded before classification.
- Added source-level filters in the News Feed tab.
- Added sidebar controls for lookback windows and refresh behavior.
- Added ticker exceptions handling for failed or private names.
- Added personal overrides via `config.local.py`.
- Added tests for scoring, theme classification, app helper behavior, and report-quality filters.
- Improved report language so score drivers are surfaced explicitly.
- Added source derivation from article URLs when Yahoo leaves source metadata blank.
- Added a 21-day story window, weaker `Other`-theme rejection rules, and a qualified-story subset for scoring calibration.
- Added `review_snapshot_history.py` to summarize score drift and the latest validation audit.
- Added output-generation tests for `glp1_watch/reporting.py`.
- Added tests for `review_snapshot_history.py` and snapshot-level consistency around accepted versus qualified story counts.
- Updated score-history tracking so accepted-story and qualified-story counts are persisted separately, with backward-compatible history backfills.
- Added `clean_outputs.bat` with confirmation, `--keep-history`, and `--yes` modes.
- Added `.gitignore` rules for Python cache artifacts, pytest cache, local overrides, and raw output cache files.
- Updated README operator notes so sandbox runs, live runs, validation interpretation, history review, and cleanup flow are documented.
- Added `pytest.ini` so local pytest collection resolves the workspace package cleanly.
- Added a per-primary-ticker and per-primary-ticker-theme cap for qualified scoring stories so one repeated ticker narrative cannot dominate the scoring subset as easily.
- Fixed saved-report LLY drawdown formatting so missing 52-week-high inputs render as `Unknown` instead of `nan%`.
- Added same-minute score-history deduplication for identical latest score, stance, AI score, and story-count rows.
- Added market-data quality audit status so partial price coverage is visible in the dashboard, reports, and validation output.
- Clarified the Streamlit report-save action and updated `start_dashboard.bat` so the launcher writes a snapshot report before opening the dashboard.
- Improved saved reports with diversified key-story selection, legal-dispute sentiment dampening, prior-run change lines, broader text cleanup, and a more reliable 52-week drawdown calculation.

Latest successful live snapshot:

- Date: 2026-07-26 13:34 UTC
- Stance: Neutral
- Score: 59.0
- LLY AI trade score: 66.8
- Ticker rows: 38
- Total stories fetched: 241
- Accepted relevant news stories: 77
- Qualified scoring stories: 24
- Scoring coverage: 24 of 77 accepted stories qualified for scoring
- News confidence: High
- RSS errors: 0
- Market data error: None
- Market data quality: High

Important note:

- The old 2026-07-09 15:06 UTC live report is no longer the best reference point for the current code because current live runs now reflect the stricter relevance gate, accepted-versus-qualified story reporting, and the newer ticker-concentration cap.
- The latest calibrated live run is `Neutral` at 59.0 with 24 qualified stories, high news confidence, and high market data quality.
- The previous cleanup blockers are now addressed: saved reports no longer show `nan%` for missing LLY drawdown data, and identical same-minute score-history appends are skipped going forward.

## Environment Notes

The Codex sandbox can resolve DNS and ping external hosts, but outbound TCP 443 is blocked inside the sandbox. Live Yahoo Finance and RSS calls work when the script is run outside the sandbox.

Yahoo Finance RSS search quality was the main limitation early in the project. Ticker headline feeds, source derivation, a keyword prefilter, stricter report-quality filters, and a ticker-theme scoring cap are now in place. The next code pass should focus more on polish and residual noise than on basic feed viability.

Use either:

```bat
start_dashboard.bat
```

or:

```bash
python generate_snapshot.py
streamlit run app.py
```

## Project Completion

The original v1 roadmap is complete as of 2026-07-19. The dashboard, live-data fallback behavior, news-quality controls, scoring calibration, audit outputs, cleanup tooling, documentation, and test coverage are all in place.

The final review confirmed:

- Latest snapshot: 2026-07-26 13:34 UTC
- Stance: Neutral
- Overall score: 59.0
- LLY AI-trade score: 66.8
- Accepted stories: 77
- Qualified scoring stories: 24
- News confidence: High
- Market data quality: High
- Score history tracked: 38 snapshots
- Tests: 38 passed

Current finish status:

- No active v1 code blockers remain.
- No further v1 roadmap work is required for the script to be considered finished.
- Future work is now organized as the gated decision-layer upgrade described below.

The final operational decisions were:

- No further `NEWS_TICKERS` / `NEWS_QUERIES` tuning was warranted; the qualified scoring subset remained diversified despite feed concentration.
- Generated point-in-time artifacts are pruned between reviews while `output/history/dashboard_scores.jsonl` is preserved.
- Same-minute history deduplication is working; valid metric changes remain recorded.

## Final Review Checklist

1. Open the newest files under `output/reports/` and `output/validation/`.
2. Confirm the latest saved live snapshot still reads `2026-07-26 13:34 UTC`, `59.0`, `Neutral`, `77 accepted`, and `24 qualified`.
3. Confirm the LLY trend line renders a real drawdown or `Unknown`, not `nan%`.
4. Run `python review_snapshot_history.py` after any output or history-writing change.

## Decision-Layer Upgrade Roadmap

The long-term goal is to evolve the project from a descriptive thematic dashboard into a GLP-1 and AI-health capital-allocation decision layer.

The durable full specification is preserved in `DECISION_LAYER_UPGRADE_SPEC.md`.

This work must be completed in deliberate phases. At the start of each phase, inspect the repository, review prior phase output and documentation, confirm tests pass, and produce a concise implementation plan for that phase only. At the end of each phase, run tests, generate current outputs, update documentation, and stop for approval.

### Phase 1: Improve the Existing Analytical Structure

Status: complete (2026-10-11); adversarial review findings fixed, live-validated on Windows, and approved for merge to `master`.

Objective: make the current report more decision-ready without issuing allocation tiers or portfolio recommendations.

Delivered:

- Configurable health-stack sleeves (`config/health_stack_sleeves.yaml`): eight sleeves per the operator-approved rosters; AI Infrastructure Enablers kept as a supporting eighth sleeve (explicit classifier input, reported, excluded from core breadth counts).
- Loud-validation sleeve loader (`glp1_watch/health_stack_sleeves.py`): unknown tickers, duplicate membership, comparator tickers as members, and wrong required-sleeve set all raise.
- Sleeve-level market confirmation summaries + leader-concentration analysis (`glp1_watch/leadership_concentration.py`).
- Precedence-ordered eight-state confirmation classifier + separate leader/stack assessments (`glp1_watch/confirmation_state.py`).
- Event-level news clustering with unique event counts and independent source counts (`glp1_watch/news_event_clustering.py`; heuristic — directional, not precise).
- New report section `Health Stack Confirmation Structure` (after Executive Summary) + Streamlit expander.

Phase 1 preserved all existing market data, news, scoring, reporting, validation, and command-line workflows (`TICKER_GROUPS` untouched; XLV/QQQ/SPY remain comparators).

Test state: 95 tests total — 91 passing, including all 57 new Phase 1 tests. Four `test_news.py` failures are pre-existing date-window artifacts (hardcoded 2026-07-08 fixtures aged past the 21-day window; fail on master too).

Completion validation: the post-fix Windows run produced 83 unique events from 85 accepted stories, including one multi-source event. Phase 2 remains gated pending explicit approval.

Documented Phase 1 limitations: two-name Health Data and Clinical AI sleeve (TEM, CERT); heuristic event clustering.

See `PHASE_1_IMPLEMENTATION_PLAN.md` for the implementation plan.

### Phase 2: Add Sleeve-Level Opportunity Scoring

Status: implemented 2026-10-11 on branch `muse/phase-2-opportunity-scoring`; pending adversarial review and live validation.

Implemented:

- Overall score renamed/clarified as the Health Stack Flywheel Score (labels only; `overall_score` snapshot key unchanged).
- Structural Thesis Score per sleeve (news-evidence proxy, Bayesian-smoothed to 50-neutral with no data).
- Market Confirmation Score per sleeve (returns, RS breadth vs XLV/SPY/QQQ, trend position, drawdown, momentum pace, volatility, concentration).
- Catalyst Score per sleeve (unique material events across six categories, sentiment-signed, per-category saturation).
- Expectations Risk Score per sleeve (acceleration, extension, no-drawdown, narrow leadership, news saturation; confidence capped at Medium — no valuation data).
- Sleeve Opportunity Scores (0.35/0.25/0.20/0.20 blend, expectations risk inverted) with six trend labels and recognition-gap flags.
- `Health Stack Opportunity Ranking` report section plus Streamlit expander.
- All weights/thresholds in `config/decision_weights.yaml` with loud validation.
- 42 new tests; full suite 137 total / 133 passing (4 pre-existing `test_news.py` date-window failures, fail on master too).

Documented Phase 2 limitations: Structural Thesis is a news-evidence proxy (no fundamentals feed); Expectations Risk has reduced confidence (no valuation/earnings-revision data); trend labels use a stateless 1M-vs-3M pace proxy until Phase 3 persistence; the partnership catalyst category shares the M&A theme (no dedicated partnership theme in the current theme set).

### Phase 3: Add Persistence, History, and Recommendation Readiness

Status: implemented 2026-10-11 on branch `muse/phase-3-persistence-readiness`; pending adversarial review and live validation.

Implemented:

- `glp1_watch/persistence_engine.py`: CSV history store (`output/history/health_stack_history.csv`, one row per sleeve per report date, upsert on reruns), persistence metrics (current/previous score, 4- and 8-report trends, consecutive improving/deteriorating streaks, streaks above/below 65/45, condition start date, max severity, second derivative), and the seven-state recommendation-readiness classification (Insufficient Evidence, Early Signal, Developing, Confirmed, Persistent, Exhausted, Repairing) with precedence ordering (Exhausted outranks Persistent) and always-reported conflicting evidence.
- `## Persistence and Decision Readiness` report section plus Streamlit expander.
- `## What Changed Since the Previous Report` section (score/trend/readiness moves, new/lost leaders, catalyst and breadth changes, data-quality changes).
- 19 new tests covering the spec's 13 Phase 3 test items.

Documented Phase 3 limitations: history starts cold (no backfill of pre-Phase-3 per-sleeve scores — early runs read Insufficient Evidence until streaks form); improvement threshold is a fixed 1.0-point noise floor; readiness classifies evidence maturity only, never portfolio actions.

### Phase 4: Add the Capital Allocation Decision Layer

Status: merged to master 2026-10-11 as `09057b4` (operator-approved merge; byte-identical verified).

Planned additions:

- Add sleeve recommendations.
- Add allocation tiers.
- Add leader decision and broad-stack decision.
- Add broad vs selective exposure classification.
- Add confidence, urgency, tactical, and strategic views.
- Add upgrade, downgrade, and invalidation conditions.

### Phase 5: Add Position-Level Decisions and Accountability

Status: in progress — implemented on branch `muse/phase-5-positions-accountability`. Operator approved all 7 design decisions 2026-10-11 (precedence-ordered 13-status classifier + explicit Not Rated outcome; sleeve tier −1 rule with floor 0 and no price-action upgrades; two-track backtesting with honesty guardrails; absolute + relative FP/FN definitions; single sleeve+ticker journal file with immutable decision fields; automatic forward-fill at maturity; §§9–10 report placement) plus guardrails (analytical only; ticker calls cannot override broad-stack exposure; insufficient history ≠ poor performance; min-n gating; dry-run purity).

Planned additions:

- Add ticker-level decisions.
- Add decision journal.
- Add historical accountability metrics.
- Add basic backtesting where reliable.

## Cleanup Notes

Historical output and cache files may still contain older ticker universes, including `EXAI`, from prior runs. The live config no longer requests `EXAI`.

Generated point-in-time outputs are useful for local audit review but should not be versioned long term. Git should ignore generated reports, validation audits, classified CSVs, and raw RSS payloads while preserving `output/history/dashboard_scores.jsonl` as the durable score-history audit trail.

That cleanup pass is now in place:

- Use `clean_outputs.bat` for an interactive cleanup.
- Use `clean_outputs.bat --keep-history` to preserve `output/history/dashboard_scores.jsonl`.
- Use `clean_outputs.bat --yes` to skip the confirmation prompt.





