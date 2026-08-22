# Decision Layer Upgrade Specification

## Long-Term Goal

Evolve the GLP-1 AI Health Stack Watch from a descriptive thematic dashboard into a specialized GLP-1 and AI-Health Capital Allocation Decision Layer.

This must be implemented in deliberate phases. Each phase must be independently useful, tested, documented, and operational before beginning the next phase.

Do not remove or weaken the existing:

- Market-data collection
- Ticker baskets
- Relative-strength calculations
- Price-trend analysis
- News collection
- Relevance filtering
- Sentiment scoring
- Theme classification
- Data-quality auditing
- Existing report sections
- Existing command-line workflow

Extend the current architecture rather than replacing it.

## Core Problem

The current report combines many distinct investment conditions into one overall score and one broad stance. The upgraded system must eventually distinguish among:

- A strong individual leader
- An improving subgroup
- A broadly confirmed investment theme
- A leader-dependent theme
- A fragmented theme
- A failing theme

The system should ultimately answer:

- Does the broad GLP-1 and AI-health stack deserve capital?
- Which sleeve deserves capital?
- Which companies are confirmed leaders?
- Which areas should be avoided?
- Is exposure best implemented broadly or selectively?
- Should capital be increased, maintained, reduced, or withheld?
- How confident is the recommendation?
- What evidence would reverse it?

## Development Rules

At the start of each phase:

1. Inspect the current repository.
2. Review the output and documentation from the previous phase.
3. Confirm that the current project and tests run successfully.
4. Produce a concise implementation plan for that phase only.
5. Do not begin later-phase work unless explicitly instructed.

At the end of each phase:

1. Run all existing tests.
2. Add and run tests for the new functionality.
3. Run the complete project using current data.
4. Show the updated report or machine-readable output.
5. Update `README.md`.
6. Update `CHANGELOG.md`.
7. Update or create `SESSION_HANDOFF.md`.
8. Document limitations and recommended next steps.
9. Stop and wait for approval before beginning the next phase.

Do not create placeholder modules for future phases unless required by the current phase.

Do not leave pseudocode or unfinished production paths.

## Phase 1: Improve the Existing Analytical Structure

Status: planned. Begin with Phase 1 only.

Objective: make the current report more decision-ready without issuing allocation tiers or portfolio recommendations.

Phase 1 should separate the broad thesis into distinct analytical sleeves and clarify whether confirmation is broad, selective, concentrated, or deteriorating.

Required sleeves:

- Established GLP-1 Leaders
- Emerging GLP-1 Challengers
- Large-Pharma GLP-1 Optionality
- AI Drug-Discovery Platforms
- Gene Editing and Precision Medicine
- Health Data and Clinical AI
- Broad Biotech Risk Appetite

Ticker membership must be editable in configuration and not buried in decision logic. A likely file is:

```text
config/health_stack_sleeves.yaml
```

Confirmation states:

- Broadly Confirming
- Selectively Confirming
- Leader-Dependent
- Fragmenting
- Early Repair
- Deteriorating
- Failing
- Insufficient Evidence

The classification must consider overall score, sleeve-level performance, breadth, relative strength, moving-average participation, catalyst breadth, news concentration, leadership concentration, and data quality.

Leader concentration should measure:

- Percentage of positive contribution attributable to the top name
- Percentage attributable to the top three names
- Strongest sleeve contribution
- LLY-specific contribution when configured
- Number of confirming sleeves
- Number of deteriorating sleeves
- Percentage of tracked names outperforming XLV
- Percentage outperforming SPY
- Percentage above 50DMA
- Percentage above 200DMA

Add separate report conclusions:

- Leader Assessment
- Stack Assessment

Improve news event deduplication by tracking:

- Raw story count
- Accepted story count
- Qualified story count
- Unique event count
- Independent source count
- Material event count
- Duplicate or syndicated coverage
- Event or cluster identifier on accepted stories

Add a report section near the top:

```text
## Health Stack Confirmation Structure
```

Include:

- Overall confirmation state
- Leader assessment
- Stack assessment
- Leadership concentration
- Strongest sleeve
- Weakest sleeve
- Number of confirming sleeves
- Number of deteriorating sleeves
- Unique material events
- Main positive evidence
- Main negative evidence
- Main contradiction

Phase 1 tests:

- Sleeve configuration loading
- Ticker-to-sleeve mapping
- Broad confirmation
- Selective confirmation
- Leader-dependent confirmation
- Fragmentation
- Early repair
- Missing sleeve data
- Leader-concentration calculations
- Event deduplication
- Multiple sources covering one event
- Distinct events involving the same ticker
- No-change behavior

At Phase 1 completion, provide summary of changes, files created or modified, tests run and results, latest updated report, confirmation-state output, known limitations, and recommended Phase 2 work. Then stop.

