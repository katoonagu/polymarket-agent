# 09 - BTC 15m Chainlink Directional Ladder Spec

## Purpose

This spec defines the first planned market-specific strategy module for the
current Polymarket operator stack: a paper-first BTC 15-minute directional
ladder for recurring Up/Down markets whose resolution source is the Chainlink
BTC/USD stream.

This spec now covers both the target design and the first paper/research
runtime on the current branch. The current implementation adds bounded recorder,
replay, paper-run, liquidity-sample, campaign, and report commands under
`pm strategy btc15m`, and now also adds a bounded current-window terminal
session. It still does not add live automation, a daemon, or a scheduler; live
execution is available only inside the attached terminal surface and remains
explicitly gated behind operator confirms.

## Current Phase

The broader strategy track name is:

- `btc_15m_chainlink_ladder`

The first runtime implementation name on the current branch is:

- `btc_15m_chainlink_directional_ladder_v1`

Current branch status:

- bounded recorder, replay, paper-run, liquidity-sample, campaign, and report
  commands now exist under `pm strategy btc15m`
- the runtime remains a separate research surface and does not emit generic
  reviewable strategy intents yet
- the current target is forward recording plus replay, bounded campaign
  collection, and paper evaluation
- public Binance REST overlays are now part of the research path for
  top-of-book, depth, and short-horizon realized-volatility context
- guarded live automation is still explicitly deferred, but the current branch
  now also includes one bounded BTC15m current-window terminal session with a
  paper-first default and explicitly gated live execution
- execution remains the only module allowed to place or cancel orders

This is the first planned specialization beyond the current generic
`recurring_crypto_interval_observe` track.

Current research commands:

- `pm strategy btc15m record start [--seconds <n>]`
- `pm strategy btc15m record window --slug <market_slug>`
- `pm strategy btc15m replay --from <iso> --to <iso>`
- `pm strategy btc15m paper-run --limit <n>`
- `pm strategy btc15m paper-run --slug <market_slug> [--mode paper|live]`
- `pm strategy btc15m liquidity sample [--seconds <n>]`
- `pm strategy btc15m campaign next-window [--slug <market_slug>] [--mode paper|live]`
- `pm strategy btc15m campaign run --hours <n> [--slug <market_slug>] [--mode paper|live]`
- `pm strategy btc15m campaign report`
- `pm strategy btc15m terminal --follow-current [--observe-only] [--mode paper|live] [--confirm]`
- `pm strategy btc15m terminal --current [--observe-only] [--mode paper|live] [--confirm]`
- `pm strategy btc15m terminal --wait-next [--mode paper|live] [--confirm]`
- `pm strategy btc15m terminal replay --session-id <id>`
- `pm strategy btc15m terminal report [--session-id <id>]`
- `pm strategy btc15m report`

Current workflow notes:

- `paper` is the default mode and uses live public market plus oracle inputs
  with simulated fills and PnL only
- live data stays on in both `paper` and `live`; the mode switch changes
  execution behavior only
- `live` remains reserved on the recorder, replay, campaign, dashboard, and
  paper-run surfaces; bounded live execution now exists only inside
  `pm strategy btc15m terminal --follow-current --mode live --confirm`
- `paper-run --slug` is the direct explicit-market paper testing path when
  recurring discovery is imperfect
- `campaign run --slug` targets exactly one explicit window and then stops
- `terminal --follow-current` is the canonical BTC15m operator session and
  follows the active current market immediately; `--current` remains a
  compatibility alias
- the terminal now auto-rolls across BTC15m slugs while the operator stays
  attached and writes one tear sheet per completed window plus one session log
- the terminal now persists a display-truth layer separate from strategy truth;
  displayed price-to-beat, displayed BTC, displayed Up/Down prices, countdown,
  and source metadata are distinct from Chainlink boundaries, start proxies,
  direction lock, and ladder state
- the primary operator view is page-parity-first: price to beat, current live
  BTC price, Up price, Down price, countdown, midpoint/spread, and visible
  liquidity are shown before Binance diagnostics
- page parity is API-first with lightweight public current-page fallback only
  for missing visible fields; fallback failure is non-fatal and explainable
- displayed Up/Down prices follow public page-style emulation rules when exact
  visible page prices are unavailable: use midpoint when spread is `<= 0.10`,
  otherwise use latest public last-trade price; if neither is safe, degrade to
  persisted display values or explicit empty fields with notes
