# 04 - Arkham Intelligence Spec

## Purpose

The Arkham module is the first external intelligence enrichment layer on top of the existing Polymarket operator stack. It exists to add richer address context for tracked wallets and manual investigations without adding new execution behavior.

In the current phase, Arkham is:

- an operator-driven intelligence overlay
- a cache-backed address enrichment service
- a dossier builder for manual review
- a suspicious-wallet heuristic layer for tracked wallets

It is not:

- a trading trigger
- a daemon
- a live execution dependency
- a source of absolute truth

## Current Scope

The implemented slice supports:

- `pm arkham status`
- `pm arkham enrich --address <0x...>`
- `pm arkham dossier --address <0x...>`
- `pm arkham sync tracked [--limit <n>]`
- `pm arkham suspicious tracked [--limit <n>]`

The current implementation uses only documented Arkham REST endpoints:

- `GET /chains`
- `GET /intelligence/address/{address}`
- `GET /intelligence/address_enriched/{address}`
- `GET /intelligence/entity/{entity}`
- `GET /counterparties/address/{address}`

If a broader capability is not documented, this module must degrade gracefully instead of inventing unsupported behavior.

## Auth and Safety Rules

- Arkham credentials are env-only.
- `ARKHAM_API_KEY` is the canonical env var.
- `PM_ARKHAM_API_KEY` is a supported compatibility alias.
- Raw Arkham secrets must never be printed.
- No plaintext secret storage is added.
- Missing credentials must return a clean readiness/help response instead of crashing the namespace.
- Arkham outputs are heuristic context only and must never auto-submit, auto-dispatch, or auto-trade.

## Data Model and Local State

The module persists local cache-style enrichment state in:

- `.pm/state/arkham-enrichments.json`

This file stores one latest normalized enrichment record per address with:

- address
- verified, predicted, and user entity context when present
- verified and user label context when present
- populated tags
- cluster ids
- contract, service, and program flags when present
- deterministic confidence classification:
  - `verified`
  - `predicted`
  - `user`
  - `unknown`
- recent enrichment timestamp
- source attribution
- structured partial errors

State rules:

- versioned JSON document
- atomic writes
- explicit state errors on invalid files
- cache-style replacement for the same address rather than append-only history

## Command Behavior

### `pm arkham status`

Returns:

- whether Arkham credentials are configured
- which env source is active
- whether the Arkham API is reachable via `GET /chains`
- tracked-wallet count from the local wallet registry
- cached-enrichment count
- latest enrichment timestamp
- next-step guidance when credentials are missing

### `pm arkham enrich`

Behavior:

- normalize the supplied address using the existing wallet-address rules
- fetch primary enrichment from `address_enriched`
- if `address_enriched` fails, attempt degraded assembly from `address`
- persist the normalized latest record locally
- return structured partial errors when only some Arkham sections succeed

### `pm arkham dossier`

Behavior:

- build from the latest enrichment plus best-effort Arkham add-ons
- resolve entity details using this priority:
  1. verified entity
  2. predicted entity
  3. user entity
- fetch top counterparties with fixed defaults:
  - `limit=10`
  - `timeLast=30d`
- if credentials are missing, return readiness/help plus any cached enrichment already available locally

### `pm arkham sync tracked`

Behavior:

- read tracked wallets from the local wallet registry in registry order
- default `limit=20`
- enrich up to `limit` tracked wallets
- persist updated cache entries
- continue across per-wallet failures and surface partial errors

### `pm arkham suspicious tracked`

Behavior:

- use the tracked-wallet registry plus the latest local Arkham cache only
- make no implicit Arkham network calls
- rank watch candidates deterministically
- frame results as heuristics, flags, and watch candidates rather than accusations

## Suspicious-Wallet Heuristics

The suspicious tracked-wallet layer combines:

- Arkham enrichment presence and attribution quality
- Arkham risk-style tags and labels when clearly present
- shared `clusterIds` across tracked wallets
- shared verified or predicted entity ids across tracked wallets
- local wallet-pipeline context from the existing wallet module:
  - event counts
  - signal counts
  - shadow-run counts
  - repeated `WOULD_COPY` counts
  - concentrated market footprint hints

The local watch lexicon is intentionally narrow and only flags clear Arkham text matching:

- sanctions or blocklist
- exploit or hack
- fraud or scam
- mixer or obfuscation
- other clearly high-risk service references

If Arkham does not provide a documented field, the signal stays absent instead of being inferred.

## Output Contract

The module should return normalized snake_case JSON and stable human-readable summaries.

Important response families:

- readiness and status
- single-address enrichment
- dossier
- tracked sync batch
- suspicious tracked ranking

Partial errors should follow the repo-wide shape:

```json
{
  "section": "address_enriched",
  "code": "request_failed",
  "message": "..."
}
```

## Boundaries

The current branch intentionally does not include:

- graph-building commands
- flow timeline commands
- cluster review or approval workflows
- alert daemons
- websocket ingestion
- strategy auto-execution from Arkham outputs
- any execution-side order placement or cancellation path

Arkham remains an intelligence input only. Execution stays isolated and operator-driven.