## Phase 2: Add Sleeve-Level Opportunity Scoring

Status: gated. Begin only after Phase 1 has been reviewed and approved.

Objective: create separate analytical scores for each sleeve so the project no longer relies on one flywheel score to represent all areas of the health stack.

Preserve the existing overall score, but rename or clarify it as:

```text
Health Stack Flywheel Score
```

Do not use it as the sole decision input.

Add a Structural Thesis Score from 0 to 100 measuring whether the long-term GLP-1 and AI-health flywheel is becoming economically stronger.

Possible inputs:

- GLP-1 demand evidence
- Commercial adoption
- Pipeline progress
- Regulatory progress
- Reimbursement developments
- Partnership activity
- Licensing activity
- M&A activity
- AI-health capital formation
- Evidence of AI improving research productivity
- Evidence of AI reducing development time or cost
- Data quality

Add a Market Confirmation Score from 0 to 100 measuring whether the market is rewarding the thesis.

Possible inputs:

- Absolute returns
- Relative strength versus XLV
- Relative strength versus SPY
- Relative strength versus QQQ
- 50DMA status
- 200DMA status
- Breadth
- Drawdown
- Persistence
- Leadership concentration
- Volatility
- Rate of change

Add a Catalyst Score from 0 to 100.

Separate components:

- Commercial catalysts
- Clinical catalysts
- Regulatory catalysts
- Partnership and licensing catalysts
- M&A catalysts
- Policy and reimbursement catalysts

Do not let raw article count dominate the score. Use unique material events.

Add an Expectations Risk Score from 0 to 100, where higher means greater risk that expectations, valuation, or positioning have become difficult to satisfy.

Potential inputs:

- Price acceleration
- Distance above moving averages
- Drawdown from high
- Valuation data, when available
- Earnings-revision deceleration, when available
- Strong price action with weakening catalysts
- Narrow leadership
- Excessive dependence on one company
- Positive-news saturation

If valuation or revisions are unavailable, report reduced confidence rather than inventing them.

Add Sleeve Opportunity Scores from 0 to 100.

Suggested inputs:

- Absolute performance
- Relative performance
- Breadth
- Trend
- Structural Thesis Score
- Catalyst Score
- Expectations Risk Score
- Persistence
- Data quality
- Leadership concentration
- Internal dispersion

Suggested interpretation:

- 80-100: Strong opportunity
- 65-79: Attractive
- 55-64: Selectively attractive
- 45-54: Neutral
- 35-44: Weak
- 20-34: Avoid broad exposure
- 0-19: Broken or highly speculative

Also classify each sleeve as:

- Strong and improving
- Strong but decelerating
- Neutral and improving
- Neutral and deteriorating
- Weak but improving
- Weak and deteriorating

Add report section:

```text
## Health Stack Opportunity Ranking
```

Table:

```text
| Rank | Sleeve | Opportunity Score | Structural Score | Market Confirmation | Catalyst Score | Expectations Risk | Trend |
```

Add a decision-neutral interpretation explaining where evidence is strongest and weakest. Do not issue allocation tiers or direct portfolio actions.

Phase 2 tests:

- Structural Thesis Score
- Market Confirmation Score
- Catalyst Score
- Expectations Risk Score
- Sleeve Opportunity Score
- Missing valuation data
- Missing catalyst data
- Strong leader with weak stack
- Strong stack with weak leader
- Recognition-gap condition
- Expectations-risk condition
- High dispersion
- Low data quality
- Score bounds
- Configuration weight loading

At Phase 2 completion, provide summary of changes, files created or modified, tests run and results, latest opportunity ranking, score methodology, remaining data limitations, and recommended Phase 3 work. Then stop.

## Phase 3: Add Persistence, History, and Recommendation Readiness

Status: gated. Begin only after Phase 2 has been reviewed and approved.

Objective: determine whether signals are persistent enough to justify action.

Add a history store using the project storage convention.

Track by report date:

- Health Stack Flywheel Score
- Structural Thesis Score
- Market Confirmation Score
- Catalyst Score
- Expectations Risk Score
- Sleeve Opportunity Scores
- Confirmation-state classification
- Breadth
- Leadership concentration
- Trend classification
- Data quality
- Unique material-event count

A CSV or SQLite implementation is acceptable. Possible file:

```text
data/health_stack_history.csv
```

Persistence metrics for each sleeve:

- Current score
- Previous score
- Four-report trend
- Eight-report trend
- Consecutive improving reports
- Consecutive deteriorating reports
- Consecutive reports above threshold
- Consecutive reports below threshold
- Date current condition began
- Maximum severity reached
- Whether improvement is accelerating
- Whether deterioration is accelerating

Recommendation readiness classifications:

