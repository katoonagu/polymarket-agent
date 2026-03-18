# 01 - Execution Engine Spec

## Purpose

The execution layer is the only module allowed to place, replace, or cancel orders. Every other module in this repository may produce context, rankings, signals, candidate intents, or manual review decisions only.

The current phase does not enable live trading. It introduces the first authenticated foundation for:

- non-mutating setup and readiness checks
- authenticated balance and allowance reads
- local order construction and signing
- dry-run execution planning

It does not yet allow:

- live order submission
- cancel or replace flows
- on-chain approval writes
- user websocket sessions
- background daemons
- database-backed execution state

## Current Phase Boundary

The current execution phase is intentionally conservative.

Implemented now:

- `pm setup doctor`
- `pm auth show`
- `pm auth derive-api-key`
- `pm auth balances`
- `pm auth allowances`
- `pm exec dry-run`

Not implemented yet:

- `pm exec buy`
- `pm exec sell`
- `pm exec cancel`
- `pm exec replace`
- execution lifecycle tracking
- fills reconciliation
- live order status polling

## Design Principles

- execution stays isolated from intelligence modules
- authenticated access is never the default for public intelligence commands
- private keys come from environment only
- raw private keys are never printed
- derived API credentials are ephemeral and are never persisted locally
- live order submission must remain a separate later phase
- dry-run must stay deterministic, auditable, and operator-safe

## Authenticated Foundation

### Environment contract

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

### Supported signature types

The current auth layer supports explicit signature-type configuration compatible with the official Polymarket client:

- `EOA`
- `POLY_PROXY`
- `POLY_GNOSIS_SAFE`

Equivalent numeric values are also accepted:

- `0`
- `1`
- `2`

## `pm setup doctor`

`pm setup doctor` is non-mutating. It must not create API credentials, post orders, or change on-chain or exchange state.

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

This phase is read-only with respect to allowances. It does not implement approval writes.

## `pm exec dry-run`

`pm exec dry-run` is the only execution-facing command implemented in this phase.

### Inputs

- `--market <slug|condition_id>`
- `--outcome <yes|no>`
- `--side <buy|sell>`
- `--price <p>`
- `--size <n>`

### Resolution flow

The dry-run planner must:

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

### Deterministic skip rules

The dry-run response returns `decision: SKIP` when any of these conditions apply:

- market not found
- market inactive
- market closed
- requested outcome cannot be mapped to a token id
- authenticated configuration is missing or invalid
- official geoblock check fails or reports blocked access
- public book context cannot be fetched
- price is not aligned to tick size
- price is outside the permitted tick-size-constrained range
- size is below the discovered minimum order size when present
- fee-rate lookup fails
- local signing fails

### `WOULD_POST`

The dry-run response returns `decision: WOULD_POST` only when:

- auth config is valid
- geoblock check passes
- market and token context resolve cleanly
- market is active and open
- price and size pass validation
- local signing succeeds

### Response contract

Dry-run JSON should include at least:

- request summary
- auth context summary
- resolved market context
- token and outcome mapping
- public book context
- tick size, fee rate, and minimum order size context
- locally signed order payload
- `decision`
- `reasons`

The signed order payload is built locally and never posted in this phase.

## Module Boundaries

### Intelligence modules

The following modules remain read-only and may never place or cancel orders:

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

The execution module remains the only future owner of:

- live posting
- cancel and replace
- execution status tracking
- order lifecycle state
- fills reconciliation
- execution audit events

This ownership rule already applies even though only dry-run is implemented now.

## Security Requirements

- private keys must come from environment only
- raw private keys must never be logged or printed
- derived API credentials must never be persisted
- authenticated dry-run output may include derived API credentials and signed-order material, but never the raw private key
- execution-safe behavior must remain the default

## Local State

This phase intentionally adds no local auth cache and no execution database tables.

There are no new `.pm/state/` files for:

- private keys
- API credentials
- balances cache
- allowances cache
- posted orders
- open orders
- fills

## Next Execution Phases

Later phases may add:

- approval inspection and mutation flows
- live order submission
- cancel and replace
- execution status views
- order and fill reconciliation
- execution audit logs
- guarded operator setup flows

Those capabilities remain out of scope for the current authenticated dry-run foundation.
