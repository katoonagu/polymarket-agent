# 01 - Execution Engine Spec

## Purpose

The execution layer is the only module allowed to place, cancel, or eventually replace orders. Every other module in this repository may produce context, rankings, signals, candidate intents, or manual review decisions only.

The current phase includes:

- authenticated setup and readiness checks
- authenticated balances and allowance reads
- guarded approval inspection and approval writes
- local dry-run order construction and signing
- paper-default order posting and cancellation lifecycle
- explicitly gated live order submission and cancellation
- bounded authenticated user-channel watch and reconciliation
- guarded manual strategy-to-execution dispatch
- portfolio truth and reconciliation views built on top of execution audit state

The current phase still does not include:

- replace flows
- automatic retry loops
- background daemons
- strategy auto-submit
- database-backed execution state

## Current Phase Boundary

Implemented now:

- `pm setup doctor`
- `pm auth show`
- `pm auth profile show`
- `pm auth profile init`
- `pm auth profile from-env`
- `pm auth profile doctor`
- `pm auth profile clear`
- `pm auth derive-api-key`
- `pm auth balances`
- `pm auth allowances`
- `pm approve check`
- `pm approve set`
- `pm exec dry-run`
- `pm exec post`
- `pm exec orders open`
- `pm exec order get`
- `pm exec watch`
- `pm exec order wait`
- `pm exec events`
- `pm exec reconcile`
- `pm exec cancel`
- `pm exec cancel-all`
- `pm exec cancel-market`
- `pm risk show`
- `pm risk init-defaults`
- `pm strategy dispatch`
- `pm strategy dispatch pending`
- `pm strategy executions`
- `pm strategy execution get`

Still out of scope:

- replace flows
- automatic or daemonized reconciliation loops
- live order polling loops
- unbounded private websocket monitoring
- automatic execution orchestration from strategy
- portfolio-driven order mutation or auto-rebalancing

## Design Principles

- execution stays isolated from intelligence modules
- authenticated access is never required for public intelligence commands
- private keys come from environment only
- raw private keys are never printed
- derived API credentials are ephemeral and are never persisted locally
- live behavior is never the default
- real writes require explicit operator confirmation
- paper and preview flows must remain deterministic, auditable, and operator-safe

## Authenticated Foundation

### Environment Contract

Authenticated commands use environment variables only:

- `POLYMARKET_PRIVATE_KEY`
- `POLYMARKET_SIGNATURE_TYPE`
- `POLYMARKET_FUNDER` when a non-EOA signature type requires it
- `POLYMARKET_CLOB_HOST` optional, default `https://clob.polymarket.com`
- `POLYMARKET_CHAIN_ID` optional, default `137` for the default host

Rules:

- if `POLYMARKET_CLOB_HOST` overrides the default host, `POLYMARKET_CHAIN_ID` must be set explicitly
- signature type must be explicit and must not be guessed
- the private key must never be written to `.pm/state/`
- derived L2 API credentials must never be written to `.pm/state/`

### Non-Secret Operator Profile

Authenticated and portfolio-facing commands may also use a local non-secret operator profile at
`.pm/state/operator-profile.json`.

Stored fields:

- `signer_address`
- `funder_address`
- `signature_type`
- `chain_id`
- `account_label`
- `source`

Rules:

- the profile never stores raw private keys
- the profile never stores derived API credentials
- non-secret account resolution is per-field: CLI override, then operator profile, then env-derived context
- authenticated commands still require env or session private-key access and must reject signer mismatches against the current private key

### Supported Signature Types

The auth layer supports explicit signature-type configuration compatible with the official Polymarket client:

- `EOA`
- `POLY_PROXY`
- `POLY_GNOSIS_SAFE`

Equivalent numeric values are also accepted:

- `0`
- `1`
- `2`

## `pm setup doctor`

`pm setup doctor` is non-mutating. It must not create API credentials, post orders, cancel orders, or write approvals.

It checks:

- private-key env presence and parseability
- signer address derivation
- signature-type parseability
- funder consistency
- official geoblock endpoint status
- CLOB host reachability
- whether the current config is sufficient for ephemeral API-key derivation

It returns:

- a top-level `ready` flag
- normalized auth context
- normalized geoblock result
- sectioned checks
- sectioned errors

## `pm auth`

### `pm auth show`

Shows normalized authenticated context:

- signer address
- funder address
- signature type
- CLOB host
- chain id
- whether a private key is present
- whether ephemeral API-key derivation appears possible

This command is informational and should still succeed when auth config is incomplete. Incomplete or invalid pieces are returned as structured warnings.

### `pm auth profile`

`pm auth profile` manages the local non-secret operator identity profile:

- `pm auth profile show`
- `pm auth profile init`
- `pm auth profile from-env`
- `pm auth profile doctor`
- `pm auth profile clear`

Rules:

- `show` returns `present=false` and `profile=null` when the profile file is missing
- `init` persists one explicit non-secret profile
- `from-env` derives signer from the current private key plus env non-secret fields and persists only non-secret data
- `doctor` is local-only and returns identity, readiness, mismatch warnings, and a geoblock reminder
- `clear` removes the profile file without touching env or session secrets

### `pm auth derive-api-key`

Uses the official Polymarket Python client to derive ephemeral L2 API credentials.

Rules:

- credentials are derived on demand
- credentials are returned in command output
- credentials are not persisted locally
- raw private keys are never printed

### `pm auth balances`

Authenticated collateral balance lookup using the official client.

### `pm auth allowances`

Authenticated collateral allowance lookup using the official client.

## `pm approve`

### `pm approve check`

Returns normalized approval readiness for:

- `usdc` collateral allowance
- `ctf` conditional-token allowance

Each item includes:

- asset type
- balance and allowance snapshot
- target contract address
- exchange address
- readiness flag

### `pm approve set`

`pm approve set --asset <usdc|ctf>` supports two modes:

- preview mode by default
- live mode only with `--live --confirm`

Preview mode:

- builds and validates the approval action
- returns `WOULD_SET` or `SKIP`
- persists a local approval plan
- never sends a write

Live mode:

- requires valid auth config
- requires `--live --confirm`
- rechecks geoblock status before writing
- calls the official client allowance-update flow
- persists both a local plan and a local result

## Strategy-to-Execution Bridge

The current phase adds a guarded bridge from manually approved strategy intents into the execution module.

Commands:

- `pm risk show`
- `pm risk init-defaults`
- `pm strategy dispatch --intent-id <id> [--paper] [--live --confirm]`
- `pm strategy dispatch pending [--limit <n>] [--paper]`
- `pm strategy executions [--limit <n>]`
- `pm strategy execution get --execution-id <id>`

Rules:

- only intents whose latest manual decision is `APPROVE` may dispatch
- paper mode is the default
- live dispatch requires both `--live` and `--confirm`
- `dispatch pending` stays paper-only in this phase
- execution remains the only module that can actually post or cancel orders

`pm risk show` returns the effective dispatch policy set. `pm risk init-defaults` creates a versioned local policy file only when missing.

### Dispatch-enabled strategy scope

The bridge is intentionally narrow in v1:

- `wallet_shadow_copy` is dispatch-enabled by default
- `market_watch_reversion` remains reviewable but returns `SKIP strategy_dispatch_disabled`
- `recurring_crypto_interval_observe` remains reviewable but returns `SKIP strategy_dispatch_disabled`

### Dispatch-time checks

Before calling execution, the bridge runs deterministic policy and risk checks:

- market active and open when required
- drift threshold
- spread threshold
- max size per order
- max exposure per market
- max exposure per strategy
- balance readiness
- allowance readiness

Exposure is tool-local in this phase. It is derived from prior non-skip strategy dispatch results persisted by this tool, not from a full account-wide position engine.

If checks fail, dispatch returns and persists `SKIP` with explicit reason blocks. If checks pass:

- paper dispatch reuses the existing order-post path with `live=False`
- live dispatch reuses the existing order-post path with `live=True` and explicit confirmation

Each dispatch persists:

- a normalized dispatch result
- a linkage record connecting the source `intent_id` to execution plan/result ids and the exchange `order_id` when available

## `pm exec dry-run`

`pm exec dry-run` remains the non-live planning command.

It must:

1. validate CLI-facing arguments
2. validate authenticated configuration
3. run the official geoblock check
4. resolve market context through Gamma
5. map `yes` or `no` to the correct token id
6. fetch public book, midpoint, and spread through the public CLOB adapter
7. fetch tick size, fee rate, and negative-risk context through the official authenticated client
8. validate price and size against deterministic rules
9. build and sign the order locally
10. return a dry-run plan without submission

`pm exec dry-run` returns:

- `WOULD_POST` when local planning succeeds
- `SKIP` when any required validation or readiness check fails

It never posts the signed order.

## `pm exec post`

`pm exec post` is the first order-posting surface.

Inputs:

- `--market <slug|condition_id>`
- `--outcome <yes|no>`
- `--side <buy|sell>`
- `--price <p>`
- `--size <n>`
- `--order-type <gtc|gtd|fok>`
- `--expires-at <iso8601>` required for `gtd`
- `--post-only` allowed only for `gtc` and `gtd`
- `--paper` optional explicit paper mode
- `--live --confirm` for real submission

Rules:

- paper mode is the default even when `--paper` is omitted
- live submission requires both `--live` and `--confirm`
- geoblock must be checked again before any live submission
- tick size must be validated
- minimum order size must be validated when available
- balance and allowance readiness must be validated
- negative-risk context must be carried through to local signing

Responses:

- `WOULD_POST` for paper-mode plans that pass validation
- `POSTED` for live orders successfully submitted
- `SKIP` when validation, readiness, geoblock, or live submission fails

## Authenticated Order Reads

### `pm exec orders open`

Authenticated live read for open orders with optional filters:

- `--market <condition_id>`
- `--token-id <asset_id>`

### `pm exec order get`

Authenticated live read for a single order by `--order-id`.

These commands read exchange state through the official authenticated client. They do not use paper-mode local state as a replacement for exchange reads.

## Authenticated Execution Watch

### `pm exec watch`

`pm exec watch` opens a bounded authenticated user-websocket session.

Inputs:

- optional `--market <condition_id>`
- optional `--seconds <n>`, default `10`
- optional `--max-events <n>`

Rules:

- the websocket uses ephemeral Level 2 API credentials derived through the auth layer
- credentials are not persisted locally
- sessions are always bounded by time or event count
- if `--market` is omitted, the command derives condition IDs from current open orders
- if no open-order condition IDs are available and no `--market` is provided, the command returns a deterministic `not_found` error
- reconnects are limited and there is no infinite retry loop

Normalized event fields include:

- `session_id`
- `source`
- `captured_at`
- `condition_id`
- `order_id`
- `asset_id`
- `event_type`
- `trade_status`
- `side`
- `price`
- `size`
- `status`
- `timestamp`

Supported normalized order events:

- `PLACEMENT`
- `UPDATE`
- `CANCELLATION`

Supported normalized trade statuses:

- `MATCHED`
- `MINED`
- `CONFIRMED`
- `RETRYING`
- `FAILED`

### `pm exec order wait`

`pm exec order wait --order-id <id> --seconds <n>`:

- resolves the order through authenticated REST first
- subscribes to that order's condition ID only
- persists matching normalized events locally
- returns success JSON on both terminal completion and timeout

Terminal outcomes in this phase:

- `CANCELLATION`
- `CONFIRMED`
- `FAILED`

Non-terminal statuses in this phase:

- `MATCHED`
- `MINED`
- `RETRYING`

On timeout, the command performs one final authenticated `order get` read and includes it in the response when available.

### `pm exec events`

`pm exec events` reads the local persisted execution event log only. It does not open a websocket session.