- Insufficient Evidence
- Early Signal
- Developing
- Confirmed
- Persistent
- Exhausted
- Repairing

Examples:

- One improving report: Early Signal
- Two improving reports: Developing
- Three or more with breadth confirmation: Confirmed
- Persistent strong readings: Persistent
- Strong score with worsening catalysts and narrowing breadth: Exhausted
- Weak score with two improving reports: Repairing

Do not make readiness purely mechanical. Conflicting evidence must be reported.

Add report section:

```text
## Persistence and Decision Readiness
```

Table:

```text
| Sleeve | Current Score | Four-Report Trend | Persistence | Readiness | Second Derivative |
```

Add:

```text
## What Changed Since the Previous Report
```

Include score changes, trend changes, new leaders, lost leaders, new deterioration, early repair, catalyst changes, breadth changes, leadership concentration changes, and data-quality changes.

Phase 3 tests:

- History loading
- First-run behavior
- Consecutive improvement
- Consecutive deterioration
- Persistent leadership
- Early repair
- Exhaustion
- Missing prior history
- Duplicate report dates
- Out-of-order dates
- Conflicting signals
- Second-derivative classification
- No-change behavior

At Phase 3 completion, provide summary of changes, files created or modified, tests run and results, latest persistence table, current recommendation-readiness classifications, remaining limitations, and recommended Phase 4 work. Then stop.

## Phase 4: Add the Capital Allocation Decision Layer

Status: gated. Begin only after Phase 3 has been reviewed and approved.

Objective: convert analytical outputs into explicit, probabilistic allocation recommendations.

Recommendation categories:

- STRONG INCREASE
- INCREASE
- ACCUMULATE GRADUALLY
- HOLD
- HOLD / STOP ADDING
- REDUCE
- STRONG REDUCE
- AVOID NEW CAPITAL
- WATCH FOR RE-ENTRY
- CATALYST-DEPENDENT WATCH

Allocation tiers:

- Tier 0: Avoid
- Tier 1: Exploratory allocation
- Tier 2: Normal allocation
- Tier 3: Overweight
- Tier 4: Maximum-conviction overweight

For every sleeve report:

- Previous tier
- Recommended tier
- Change
- Recommendation
- Implementation speed
- Confidence
- Urgency
- Tactical view
- Strategic view

Normal changes should be limited to one tier per report. Allow a two-tier move only during a severe thesis break or major confirmed catalyst.

Create two headline decisions:

- Leader Decision
- Stack Decision

These may disagree.

Every report must classify preferred implementation as:

- Broad
- Selective
- Leader-Only
- Exploratory
- No New Capital

Confidence score:

- 0-39: Low
- 40-59: Moderate
- 60-79: High
- 80-100: Very High

Confidence inputs should include signal persistence, agreement between price and fundamentals, breadth, data quality, catalyst diversity, leadership concentration, time-horizon agreement, degree of conflict, and historical stability.

Urgency:

- Low
- Moderate
- High
- Immediate

Add immediate, tactical, intermediate, and strategic views for each sleeve.

Every recommendation must include measurable:

- Upgrade conditions
- Downgrade conditions
- Invalidation conditions

Avoid vague language such as "monitor developments."

Required top-of-report structure:

```text
# GLP-1 AI Health Decision Layer

## 1. Investment Committee Decision
## 2. Allocation Decisions
## 3. Opportunity Ranking
## 4. Leader vs Stack Decision
## 5. Decision Cards
## 6. What Changed Since the Previous Report
## 7. Decision Risks
## 8. Existing Report Sections
```

Guardrails:

- Limit normal changes to one tier per report.
- Require persistence before STRONG INCREASE or STRONG REDUCE.
- Require breadth confirmation before recommending broad exposure.
- Require two improving reports before WATCH FOR RE-ENTRY becomes ACCUMULATE.
- Do not reverse a recommendation because of one strong or weak week.
- Prefer gradual implementation when the strategic thesis remains intact.
- Allow no allocation change when evidence is genuinely inconclusive.
- Do not treat every company in a weak sleeve identically.
- Do not automatically increase the broad stack because LLY is strong.
- Do not automatically reduce the leader because speculative health names are weak.

Phase 4 tests:

- Recommendation thresholds
- Allocation tiers
- Tier-change limits
- Strong leader with weak stack
- Weak leader with improving stack
- Broad confirmation
- Selective confirmation
- Leader-only exposure
- Catalyst-dependent watch
- Recognition gap
- Expectations risk
- Early repair
- Confidence scoring
- Urgency scoring
- Tactical versus strategic disagreement
- Upgrade conditions
- Downgrade conditions
- No-change behavior
- Severe regulatory-risk override

At Phase 4 completion, provide summary of changes, files created or modified, tests run and results, latest GLP-1 AI Health Decision Layer output, allocation decisions, remaining limitations, and recommended Phase 5 work. Then stop.