- displayed price-to-beat must never reuse `start_price_proxy_v1`; it comes
  only from exact page extraction or market-question/title parsing tied to the
  active slug
- late attach on `terminal --follow-current` now falls back into `OBSERVE_ONLY`
  instead of hard-stopping when the start boundary cannot be recovered, then
  continues forward into the next slug
- `terminal --follow-current --observe-only` keeps the current session attached
  without arming the ladder
- `terminal --wait-next` watches the current window, begins pre-start capture
  before the next BTC15m bucket opens, arms that next window, and exits after a
  final tear sheet
- `terminal --json` is snapshot-only and exits immediately
- ladder prices render as `30¢ / 20¢ / 10¢` in human terminal views while JSON
  stays numeric as `0.30 / 0.20 / 0.10`
- `terminal --mode live --confirm` is the only BTC15m live execution surface on
  the current branch and still requires inline per-rung and cancellation
  confirms inside the attached terminal
- `terminal replay --session-id` replays persisted terminal snapshots only and
  does not call live market, oracle, or execution endpoints
- `terminal report --session-id` returns one persisted tear sheet while bare
  `terminal report` remains the aggregate session-history view

## Strategy Overview and Design Goals

The strategy is a directional ladder for one recurring BTC 15-minute market
window at a time.

V1 design goals:

- use deterministic recurring-market discovery
- anchor direction to a start-of-window Chainlink price proxy
- require confirmation from both Chainlink and Binance before choosing a side
- keep the ladder simple, fixed, and auditable
- hold to expiry in v1
- record enough oracle, market, and microstructure context to support replay,
  paper evaluation, and later guarded-live review
- enrich each recorded window with bounded Binance liquidity and realized-vol
  overlays
- make thin-liquidity and manipulation-style skips deterministic and explainable

V1 design limits:

- no side flipping
- no take-profit
- no stop-loss
- no background automation
- no assumption that RTDS Chainlink is already settlement-equivalent

## Market Type and Recurring Identification

The target market class is:

- recurring BTC 15-minute Up/Down markets on Polymarket
- markets whose resolution source is described in market metadata as Chainlink
  BTC/USD or equivalent Chainlink BTC/USD oracle wording

Recurring discovery should reuse the existing deterministic Gamma-based
resolver:

- `query="btc"`
- `interval="15m"`
- existing active/open/match-score/recency ranking
- existing outcome-to-token alignment from normalized market outputs

Each future strategy window should resolve a normalized market identity with at
least:

- `window_id`
- `condition_id`
- `market_slug`
- `event_slug`
- `question`
- `token_ids`
- `outcomes`
- `window_open_time`
- `window_start_at` when discoverable
- `window_end_at` when discoverable

`condition_id` is the primary input for deterministic per-window identity.

## Resolution Assumptions and Boundary Recording Rules

### Provisional resolution model

The provisional operational assumption for this track is:

- the market resolves by comparing a beginning-of-window BTC/USD reference price
  with an end-of-window BTC/USD reference price
- `UP` wins when the end value is greater than the beginning value
- `DOWN` wins when the end value is less than the beginning value

This assumption must be validated empirically against real BTC 15-minute
Polymarket recurring markets before any guarded-live promotion.

### Required Chainlink boundary observations

For every candidate market window, the future recorder must capture four
boundary observations from the Chainlink RTDS stream:

- last accepted Chainlink tick at or before the scheduled start
- first accepted Chainlink tick at or after the scheduled start
- last accepted Chainlink tick at or before the scheduled end
- first accepted Chainlink tick at or after the scheduled end

These observations must be stored even when the window is later skipped.

### Operational boundary proxies for v1

The v1 operational start anchor is:

- `start_price_proxy_v1`
- defined as the first accepted Chainlink tick at or after the scheduled start

The v1 replay and reconciliation end anchor is:

- `end_price_proxy_v1`
- defined as the first accepted Chainlink tick at or after the scheduled end

Rules:

- pre-start and pre-end observations are still persisted for audit and replay
  even when the post-boundary observation is missing
- if the required post-start Chainlink tick does not arrive within the bounded
  post-start grace window, the window is marked partial and evaluation skips
- if the required post-end Chainlink tick does not arrive within the bounded
  post-end grace window, the window is marked partial and replay or final
  evaluation remains pending or skipped