### `pm exec reconcile`

`pm exec reconcile` compares the latest persisted execution websocket events with:

- one authenticated `orders open` view
- per-order authenticated `order get` views

The current phase uses a fixed reconciliation window of the latest 100 persisted execution events and classifies each recent order as:

- `consistent_open`
- `consistent_closed`
- `inconclusive`
- `mismatch`

Each run persists a local reconciliation summary.

The BTC15m one-window live session controller now reuses this same bounded
execution stack directly:

- `pm strategy btc15m session arm --next --mode live --confirm` performs
  non-mutating authenticated preflight through the shared execution services
- `pm strategy btc15m session run --session-id <id>` posts and cancels BTC15m
  ladder rungs through the existing lifecycle service only
- final BTC15m session reports persist order linkage plus the latest execution
  reconciliation summary after the bounded live window completes

## Cancellation Surface

### `pm exec cancel`

Preview or cancel one order by `--order-id`.

### `pm exec cancel-all`

Preview or cancel all currently open orders.

### `pm exec cancel-market`

Preview or cancel market-scoped orders using:

- `--market <condition_id>`
- optional `--token-id <asset_id>`

Cancellation rules:

- paper mode is the default
- live cancellation requires `--live --confirm`
- geoblock must be checked before live cancellation
- every paper or live cancellation attempt persists a local audit record

## Deterministic Skip Rules

Execution responses return `decision: SKIP` when relevant conditions fail, including:

- missing or invalid auth config
- official geoblock check failure or blocked status for live writes
- market not found
- inactive or closed market
- requested outcome cannot be mapped to a token id
- book context cannot be fetched
- price is not aligned to tick size
- price is outside the permitted range
- size is below minimum order size when known
- balance is insufficient
- allowance is insufficient
- local signing fails
- live submission or cancellation call fails

## Local Execution State

The current execution phase persists append-only local audit state under `.pm/state/`:

- `risk-policies.json`
- `strategy-execution-links.json`
- `strategy-dispatch-results.json`
- `approval-plans.json`
- `approval-results.json`
- `execution-order-plans.json`
- `execution-order-results.json`
- `execution-events.jsonl`
- `execution-reconciliations.json`
- `portfolio-snapshots.json`
- `portfolio-reconciliations.json`

The portfolio layer depends on execution audit and reconciliation records for attribution and discrepancy reporting, but it does not take order ownership away from execution. Execution remains the only module that can place or cancel orders.

Rules:

- versioned JSON documents
- atomic writes
- append-only records
- explicit state errors on invalid or corrupted files

## Still Out of Scope

- replace flows
- background or daemonized private websocket monitoring
- automatic retry loops
- strategy-driven auto-submit or auto-cancel
- strategy self-execution without explicit dispatch
- database-backed execution storage

The current phase still adds no local cache for:

- private keys
- API credentials
- balances
- allowances
- open orders
- fills

## Module Boundaries

### Intelligence modules

The following modules remain unable to place or cancel orders directly:

- market intelligence
- public CLOB reads
- Data API reads
- wallet intelligence
- stream capture
- strategy and orchestrator

They may only emit:

- context
- watchlists
- signals
- candidate intents
- local review decisions

Strategy and orchestrator may hand off only through explicit manual dispatch plus risk policy.

### Execution module

The execution module remains the only owner of:

- approval writes
- order posting
- order cancellation
- bounded authenticated execution status tracking
- future replace flows
- future fills reconciliation

Execution remains the only module allowed to place or cancel orders.

## Security Requirements

- private keys must come from environment only
- raw private keys must never be logged or printed
- derived API credentials must never be persisted
- authenticated output may include derived API credentials and signed-order material, but never the raw private key
- live behavior must remain explicitly gated and non-default

## Next Execution Phases

Later phases may add:

- replace flows
- richer execution status views
- fills reconciliation
- background private websocket monitoring
- guarded operator shell and status surfaces
- replay and audit tooling

Those capabilities remain outside the current controlled write-path foundation.
