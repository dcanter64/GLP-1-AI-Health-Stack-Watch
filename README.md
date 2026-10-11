# GLP-1 AI Health Stack Watch

Streamlit dashboard for tracking the GLP-1, Eli Lilly, AI-biotech, cardiometabolic, and healthcare-AI stack trade using free public data.

## Status

Version 1 is finished as of 2026-07-19. The Streamlit dashboard pulls yfinance market data, ingests Yahoo Finance RSS stories, classifies news themes, scores the GLP-1 flywheel, and writes audit/report artifacts on each run.

A major phased upgrade is underway. The long-term target is to evolve the project into a specialized **GLP-1 and AI-Health Capital Allocation Decision Layer**, but this must be done one approved phase at a time. Phase 1 (analytical structure only; no allocation tiers or portfolio recommendations) is implemented on branch `muse/phase-1-confirmation-structure` and pending adversarial review plus a live validation run before merge.

The news engine now uses ticker headline feeds, a keyword prefilter, source derivation, a 21-day story window, and a stricter healthcare relevance gate before story classification, sentiment, ticker tagging, and scoring. The scoring path also uses a smaller qualified-story subset so one noisy feed cannot overwhelm the flywheel score.

The local support tooling is now in good shape too: report/output generation is covered by tests, the snapshot-history review script is tested, and cleanup now supports confirmation plus history-preserving mode.

Latest successful live run:

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

Final code note:

- The latest live snapshot reflects the accepted-versus-qualified story model and the per-ticker-theme scoring cap used to reduce ticker concentration.
- Missing LLY drawdown inputs now render as `Unknown` instead of `nan%` in saved reports.
- Future repeated live runs inside the same minute skip appending a score-history row when the latest row has identical score, stance, AI score, and story counts.
- Report output now diversifies key stories, tempers legal-dispute sentiment, includes change-versus-prior-run lines, and computes 52-week drawdown from the available one-year price window.

See `roadmap.md` for the completion record and operating notes.

## Decision-Layer Upgrade

The upgrade will be implemented in gated phases:

- Phase 1: analytical structure, investment sleeves, confirmation-state classification, leader concentration, leader-vs-stack conclusions, and news event clustering.
- Phase 2: sleeve-level opportunity scoring.
- Phase 3: persistence, history, and recommendation-readiness classification.
- Phase 4: explicit capital-allocation decision layer.
- Phase 5: position-level decisions, decision journal, and accountability.

Only Phase 1 has been implemented. Later phases require explicit review and approval.

Phase 1 adds a `Health Stack Confirmation Structure` section to the report and dashboard:

- Eight configurable sleeves in `config/health_stack_sleeves.yaml` (seven required plus a supporting AI Infrastructure Enablers sleeve). Sleeve membership is operator-editable; the loader validates loudly: unknown tickers, duplicate membership across sleeves, comparator tickers (XLV/QQQ/SPY) as members, and a wrong required-sleeve set all raise instead of degrading silently.
- Sleeve-level market summaries: 3M return, percent outperforming XLV/SPY, percent above 50/200DMA, best/worst names, and a confirming/mixed/deteriorating/insufficient-data status.
- Leadership-concentration analysis with a broad/selective/leader-dependent verdict. Core breadth counts use the seven required sleeves only, so semiconductor performance cannot make weak healthcare breadth look healthy.
- A precedence-ordered eight-state confirmation classifier: Broadly Confirming, Selectively Confirming, Leader-Dependent, Fragmenting, Early Repair, Deteriorating, Failing, Insufficient Evidence.
- Separate leader and stack assessments plus a named leader-vs-stack contradiction.
- Heuristic news-event clustering (theme + title-token key) with unique-event, independent-source, and material-event counts.

Phase 1 limitations (documented, not fixed):

- The Health Data and Clinical AI sleeve has only two names (TEM, CERT); its status swings on single names.
- Event clustering is heuristic: near-identical headlines can merge distinct events, and very differently worded headlines can split one event. Counts are directional, not precise.

Planning documents:

- `DECISION_LAYER_UPGRADE_SPEC.md`
- `PHASE_1_IMPLEMENTATION_PLAN.md`
- `CHANGELOG.md`
- `SESSION_HANDOFF.md`

## Run

On Windows, double-click:

```bat
start_dashboard.bat
```

The batch launcher checks dependencies, writes a fresh snapshot report under `output/reports/`, then starts Streamlit.

Or run manually:

```bash
pip install -r requirements.txt
streamlit run app.py
```

To generate the output artifacts without launching Streamlit:

```bash
python generate_snapshot.py
```

To review score-history drift and the latest validation audit after a live run:

```bash
python review_snapshot_history.py
```

Recommended morning restart:

```bash
python generate_snapshot.py
python review_snapshot_history.py
```

## Operator Notes

- `Codex sandbox run`: useful for code changes, tests, and report formatting work. Live Yahoo Finance and RSS calls may fall back because outbound HTTPS is blocked here.
- `Normal Windows shell run`: use this for `python generate_snapshot.py` when you want a real live snapshot and fresh output artifacts.
- `Validation audit`: compare `Accepted stories` with `Qualified scoring stories`. The qualified count is the smaller subset that actually influences scoring and news confidence.
- `Market data quality`: check `High` / `Partial` / `Low` before trusting market-confirmation scores. A run can have no market-data exception but still have sparse ticker coverage.
- `Ticker concentration`: accepted-story counts can still be concentrated in a few ticker feeds, but the scoring subset now caps stories per primary ticker and per primary ticker within the same theme.
- `History review`: `python review_snapshot_history.py` summarizes accepted-story drift and qualified-story drift when that data is available in the history file.
- `Cleanup`: run `clean_outputs.bat` for an interactive cleanup. Use `clean_outputs.bat --keep-history` to preserve score drift history, or `clean_outputs.bat --yes` to skip confirmation.
- `Output retention`: generated reports, validation audits, classified CSVs, and raw RSS payloads are ignored by git. Keep `output/history/dashboard_scores.jsonl` as the long-running audit trail.

## Outputs

- `output/reports/`: markdown snapshot reports
- `output/raw/`: raw RSS payloads and cache files
- `output/classified/`: ticker performance and classified article CSVs
- `output/history/`: JSONL score history
- `output/validation/`: run audit markdown

## Notes

- The Codex sandbox blocks outbound HTTPS, so live Yahoo calls may show fallback diagnostics when run inside the sandbox.
- Running from a normal Windows shell or by double-clicking `start_dashboard.bat` allows Yahoo Finance data to load.
- `EXAI` has been removed from the ticker universe because Exscientia went private.
- Yahoo Finance RSS search is still noisy. The dashboard now uses ticker headline feeds, filters unrelated finance and tech stories before classification, and derives cleaner publisher names from article URLs when feed metadata is blank.
- Optional personal overrides can be added in `config.local.py` at the project root. See `config.local.py.example`.