- stale post-boundary ticks beyond the configured grace window are treated as
  missing for the operational proxy
- `end_price_proxy_v1` is required for replay, post-window evaluation, and
  reconciliation, not for minute-5 side selection

### Persisted timing controls

The current runtime persists explicit timing controls with each canonical
boundary decision and each recorded window:

- `pre_start_capture_window_seconds = 60`
- `post_start_grace_window_seconds = 60`
- `pre_end_capture_window_seconds = 60`
- `post_end_grace_window_seconds = 60`
- `direction_lock_offset_seconds = 300`
- `entry_window_start_offset_seconds = 300`
- `entry_window_end_offset_seconds = 600`
- `cancel_open_entries_offset_seconds = 600`

### Planned boundary persistence

The current runtime persists raw boundary observations as append-only records
under:

- `.pm/state/btc-15m-chainlink-boundary-observations.jsonl`

Each raw observation should include at least:

- `window_id`
- `condition_id`
- `market_slug`
- `boundary_kind`
- `captured_at`
- `source_timestamp`
- `source_value`
- `source` with `chainlink_rtds`
- `session_id`
- `accepted`
- `selected`
- `selection_status`
- `notes`

The current runtime persists canonical boundary decisions under:

- `.pm/state/btc-15m-chainlink-boundary-decisions.json`

Each canonical decision should summarize:

- selected pre-start and post-start ticks
- selected pre-end and post-end ticks
- `start_price_proxy_v1`
- `end_price_proxy_v1`
- persisted timing controls
- selection rationale
- ambiguity or fallback notes

### Unresolved empirical assumptions

The following remain unresolved and must be validated empirically:

- exact inclusion rule around the scheduled start timestamp
- exact inclusion rule around the scheduled end timestamp
- acceptable source timestamp granularity
- acceptable clock skew and capture tolerance
- whether RTDS Chainlink is a sufficient proxy for final settlement behavior
- whether Polymarket applies rounding, truncation, or other transformations
- exact tie behavior when start and end values are equal

## Data Sources

The planned strategy depends on these existing or planned inputs:

- existing Polymarket recurring market resolver
- existing public CLOB reads for best bid, best ask, midpoint, spread, and
  lightweight book context
- existing RTDS Chainlink BTC/USD stream
- existing RTDS Binance BTC price stream as a second directional confirmation
  feed
- existing public Binance REST `bookTicker`, `depth`, and closed `1m` kline
  reads for liquidity and short-horizon realized-volatility overlays
- optional future Binance recent trades, aggregate trades, and deeper volume
  integration as later enhancements only

Rules:

- recurring market identification remains Gamma-search-based and deterministic
- Chainlink is the start-price anchor in v1
- Binance is used for directional confirmation in v1, not as the primary start
  anchor
- Chainlink remains the only canonical start and end boundary source in the
  current runtime; Binance boundary observations are contextual only
- current generic `pm stream recurring` is not the future full recorder
  contract, because the strategy needs separate Chainlink and Binance capture,
  boundary-state persistence, and per-window microstructure recording
- Binance REST overlays are part of the BTC15m research path, but they do not
  change the generic `pm stream` contract and they do not imply a broader
  exchange-integration surface

## Strategy Mechanics

### Observation timeline

The future runtime should observe each market window from the start of the
window. The decision and ladder timeline is:

- minute 0 to minute 5: observe only
- minute 5: lock one direction or skip
- minute 5 inclusive to minute 10 exclusive: place and maintain the ladder in
  paper mode
- minute 10 onward: no new ladder placement
- expiry: hold any filled position to resolution

### Direction lock at minute 5

Direction is chosen once, at minute 5, and never changed afterward in v1.

Definitions at the minute-5 decision point:

- `chainlink_decision_price` = latest accepted Chainlink BTC/USD value
- `binance_decision_price` = latest accepted Binance BTC price value
- `start_price_proxy_v1` = first accepted Chainlink tick at or after the
  scheduled start

Direction rule:

- choose `UP` only if both `chainlink_decision_price` and
  `binance_decision_price` are above `start_price_proxy_v1`
- choose `DOWN` only if both are below `start_price_proxy_v1`
- otherwise `SKIP`

Equality, mixed direction, or missing decision prices all resolve to `SKIP` in
v1.

### Ladder placement window

Only one direction may be active for a market window. Once selected:

- the ladder may be placed only between minute 5 inclusive and minute 10
  exclusive
