# 09 - BTC 15m Chainlink Ladder Spec

## Purpose

This spec defines the first planned market-specific strategy track for the current
Polymarket operator stack: a paper-first BTC 15-minute Up/Down ladder that uses
Polymarket recurring-market discovery, public CLOB reads, and Chainlink BTC/USD
context from Polymarket RTDS.

The current step is docs-first only. It does not add runtime strategy code, a
daemon, a scheduler, new CLI commands, or live automation. Its job is to make
the future recorder, replay, paper-evaluation, and guarded-live phases decision
complete before implementation begins.

## Current Phase

This spec plans a future strategy named `btc_15m_chainlink_ladder`.

The current branch does not implement it yet. In this phase:

- the strategy exists only as a planned design
- the first goal is forward boundary recording plus replay and paper evaluation
- guarded live automation is explicitly deferred
- execution remains the only module that may ever place or cancel orders

This strategy is intended to become the first market-specific specialization
beyond the current generic `recurring_crypto_interval_observe` track.

## Market Scope and Recurring Identification

The target market class is:

- recurring BTC 15-minute Up/Down markets on Polymarket
- resolution source described by Polymarket market metadata as the Chainlink
  BTC/USD stream or equivalent Chainlink BTC/USD oracle wording

Recurring discovery should reuse the current deterministic Gamma-based resolver:

- query-driven discovery with `query="btc"`
- interval `15m`
- deterministic ranking across active, open, stronger query match, and recency
- explicit outcome and token alignment from normalized market outputs

Each future ladder instance should resolve one market window identity with at
least:

- `window_id`
- `condition_id`
- `market_slug`
- `event_slug`
- `question`
- `token_ids`
- `outcomes`
- `window_start_at` when discoverable
- `window_end_at` when discoverable

`window_id` should be deterministic and derived from the resolved market window,
preferably from `condition_id`, with market slug and planned boundary timestamps
as secondary inputs when needed.

## Resolution Assumptions

### Provisional market-resolution model

The provisional assumption for this track is:

- the market resolves by comparing a beginning-of-window BTC/USD reference price
  with an end-of-window BTC/USD reference price
- `UP` wins when the end price is greater than the beginning price
- `DOWN` wins when the end price is less than the beginning price

This model is intentionally provisional and must be validated empirically against
real Polymarket recurring BTC 15m markets and their final resolution behavior.

### Boundary observations

Future implementation must record both boundary phases:

- start boundary observations near the opening of the 15-minute window
- end boundary observations near the closing of the 15-minute window

The system should persist raw candidate observations and a separate canonical
boundary decision. The canonical decision must not overwrite or discard the raw
window of candidate observations.

### Planned boundary persistence

Future raw boundary observations should be append-only records under:

- `.pm/state/btc-15m-chainlink-boundary-observations.jsonl`

Each raw observation should include at least:

- `window_id`
- `condition_id`
- `market_slug`
- `boundary_kind` with `start` or `end`
- `captured_at`
- `source_timestamp`
- `source_value`
- `source` fixed to `chainlink_rtds`
- `session_id`
- `selected` boolean
- `selection_status`
- `notes` when useful for explainability

Future canonical boundary decisions should be persisted under:

- `.pm/state/btc-15m-chainlink-boundary-decisions.json`

Each canonical decision should summarize the selected start and end observations,
selection rationale, and any ambiguity or fallback conditions.

### What remains uncertain

The following must stay explicit open validation items:

- exact start-boundary inclusion rule
- exact end-boundary inclusion rule
- acceptable timestamp granularity and clock skew tolerance
- whether Chainlink RTDS is a sufficient proxy for final settlement behavior
- whether Polymarket uses a rounded, truncated, or otherwise transformed
  comparison value
- whether equal start and end values imply a special tie rule or a deterministic
  `DOWN`/`UP` convention

## Data Sources

The planned strategy depends on these sources:

- Polymarket recurring market discovery via the current Gamma-based recurring
  resolver
- Polymarket public CLOB data for midpoint, spread, best bid, best ask, and
  optional book-depth context
- Polymarket RTDS Chainlink BTC/USD stream as the v1 boundary and directional
  reference source
- optional future direct Chainlink Data Streams integration only as a later
  validation path, not as a v1 dependency

Rules:

- market identification remains Gamma-search-based and deterministic
- live entry evaluation uses public CLOB data only
- boundary capture must be sourced from Chainlink RTDS in the first evaluation
  phase
- any future direct Chainlink integration is additive validation, not a blocker
  for recorder or paper-eval v1

## Strategy Mechanics

### Core shape

This strategy is a one-side-per-market momentum ladder anchored to the recorded
start boundary price.

Definitions:

- `start_price` = canonical selected start boundary Chainlink BTC/USD value
- `current_price` = latest accepted Chainlink BTC/USD value during the window
- `displacement_pct` = `(current_price - start_price) / start_price * 100`

The direction rule is:

- positive displacement activates the `UP` ladder
- negative displacement activates the `DOWN` ladder
- zero or near-zero displacement activates neither ladder

Only one direction may be active for a given market window. Once one direction
is active, the strategy does not flip to the opposite side in v1.

### Entry ladder

The ladder is triggered by monotonic displacement thresholds measured from the
recorded `start_price`.

Each rung should be parameterized by:

- `trigger_displacement_pct`
- `notional_usdc`
- `max_slippage_pct`
- optional `min_confidence_flags`

