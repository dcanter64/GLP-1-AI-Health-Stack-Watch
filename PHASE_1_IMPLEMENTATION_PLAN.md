# Phase 1 Implementation Plan

## Goal

Upgrade the existing GLP-1 AI Health Stack Watch from a single broad thesis score into a clearer analytical structure that separates leader confirmation, sleeve confirmation, breadth, concentration, and unique news-event evidence.

Phase 1 will not produce allocation tiers, portfolio recommendations, opportunity scores, persistence classifications, or position-level decisions. Those are reserved for later approved phases.

## Current Baseline

- Existing app: Streamlit dashboard plus markdown/CSV/JSONL validation outputs.
- Existing core score: overall GLP-1 flywheel score and LLY AI-trade confirmation score.
- Latest documented live baseline: 2026-07-26 13:34 UTC.
- Latest documented state: Neutral, score 59.0, LLY AI trade score 66.8, market data quality High.
- Current tests documented: 38 passing.

## Phase 1 Scope

### 1. Configurable Health-Stack Sleeves

Add a configurable sleeve definition file, likely:

```text
config/health_stack_sleeves.yaml
```

The initial sleeves should be:

- Established GLP-1 Leaders
- Emerging GLP-1 Challengers
- Large-Pharma GLP-1 Optionality
- AI Drug-Discovery Platforms
- Gene Editing and Precision Medicine
- Health Data and Clinical AI
- Broad Biotech Risk Appetite

Implementation notes:

- Reuse current `TICKER_GROUPS` where practical.
- Keep ticker membership editable in configuration.
- Provide a loader that validates required fields and maps tickers to sleeves.
- Do not remove current ticker groups or market-data paths.

### 2. Sleeve-Level Market Structure

Create sleeve summaries from the existing performance table:

- Average returns by sleeve.
- Relative strength versus XLV and SPY.
- Percent of names above 50DMA.
- Percent of names above 200DMA.
- Percent outperforming XLV.
- Percent outperforming SPY.
- Best and worst names per sleeve.
- Sleeve status such as confirming, mixed, deteriorating, or insufficient data.

This should extend current reporting data rather than replace the existing basket views.

### 3. Leader Concentration Analysis

Measure whether positive evidence is broad or concentrated:

- Top-name contribution to positive market evidence.
- Top-three contribution.
- Strongest-sleeve contribution.
- LLY-specific contribution when LLY is configured.
- Number of confirming sleeves.
- Number of deteriorating sleeves.
- Percent tracked names outperforming XLV and SPY.
- Percent tracked names above 50DMA and 200DMA.

The output should explicitly say whether confirmation is broad, selective, or leader-dependent.

### 4. Confirmation-State Classification

Add an overall confirmation state:

- Broadly Confirming
- Selectively Confirming
- Leader-Dependent
- Fragmenting
- Early Repair
- Deteriorating
- Failing
- Insufficient Evidence

The classifier must consider multiple inputs, not only the current overall score:

- Overall flywheel score.
- Sleeve-level confirmation.
- Market breadth.
- Relative strength.
- Moving-average participation.
- Catalyst breadth.
- News concentration.
- Leadership concentration.
- Data quality.

### 5. Separate Leader and Stack Conclusions

Add two separate top-level assessments:

- Leader Assessment: whether the strongest established leader or leaders are confirming.
- Stack Assessment: whether the broader ecosystem is confirming.

These may disagree. The report should be able to say that LLY is confirming while the broad stack remains selective or fragmented.

### 6. News Event Clustering

Add event-level clustering to accepted stories:

- Raw story count.
- Accepted story count.
- Qualified story count.
- Unique event count.
- Independent source count.
- Material event count.
- Duplicate or syndicated coverage.
- Event or cluster identifier on accepted stories.

Multiple articles about one lawsuit, clinical result, regulatory action, or partnership should count as one underlying event with multiple sources.

### 7. Report Additions

Add a section near the top of the markdown report:

```text
## Health Stack Confirmation Structure
```

Include:

- Overall confirmation state.
- Leader assessment.
- Stack assessment.
- Leadership concentration.
- Strongest sleeve.
- Weakest sleeve.
- Number of confirming sleeves.
- Number of deteriorating sleeves.
- Unique material events.
- Main positive evidence.
- Main negative evidence.
- Main contradiction.

Keep all existing detailed report sections below this new structure.

## Suggested File Layout

Likely new files:

- `config/health_stack_sleeves.yaml`
- `glp1_watch/health_stack_sleeves.py`
- `glp1_watch/confirmation_state.py`
- `glp1_watch/leadership_concentration.py`
- `glp1_watch/news_event_clustering.py`

Likely modified files:

- `glp1_watch/news.py`
- `glp1_watch/pipeline.py`
- `glp1_watch/reporting.py`
- `glp1_watch/app.py`
- `README.md`
- `roadmap.md`
- `CHANGELOG.md`
- `SESSION_HANDOFF.md`

Exact filenames may change after implementation inspection, but Phase 1 should avoid creating placeholder modules for later phases.

## Testing Plan

Add focused tests for:

- Sleeve configuration loading.
- Ticker-to-sleeve mapping.
- Broad confirmation.
- Selective confirmation.
- Leader-dependent confirmation.
- Fragmentation.
- Early repair.
- Missing sleeve data.
- Leader-concentration calculations.
- Event deduplication.
- Multiple sources covering one event.
- Distinct events involving the same ticker.
- No-change behavior for existing report generation.

Run:

```bash
python -m pytest
python generate_snapshot.py
python review_snapshot_history.py
```

Live Yahoo/RSS validation should be done from a normal Windows shell when possible.

## Phase 1 Completion Requirements

Before Phase 1 is considered complete:

- All existing tests pass.
- New Phase 1 tests pass.
- A current report is generated.
- The new confirmation-state output is shown.
- README is updated.
- CHANGELOG is updated.
- SESSION_HANDOFF is updated.
- Limitations and Phase 2 recommendations are documented.

Then stop and wait for approval before beginning Phase 2.
