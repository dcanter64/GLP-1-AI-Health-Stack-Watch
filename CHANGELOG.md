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

### Planned

- Phase 2 (sleeve-level opportunity scoring) is gated: do not begin until Phase 1 is reviewed and approved.
- Later phases are gated and will not begin until the prior phase has been reviewed and approved.
- Preserve the full Phase 1-5 upgrade specification in `DECISION_LAYER_UPGRADE_SPEC.md`.

### Recent Baseline

- Latest documented live run: 2026-07-26 13:34 UTC.
- Current documented tests: 38 passing (pre-Phase-1 baseline).
- Review fixes (2026-10-11, same branch): real fuzzy event clustering (theme + ticker overlap + title Jaccard >= 0.3 + 72h window) replacing exact key grouping; `qualified_theme_count` and `news_top_ticker_share` wired into the classifier as downward-only constraints (catalyst breadth, news breadth, news-on-leader concentration); AI Infrastructure Enablers as an explicit classifier input (a deteriorating supporting sleeve blocks Broadly Confirming; it can never upgrade the read).
- Phase 1 test state: 95 tests total — 91 passing, including all 57 new Phase 1 tests. Four `test_news.py` failures are pre-existing date-window artifacts (hardcoded 2026-07-08 fixtures aged past the 21-day news window as of 2026-10-11); they fail on master too and are unrelated to Phase 1.
- Current project status: v1 dashboard and Phase 1 complete; adversarial review findings were fixed and live validation passed on Windows 2026-10-11. Phase 2 remains gated pending explicit approval.