Rungs must be strictly ordered from lowest trigger to highest trigger. A rung is
eligible only when:

- its trigger threshold has been crossed
- all prior enabled rungs for the same side have either been filled or skipped
- the market remains active and open
- entry cutoff has not passed
- spread, drift, and stale-data guards all pass

### Side and order expression

V1 standardizes on buying the explicit matching outcome token:

- buy `UP` when the positive ladder is active
- buy `DOWN` when the negative ladder is active

V1 should not mix equivalent synthetic expressions such as selling the opposite
side. The first paper-evaluation phase must keep the execution expression simple
and auditable.

### Monitoring window

The future runtime should monitor a market window from shortly after the selected
start boundary until an entry cutoff before the scheduled window end.

The spec should treat these as future parameters:

- initial guard delay after the selected start boundary
- continuous monitoring cadence or event-driven evaluation model
- hard entry cutoff before expiry

### Exit behavior

V1 is hold-to-expiry only:

- no take-profit
- no stop-loss
- no intra-window hedge
- no side flip
- no early close logic

Any future take-profit or early-exit extension must be a separate strategy
evolution, not hidden inside the initial ladder implementation.

## Risk Controls

The future implementation must include explicit guards for:

- max size per rung
- max total size per market window
- max concurrent BTC 15m markets
- spread guard
- drift guard between CLOB entry price and Chainlink reference
- stale-data guard for Chainlink RTDS updates
- stale-data guard for public CLOB observations
- skip on incomplete or ambiguous boundary capture
- skip on incomplete outcome or token mapping
- skip when recurring market resolution is no longer active or open

The spec should keep these as configurable policy parameters:

- `max_size_usdc_per_rung`
- `max_size_usdc_per_market`
- `max_concurrent_markets`
- `max_entry_spread_pct`
- `max_chainlink_clob_drift_pct`
- `max_chainlink_staleness_seconds`
- `max_clob_staleness_seconds`
- `entry_cutoff_seconds_before_expiry`

Exact numeric values remain provisional until replay and paper evaluation produce
evidence for tuning.

## Testing and Promotion Plan

### Forward recorder

The first implementation step after this spec should be a forward recorder that:

- resolves the active BTC 15m recurring market
- records candidate start and end Chainlink boundary observations
- records enough market metadata to replay a window later
- does not place orders

### Replay harness

The next step should be a replay harness that consumes:

- recorded boundary observations
- canonical boundary decisions
- recorded market metadata
- recorded CLOB context needed for entry simulation

Replay should reconstruct:

- which side would have become active
- which ladder rungs would have triggered
- which entries would have passed or failed guards
- hold-to-expiry PnL under paper assumptions

Future replay artifacts should be persisted under:

- `.pm/state/btc-15m-chainlink-replays.json`

### Paper evaluation

Paper evaluation should run through the existing strategy, risk, and execution
stack rather than inventing a parallel path.

The paper phase should prove:

- boundary capture is reliable
- recurring market resolution is reliable
- the trigger logic is explainable
- fills can be approximated with reasonable CLOB assumptions
- the ladder does not violate the strategy/risk/execution boundary

### Promotion criteria for guarded live mode

Guarded live mode should remain deferred until all of these are acceptable:

- stable start and end boundary capture quality
- consistent canonical boundary selection
- replay results match forward-recorded outcomes closely enough
- paper-eval slippage and drift assumptions are credible
- risk guards prevent pathological ladder accumulation
- operator review surfaces remain clear and explainable

## Planned Local State

The future strategy track should use these planned artifact names:

- strategy name: `btc_15m_chainlink_ladder`
- recorder artifact:
  `.pm/state/btc-15m-chainlink-boundary-observations.jsonl`
- canonical boundary artifact:
  `.pm/state/btc-15m-chainlink-boundary-decisions.json`
- replay artifact:
  `.pm/state/btc-15m-chainlink-replays.json`

These are planned identifiers only. The current branch does not create them yet.

## Planned Repository Changes

The future implementation will require:

- a strategy module for `btc_15m_chainlink_ladder`
- recorder state for raw and canonical Chainlink boundary observations
- replay state and replay-oriented test fixtures
- paper execution integration through the existing guarded strategy-dispatch and
  execution stack
- explicit operator-facing reporting for ladder decisions, skipped rungs, and
  hold-to-expiry paper outcomes

This strategy track does not require:

- a daemon
- a background scheduler in v1
- direct live automation in the first implementation step
- new secret-handling behavior

## Open Questions

The following parameters are intentionally unresolved and must be validated
before runtime implementation is considered complete:

- canonical boundary selection rule near the exact start and end timestamps
- acceptable timestamp tolerance and source-clock skew window
- exact rung thresholds
- rung sizing schedule
- maximum number of enabled rungs
- entry cutoff timing before expiry
- whether entry trigger checks should key off best ask, midpoint, or another
  market metric
- minimum observation quality needed before a rung can trigger
- when direct Chainlink validation becomes mandatory instead of optional
- whether any tie, rounding, or settlement-edge behavior requires special-case
  paper treatment

## Non-Goals in This Phase

- no runtime strategy code
- no daemon or background loop
- no auto-trading
- no new CLI commands
- no new secret-handling model
- no implicit claim that current RTDS Chainlink reads are already settlement
  equivalent
