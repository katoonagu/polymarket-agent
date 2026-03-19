# 05 - Strategy, Review, and Guarded Dispatch Spec

## Purpose

This phase adds a deterministic strategy registry and orchestration layer on top of the existing public intelligence stack. The strategy layer consumes read-only market, wallet, and stream artifacts, produces candidate intents plus manual review decisions, and supports an explicit operator-driven handoff into execution through risk-gated dispatch.

It does not:

- auto-submit intents
- run as a daemon
- bypass execution policy checks
- let strategy place or cancel orders directly
- require a database

Execution remains the only module allowed to place or cancel orders.

## Current Scope

The current branch exposes:

```text
pm risk show [--json]
pm risk init-defaults [--json]
pm strategy list
pm strategy show --name <name>
pm strategy validate --name <name>
pm strategy evaluate --name <name> [--limit <n>]
pm strategy intents [--limit <n>]
pm strategy review --intent-id <id>
pm strategy approve --intent-id <id>
pm strategy reject --intent-id <id> --reason <text>
pm strategy dispatch --intent-id <id> [--paper] [--live --confirm]
pm strategy dispatch pending [--limit <n>] [--paper]
pm strategy executions [--limit <n>]
pm strategy execution get --execution-id <id>
pm strategy btc15m record start [--seconds <n>]
pm strategy btc15m record window --slug <market_slug>
pm strategy btc15m replay --from <iso> --to <iso>
pm strategy btc15m paper-run [--limit <n>]
pm strategy btc15m report
```

These commands operate on local gitignored state, existing public intelligence outputs, and the existing execution module. Strategy still does not post or cancel orders by itself; it may only hand off through explicit manual dispatch.

## Local State

Strategy and risk state live under `.pm/state/`:

- `strategies.json`
- `strategy-intents.json`
- `strategy-decisions.json`
- `risk-policies.json`
- `strategy-execution-links.json`
- `strategy-dispatch-results.json`
- `btc-15m-chainlink-boundary-observations.jsonl`
- `btc-15m-chainlink-boundary-decisions.json`
- `btc-15m-chainlink-windows.jsonl`
- `btc-15m-chainlink-replays.json`
- `btc-15m-chainlink-paper-runs.json`

Rules:

- files are versioned JSON documents
- writes are atomic
- append order is deterministic
- validation failures surface as explicit state errors
- past intents are never mutated in place
- current review status is derived from the latest decision record for an intent
- dispatch and execution-link audit history is append-only

## Seeded Strategy Registry

The registry is seeded and deterministic in v1. There are no create, edit, pause, or resume commands yet.

Current seeded strategies:

1. `wallet_shadow_copy`
2. `market_watch_reversion`
3. `recurring_crypto_interval_observe`

In v1, strategy names match strategy types exactly. Dispatch is intentionally wallet-first:

- `wallet_shadow_copy` is dispatch-enabled by default
- `market_watch_reversion` is reviewable but not dispatchable
- `recurring_crypto_interval_observe` is reviewable but not dispatchable

## Planned Market-Specific Strategy Tracks

The current seeded registry is still intentionally small and generic. The first
planned market-specific extension is documented separately in:

- `09-btc-15m-chainlink-ladder.md`

That strategy track uses the broader spec name `btc_15m_chainlink_ladder` and
the first runtime implementation name `btc_15m_chainlink_directional_ladder_v1`.
It is a paper-first specialization for recurring BTC 15-minute Up/Down markets
whose resolution source is the Chainlink BTC/USD stream.

Rules for that planned track:

- a separate research surface now exists under `pm strategy btc15m`
- it does not participate in the seeded generic strategy registry yet
- it does not replace the current generic
  `recurring_crypto_interval_observe` strategy
- it begins with boundary recording, replay, and paper evaluation
- it is designed around a one-time minute-5 direction lock
- it uses a fixed minute 5 to minute 10 three-rung ladder
- it holds filled positions to expiry in v1
- any future guarded live mode remains deferred behind separate validation
  criteria

## Strategy Inputs

### `wallet_shadow_copy`

Consumes persisted wallet shadow simulation output:

- `wallet-shadow-runs.json`

It evaluates upstream shadow candidates during strategy review. After manual `APPROVE`, it may be converted into an execution request only through explicit `pm strategy dispatch` plus risk policy.

### `market_watch_reversion`

Consumes watched-market state:

- `market-watchlist.json`
- `market-snapshots.json`

It compares the latest saved baseline snapshot to a fresh current snapshot built from public Gamma, CLOB, and Data reads.

### `recurring_crypto_interval_observe`

Consumes recurring market resolution and persisted stream context:

- recurring Gamma resolution
- `stream-events.jsonl`

It compares recurring market direction with persisted crypto price direction.

## Candidate Intent Contract

Strategy evaluation persists normalized candidate intents with at least:

- `intent_id`
- `strategy_name`
- `strategy_type`
- `source_kind`
- `market_slug`
- `condition_id`
- `token_id`
- `side`
- `outcome`
- `decision`
- `reason_blocks`
- `created_at`
- `source_refs`

`source_refs` point back to the upstream wallet, market, or stream artifacts used to derive the intent.

## Decision States and Review

The current phase uses:

- `OBSERVE`
- `WAIT`
- `APPROVE`
- `REJECT`

Rules:

- `evaluate` may emit only `OBSERVE`, `WAIT`, or `REJECT`
- `APPROVE` is manual only
- `approve` and `reject` append local review records only
- review alone never forwards anything to execution
- dispatch is a separate explicit operator step

## Risk Policy

The current phase adds a small local `pm risk` surface:

- `pm risk show`
- `pm risk init-defaults`

`risk-policies.json` stores one default policy and fully materialized per-strategy policies.

Seeded defaults:

- `wallet_shadow_copy`: `dispatch_enabled=true`
- `market_watch_reversion`: `dispatch_enabled=false`
- `recurring_crypto_interval_observe`: `dispatch_enabled=false`
- `max_drift_pct=5`
- `max_spread_pct=5`
- `max_size_usdc_per_order=25`
- `max_exposure_usdc_per_market=100`
- `max_exposure_usdc_per_strategy=250`
- `require_market_open=true`
- `require_balance_ready=true`
- `require_allowance_ready=true`

`pm risk show` returns built-in defaults with `persisted=false` when the file does not exist yet. `pm risk init-defaults` is idempotent and creates the file only when missing.

## Dispatch Bridge

Manual dispatch is the only supported bridge from strategy into execution.

Supported commands:

- `pm strategy dispatch --intent-id <id> [--paper] [--live --confirm]`
- `pm strategy dispatch pending [--limit <n>] [--paper]`
- `pm strategy executions [--limit <n>]`
- `pm strategy execution get --execution-id <id>`

Rules:

- only intents whose latest manual decision is `APPROVE` may dispatch
- only strategies with `dispatch_enabled=true` may dispatch
- paper mode is the default
- live dispatch requires `--live --confirm`
- `dispatch pending` is paper-only in this phase
- once an intent has a non-skip dispatch result, later dispatch attempts must return `SKIP already_dispatched`

In v1, only `wallet_shadow_copy` is dispatch-enabled by default. Explicit dispatch of the other seeded strategies should return `SKIP strategy_dispatch_disabled`.

### Deterministic wallet-first conversion

For `wallet_shadow_copy`, the bridge resolves the upstream wallet shadow candidate from stored source references and derives an execution request deterministically:

- `market_ref`: prefer `condition_id`, else `market_slug`
- `outcome`: from the approved intent
- `side`: from the approved intent
- `order_type`: fixed `gtc`
- `post_only`: fixed `false`

Dispatch price uses fresh public book context:

- `buy`: best ask, else midpoint, else upstream `current_price`
- `sell`: best bid, else midpoint, else upstream `current_price`

Dispatch size is derived from upstream notional:

- `size = simulated_size_usdc / dispatch_price`
- rounded down to 6 decimal places
- invalid or zero sizes return `SKIP`

### Dispatch-time risk checks

Risk and policy checks run before calling execution:

- market active and open when required
- drift threshold
- spread threshold
- max notional per order
- max exposure per market
- max exposure per strategy
- balance readiness
- allowance readiness

Exposure is defined in this phase as tool-local planned exposure from prior non-skip strategy dispatch results. It is not a full account-wide risk engine.

If checks fail, dispatch persists `SKIP` plus reason blocks and does not call execution. If checks pass:

- paper dispatch reuses the existing execution post path in paper mode
- live dispatch reuses the existing execution post path with `live=True` and explicit confirmation

Every dispatch persists:

- a normalized dispatch result
- a link record joining `intent_id`, `execution_id`, execution plan/result ids, and order id when available

## Explainability and Partial Errors

Every evaluated intent includes explicit `reason_blocks` with:

- `section`
- `status`
- `message`

Aggregate outputs may also include structured partial errors:

- `section`
- `code`
- `message`

Partial gaps should degrade into explainable outcomes when possible instead of crashing the full evaluation or dispatch pass.

## Manual Review and Dispatch Lifecycle

The intended operator flow in the current phase is:

1. run `pm strategy evaluate --name ...`
2. inspect `pm strategy intents`
3. inspect one candidate with `pm strategy review --intent-id ...`
4. append a local manual decision with:
   - `pm strategy approve --intent-id ...`
   - or `pm strategy reject --intent-id ... --reason "..."`
5. optionally hand off one approved intent with:
   - `pm strategy dispatch --intent-id ...`
   - or `pm strategy dispatch --intent-id ... --live --confirm`
6. optionally inspect persisted bridge history with:
   - `pm strategy executions`
   - `pm strategy execution get --execution-id ...`

Manual review and dispatch records are append-only. The latest review record determines manual status, while dispatch history remains a separate audit trail.

## Non-Goals in This Phase

- no strategy authoring UI
- no background orchestration loop
- no database-backed signal bus
- no LLM-controlled execution policy
- no automatic approval path
- no strategy self-execution or auto-submit loop

## Future Direction

Later phases may add:

- richer strategy configuration
- pause and resume controls
- stronger observability and audit trails
- shell or TUI review surfaces
- broader strategy-specific execution mappings beyond wallet-first dispatch
- market-specific recurring strategies such as `btc_15m_chainlink_ladder`

The BTC 15m ladder track is intentionally planned as a specialized follow-on to
the generic `recurring_crypto_interval_observe` strategy, not as an immediate
replacement for it.

Those features are intentionally deferred until auth, signing, approval, execution, and operator UX boundaries are designed explicitly.