## Phase 5: Add Position-Level Decisions and Accountability

Status: gated. Begin only after Phase 4 has been reviewed and approved.

Objective: add ticker-level recommendations and evaluate whether prior recommendations were useful.

For every configured portfolio or watch-list ticker report:

- Sleeve
- Current price trend
- Relative strength versus SPY
- Relative strength versus XLV
- Relative strength versus sleeve
- 50DMA status
- 200DMA status
- Drawdown from high
- Market Confirmation Score
- Catalyst Score
- Expectations Risk
- Position status
- Recommendation
- Tier
- Confidence
- Urgency
- Reason
- Upgrade conditions
- Downgrade conditions
- Invalidation conditions

Suggested position statuses:

- Core leader
- Tactical leader
- Emerging leader
- Early accumulation
- Catalyst-dependent
- Recognition gap
- Expectations-risk leader
- Thesis intact / price broken
- Price intact / thesis weakening
- Recovery candidate
- Rotation source
- Avoid new capital
- Exit candidate

Do not treat all companies in a sleeve identically.

Decision journal fields:

- Date
- Sleeve or ticker
- Recommendation
- Recommended tier
- Confidence
- Urgency
- Evidence
- Upgrade conditions
- Downgrade conditions
- Subsequent one-month performance
- Subsequent three-month performance
- Subsequent six-month performance when available

Do not fabricate forward results.

Historical accountability metrics, when enough history exists:

- Average return after increase recommendations
- Average return after reduce recommendations
- False-positive rate
- False-negative rate
- Maximum adverse excursion
- Maximum favorable excursion
- Average lead time
- Recommendation turnover
- Performance by confidence band
- Performance by recommendation type

Basic backtesting, where practical:

- Static equal-weight stack
- Static sleeve allocation
- Tier-based decision framework
- Selective leader strategy
- Broad-stack strategy
- Catalyst-confirmed strategy
- Persistence-confirmed re-entry
- Avoid-new-capital rules

Compare against:

- SPY
- QQQ
- XLV
- XBI or the project's existing biotech benchmark
- Static configured portfolio when weights are available

Report total return, annualized return, volatility, maximum drawdown, turnover, number of allocation changes, win rate, and excess return.

Be explicit about survivorship bias, incomplete historical fundamentals, news-history limitations, and unavailable valuation data.

At Phase 5 completion, provide summary of changes, files created or modified, tests run and results, latest position-level decisions, decision-journal status, available historical accountability results, backtest results if reliable, remaining limitations, and recommended future improvement. Then stop.

## Current Interpretation Target

Do not hard-code this conclusion. After the full Decision Layer is complete, the current data should be capable of producing an interpretation approximately like:

```text
The GLP-1 and AI-health stack is selectively confirming rather than broadly neutral. Established GLP-1 leadership and selected AI drug-discovery platforms show meaningful market confirmation, but weak pipeline, partnership, M&A, and broad participation evidence do not support a broad health-stack overweight.

Maintain a normal allocation to the broad stack. Favor established GLP-1 leaders and selected AI drug-discovery platforms. Avoid indiscriminate exposure to emerging challengers and weak gene-editing names until catalyst breadth and market participation improve.
```

Possible illustrative output:

- Established GLP-1 Leaders: HOLD or ACCUMULATE GRADUALLY
- Emerging GLP-1 Challengers: CATALYST-DEPENDENT WATCH
- Large-Pharma Optionality: HOLD
- AI Drug Discovery Platforms: ACCUMULATE SELECTIVELY
- Gene Editing and Precision Medicine: AVOID BROAD NEW CAPITAL
- Health Data and Clinical AI: HOLD pending stronger confirmation
- Broad Health Stack: HOLD at normal allocation
- Preferred exposure: Selective
- Confidence: Moderate
- Urgency: Low to Moderate

The implemented rules, not this example, must produce the final recommendation.

## Possible Architecture

Possible modules, adjusted to fit the existing project:

- `health_stack_sleeves.py`
- `confirmation_state.py`
- `leadership_concentration.py`
- `news_event_clustering.py`
- `structural_thesis_score.py`
- `market_confirmation_score.py`
- `catalyst_score.py`
- `expectations_risk.py`
- `opportunity_score.py`
- `persistence_engine.py`
- `allocation_tiers.py`
- `health_decision_engine.py`
- `decision_history.py`
- `decision_report.py`

Possible configuration:

- `config/health_stack_sleeves.yaml`
- `config/decision_weights.yaml`
- `config/decision_thresholds.yaml`

Possible persistent data:

- `data/health_stack_history.csv`
- `data/health_decision_journal.csv`

These names are suggestions only. Follow the repository's current conventions and avoid unnecessary architectural duplication.
