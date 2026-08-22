# Session Handoff

## Current State

The project is a working Streamlit dashboard that writes market, news, report, validation, and history artifacts under `output/`.

The current documented baseline is:

- Date: 2026-07-26 13:34 UTC
- Stance: Neutral
- Health Stack Flywheel Score: 59.0
- LLY AI trade score: 66.8
- Ticker rows: 38
- Accepted stories: 77
- Qualified scoring stories: 24
- Market data quality: High
- RSS errors: 0
- Tests: 38 passing

## User Request

The user attached a major upgrade prompt. The long-term target is a GLP-1 and AI-Health Capital Allocation Decision Layer, implemented in deliberate phases.

The immediate instruction is to begin with planning and documentation only, then stop before implementing Phase 1 code.

The full Phase 1-5 instructions are preserved in `DECISION_LAYER_UPGRADE_SPEC.md`. Use that file as the durable source for later-phase requirements after Phase 1 is complete.

## Phase Gate

Next approved work should be Phase 1 only:

- Configurable investment sleeves.
- Sleeve-level confirmation structure.
- Leader concentration analysis.
- Confirmation-state classification.
- Separate leader and stack assessments.
- News event clustering.
- New report section: `Health Stack Confirmation Structure`.

Do not implement Phase 2, Phase 3, Phase 4, or Phase 5 unless explicitly approved after Phase 1 review.

## Important Guardrails

- Preserve existing market-data collection, ticker baskets, relative-strength calculations, price-trend analysis, news collection, relevance filtering, sentiment scoring, theme classification, data-quality auditing, report sections, and command-line workflow.
- Extend the current architecture instead of replacing it.
- Do not add allocation tiers or portfolio recommendations in Phase 1.
- Do not create placeholder modules for future phases.

## Recommended Next Action

Start Phase 1 by:

1. Inspecting the repository again.
2. Running `python -m pytest`.
3. Reviewing the latest report and validation audit.
4. Implementing only the Phase 1 functionality documented in `PHASE_1_IMPLEMENTATION_PLAN.md`.
