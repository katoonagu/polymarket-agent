# 01 - Execution Engine Spec

## Purpose

The execution layer is the only module allowed to place, cancel, or eventually replace orders. Every other module in this repository may produce context, rankings, signals, candidate intents, or manual review decisions only.

The current phase introduces the first controlled write path:

- authenticated setup and readiness checks
- authenticated balances and allowance reads
- guarded approval inspection and approval writes
- local dry-run order construction and signing
- paper-default order posting and cancellation lifecycle
- explicitly gated live order submission and cancellation

The current phase still does not include:

- replace flows
- automatic retry loops
- user websocket sessions
- background daemons
- strategy auto-submit
- database-backed execution state

## Current Phase Boundary

Implemented now:

- `pm setup doctor`
- `pm auth show`
- `pm auth derive-api-key`
- `pm auth balances`
- `pm auth allowances`
- `pm approve check`
- `pm approve set`
- `pm exec dry-run`
- `pm exec post`
- `pm exec orders open`
- `pm exec order get`
- `pm exec cancel`
- `pm exec cancel-all`
- `pm exec cancel-market`

Still out of scope:

- replace flows
- automatic fills reconciliation
- live order polling loops
- private websocket order status channels
- execution orchestration from strategy

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

- `approval-plans.json`
- `approval-results.json`
- `execution-order-plans.json`
- `execution-order-results.json`

Rules:

- versioned JSON documents
- atomic writes
- append-only records
- explicit state errors on invalid or corrupted files

The current phase still adds no local cache for:

- private keys
- API credentials
- balances
- allowances
- open orders
- fills

## Module Boundaries

### Intelligence modules

The following modules remain unable to place or cancel orders:

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

### Execution module

The execution module remains the only owner of:

- approval writes
- order posting
- order cancellation
- future replace flows
- future execution status tracking
- future fills reconciliation

Strategy and orchestrator flows must remain unable to auto-submit during this phase.

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
- private websocket execution status
- guarded operator shell and status surfaces
- replay and audit tooling

Those capabilities remain outside the current controlled write-path foundation.