- no ladder orders are created before minute 5
- no new ladder orders are created at or after minute 10

### Ladder shape

V1 uses a fixed three-rung ladder of literal outcome-token bid levels:

- `0.30`
- `0.20`
- `0.10`

The ladder is buy-only on the matching outcome token:

- buy `UP` when the locked direction is `UP`
- buy `DOWN` when the locked direction is `DOWN`

No equivalent synthetic short expression is used in v1.

Unfilled rungs expire from the paper model after minute 10. Filled positions
are held to expiry.

### V1 bankroll and rung sizing

Bankroll context for the initial paper strategy is:

- `1000 USDC`

Recommended v1 paper per-market risk budget is:

- `50 USDC`

Starting paper rung allocation is fixed at:

- `20 USDC` at `0.30`
- `15 USDC` at `0.20`
- `15 USDC` at `0.10`

This split is a starting default only and should remain a review item after
replay and paper evaluation.

### Exit behavior and future analytics

V1 exit behavior is hold-to-expiry only:

- no take-profit
- no stop-loss
- no hedge
- no side flip
- no early close logic

Even though v1 holds to expiry, the recorder and replay layer must capture:

- MFE
- MAE
- max favorable price path after first fill

These metrics are required so future take-profit work can be evaluated without
redefining the strategy history format.

## Risk Controls

The future implementation must enforce these v1 controls:

- one market at a time
- per-market paper risk budget of `50 USDC` in a `1000 USDC` bankroll context
- stale-data guards for Chainlink ticks
- stale-data guards for Binance ticks
- stale-data guards for book context
- spread guard from public CLOB context
- visible-liquidity guard around the first `0.30` rung
- Binance and Chainlink directional-agreement guard at minute 5
- divergence guard between Polymarket pricing and underlying BTC movement
- skip on incomplete boundary capture
- skip on unresolved recurring market mapping
- skip on inactive or closed market
- skip on stale oracle data
- skip on stale book data
- skip on excessive spread
- skip on insufficient visible liquidity
- skip on mixed Chainlink and Binance direction at minute 5

Current paper-runtime defaults:

- minute-5 Chainlink and Binance decision ticks must each be no older than `15`
  seconds
- decision-time Polymarket quote and liquidity context must be no older than `5`
  seconds
- skip `wide_polymarket_spread` when the target-token spread is missing or
  greater than `0.08`
- skip `thin_visible_liquidity` when cumulative visible ask size at or better
  than `0.30` is below the first-rung quantity `66.666666`
- skip `binance_chainlink_directional_disagreement` when Binance and Chainlink
  disagree relative to the start proxy or when their minute-5 divergence exceeds
  `15` bps
- skip `abnormal_polymarket_underlying_divergence` when the chosen target-token
  midpoint is above `0.70` while the absolute BTC move from the start proxy is
  below `8` bps

The spec intentionally does not define live capital allocation behavior yet.

## Recording Requirements

The current runtime persists one per-window strategy record under:

- `.pm/state/btc-15m-chainlink-windows.jsonl`

Each per-window record should include at least:

- market open time
- normalized window start and end times
- selected recurring market metadata
- `window_id`
- `condition_id`
- `market_slug`
- `token_ids`
- `outcomes`
- all accepted Chainlink ticks used by the strategy
- all accepted Binance ticks used by the strategy
- selected pre-start and post-start Chainlink ticks
- selected pre-end and post-end Chainlink ticks
- contextual pre-start and post-start Binance ticks when available
- contextual pre-end and post-end Binance ticks when available
- `start_price_proxy_v1`
- `end_price_proxy_v1` when available
- minute-5 direction decision
- decision timestamp
- ladder placement attempts
- book context around each rung
- Binance top-of-book and near-touch depth snapshots
- short-horizon realized-volatility proxies from closed Binance `1m` klines
- visible Polymarket ask liquidity around `0.30`, `0.20`, and `0.10`
- anti-manipulation and thin-liquidity flags
- simulated fills
- skip reasons
- final market resolution result
- replay outcome summary
- MFE, MAE, max favorable path metrics, and time to peak

The current runtime also persists:

- `.pm/state/btc-15m-chainlink-boundary-observations.jsonl`
- `.pm/state/btc-15m-chainlink-boundary-decisions.json`
- `.pm/state/btc-15m-chainlink-windows.jsonl`
- `.pm/state/btc-15m-chainlink-replays.json`
- `.pm/state/btc-15m-chainlink-paper-runs.json`
- `.pm/state/btc-15m-chainlink-liquidity-samples.jsonl`
- `.pm/state/btc-15m-chainlink-campaign-runs.json`
- `.pm/state/btc-15m-chainlink-dashboard-snapshots.jsonl`
- `.pm/state/btc-15m-chainlink-terminal-sessions.json`

The current branch now creates these research artifacts, but it still treats
them as paper/research state only.

## Testing and Promotion Plan

### Forward recorder

The first runtime implementation on the current branch supports bounded forward
recording and should still be used for an initial recorder run of:

- `2 days`

It should:

- resolve active BTC 15m recurring markets
- capture Chainlink and Binance ticks throughout the window
- capture the required pre/post boundary ticks
- capture minute-5 decision context
- capture minute 5 to minute 10 book context and ladder attempts
- capture Binance REST liquidity overlays on a bounded schedule plus mandatory
  strategy checkpoints
- avoid all live execution behavior

### Bounded campaign runner

The current runtime now also supports a bounded campaign path:

- `pm strategy btc15m campaign next-window`
- `pm strategy btc15m campaign run --hours <n>`
- `pm strategy btc15m campaign report`

Campaign rules:

- campaigns record exactly one BTC 15m recurring window at a time
- a new window is started only when enough time remains to capture through the
  end boundary plus a short post-end wait
- campaign runs stop cleanly instead of rolling into an unbounded loop
- each completed campaign window persists one paper evaluation with
  `source_kind="campaign"` so later standalone `paper-run` does not duplicate it

### Replay harness

The current runtime includes a replay harness over recorded windows. Replay
should
reconstruct:

- resolved market window identity
- `start_price_proxy_v1`
- minute-5 direction decision
- ladder placement and simulated fill outcomes
- hold-to-expiry paper result
- MFE, MAE, and favorable path metrics

### Paper evaluation

The current runtime keeps paper evaluation as a dedicated research surface
instead of emitting generic review intents yet. It still reuses the existing
public market and stream architecture and deliberately avoids any live
execution path.

Paper evaluation should answer:

- whether the boundary capture is reliable enough
- whether minute-5 direction locking is explainable
- whether fixed ladder levels are fillable often enough to study
- whether liquidity and anti-manipulation guards are skipping the right windows
- whether skip conditions are firing for the right reasons
- whether the strategy remains interpretable and operator-safe

### Criteria for guarded live consideration

Guarded live work should remain deferred until all of the following look
acceptable:

- stable 2-day boundary capture
- low ambiguity in start and end proxy selection
- replay consistency against recorded windows
- acceptable paper slippage and fill assumptions
- clear skip-reason explainability
- stable risk-guard behavior

## Current Repository Artifacts and Remaining Work

The current runtime now includes:

- a dedicated BTC15m research module implementing
  `btc_15m_chainlink_directional_ladder_v1`
- recorder state for per-window strategy records
- recorder state for raw and canonical Chainlink boundary observations
- replay state, paper-run state, liquidity-sample state, and campaign-run state
- paper-only evaluation outside the generic strategy review and dispatch path

Still deferred or incomplete:

- broader replay-fixture coverage from multi-day recorded windows
- replay-driven parameter tuning for ladder levels and sizing
- any handoff into generic review, dispatch, or live execution flows

This strategy track still does not require in v1:

- a daemon
- a background scheduler
- new secret-handling behavior
- direct live automation in the first implementation step

## Open Questions

The following assumptions remain explicitly unresolved:

- canonical boundary selection rule around the exact scheduled timestamps
- settlement-equivalence of RTDS Chainlink vs final market resolution
- whether Binance should eventually get its own start proxy instead of using the
  Chainlink anchor
- whether `0.30/0.20/0.10` should remain absolute price levels across all BTC
  15-minute windows
- whether rung allocation should remain `20/15/15` or be rebalanced after
  replay
- whether future take-profit should key off midpoint, best bid, or realized fill
  opportunity
- whether direct Chainlink or Binance depth and volume integration become
  mandatory before guarded live

## Non-Goals in This Phase

- no live order submission
- no generic reviewable strategy intents yet
- no daemon or background loop
- no scheduler
- no auto-trading
- no secret-handling changes
- no claim that guarded live behavior is ready
