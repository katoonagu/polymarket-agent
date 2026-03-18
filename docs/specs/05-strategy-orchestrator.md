# 05 - Read-Only Strategy and Orchestrator Spec

## Purpose

This phase adds a deterministic strategy registry and orchestration layer on top of the existing public intelligence stack. The strategy layer consumes read-only market, wallet, and stream artifacts and produces candidate intents plus manual review decisions only.

It does not:

- authenticate wallets
- sign transactions
- place or cancel orders
- call the execution engine
- run as a daemon
- require a database

Execution remains the only module allowed to place or cancel orders in later phases.

## Current Scope

The current branch exposes a read-only `pm strategy` namespace with:

```text
pm strategy list
pm strategy show --name <name>
pm strategy validate --name <name>
pm strategy evaluate --name <name> [--limit <n>]
pm strategy intents [--limit <n>]
pm strategy review --intent-id <id>
pm strategy approve --intent-id <id>
pm strategy reject --intent-id <id> --reason <text>
```

These commands operate on local gitignored state and existing public intelligence outputs.

## Local State

Strategy state lives under `.pm/state/`:

- `strategies.json`
- `strategy-intents.json`
- `strategy-decisions.json`

Rules:

- files are versioned JSON documents
- writes are atomic
- append order is deterministic
- validation failures surface as explicit state errors
- past intents are never mutated in place
- current review status is derived from the latest decision record for an intent

## Seeded Strategy Registry

The registry is seeded and deterministic in v1. There are no create, edit, pause, or resume commands yet.

Current seeded strategies:

1. `wallet_shadow_copy`
2. `market_watch_reversion`
3. `recurring_crypto_interval_observe`

In v1, strategy names match strategy types exactly.

## Strategy Inputs

### `wallet_shadow_copy`

Consumes persisted wallet shadow simulation output:

- `wallet-shadow-runs.json`

It looks only at upstream shadow candidates and never executes them.

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

## Decision States

The current read-only phase uses:

- `OBSERVE`
- `WAIT`
- `APPROVE`
- `REJECT`

Rules:

- `evaluate` may emit only `OBSERVE`, `WAIT`, or `REJECT`
- `APPROVE` is manual only
- `approve` and `reject` append local review records only
- no decision is forwarded to execution in this phase

## Seeded Policy Behavior

### `wallet_shadow_copy`

Source:

- persisted wallet shadow candidate intents

Behavior:

- upstream `WOULD_COPY` candidates with complete context become `WAIT`
- upstream `WOULD_COPY` candidates with incomplete or stale context become `OBSERVE`
- upstream `SKIP` candidates become `REJECT`

### `market_watch_reversion`

Source:

- watched markets
- baseline market snapshots
- fresh current snapshot context

Behavior:

- default outcome is conservative
- emits `WAIT` only when the market is active, open, and widened spread plus midpoint drift exceed the seeded thresholds
- emits `OBSERVE` when data is incomplete or the move is weaker
- emits `REJECT` when the market is inactive or closed

### `recurring_crypto_interval_observe`

Source:

- recurring resolver output
- persisted market stream events
- persisted RTDS crypto events

Behavior:

- emits `WAIT` only when recurring market direction aligns with crypto direction strongly enough
- emits `OBSERVE` when the recurring candidate is valid but alignment is weak or incomplete
- emits `REJECT` when the resolved recurring market is inactive or closed

## Explainability and Partial Errors

Every evaluated intent includes explicit `reason_blocks` with:

- `section`
- `status`
- `message`

Aggregate outputs may also include structured partial errors:

- `section`
- `code`
- `message`

Partial gaps should degrade into explainable `OBSERVE` or `REJECT` outcomes when possible instead of crashing the full evaluation pass.

## Manual Review Lifecycle

The intended operator flow in the current phase is:

1. run `pm strategy evaluate --name ...`
2. inspect `pm strategy intents`
3. inspect one candidate with `pm strategy review --intent-id ...`
4. append a local manual decision with:
   - `pm strategy approve --intent-id ...`
   - or `pm strategy reject --intent-id ... --reason "..."`

Manual review records are append-only. The latest review record determines the current manual status shown by `review` and `intents`.

## Non-Goals in This Phase

- no strategy authoring UI
- no live execution hooks
- no order payload generation
- no background orchestration loop
- no database-backed signal bus
- no LLM-controlled execution policy
- no automatic approval path

## Future Direction

Later phases may add:

- richer strategy configuration
- pause and resume controls
- execution-bound handoff after explicit approval
- stronger observability and audit trails
- shell or TUI review surfaces

Those features are intentionally deferred until auth, signing, approval, and execution boundaries are designed explicitly.
