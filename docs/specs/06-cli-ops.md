# 06 - CLI, Storage, Observability & Operations Spec

## Purpose

<<<<<<< HEAD
The system is operated through the CLI first. That remains the right default for the early phases of `polymarket-agent` because it keeps the surface area small, makes behavior easy to audit, and allows output and control contracts to stabilize before any later TUI or web layer.

This spec covers:

- the canonical CLI contract;
- output and error behavior;
- storage and observability expectations;
- replay and incident workflows;
- operator-facing requirements that must remain separate from execution internals.

## CLI Design Principles

### 1. Namespace-first command grammar

Commands should group by resource family first, then action:

```text
pm market search ...
pm market show ...
pm market event ...
pm clob book ...
pm clob price ...
pm ops replay ...
```

This keeps the public surface consistent with the current Python architecture and aligns with the most useful read-only patterns from the official Polymarket CLI without copying its architecture wholesale.

### 2. Read-only commands stay read-only

Market discovery and public CLOB commands must not place, replace, or cancel orders. Only the execution module may ever own mutating trading behavior.

### 3. Dry-run and paper remain the safe defaults

When mutating commands are added later, they must default to `dry-run` or `paper` behavior where possible and require explicit confirmation for any higher-risk path. This does not apply to the current read-only market and CLOB commands.

### 4. Deterministic human and machine output

The CLI must support both operator-friendly output and script-friendly JSON output through one stable contract.

### 5. Auditability over convenience

Every meaningful command should be explainable after the fact through logs, artifacts, or replay data. The CLI is part of the operating boundary, not just a thin wrapper around APIs.

## Global Output Contract

All CLI commands should converge on one global output contract:

- `--output table|json`
- default: `table`
- `--json` is a compatibility alias for `--output json`

Primary rules:

- human output is optimized for operator reading;
- JSON output is optimized for scripts and automation;
- successful JSON responses use normalized `snake_case` fields;
- the user-facing JSON contract must not expose raw Gamma or CLOB wire payloads as the long-term public API;
- command output should be deterministic so tests and replay tooling can rely on it.

## JSON Error Contract

When JSON output is requested, command and parser failures should use one structured error envelope:

```json
{
  "ok": false,
  "error": {
    "code": "not_found",
    "message": "market not found",
    "resource": "market",
    "identifier": "bitboy-convicted"
  }
}
```

Expected error codes include:

- `not_found`
- `request_failed`
- `invalid_argument`
- `unknown_command`
- `usage_error`

The exact message text may vary by command, but the envelope shape should remain stable.

## Canonical CLI Namespaces

### `pm market`

Canonical namespace for Gamma-backed market discovery and metadata lookup.

Primary read-only commands:

```text
pm market search --query "btc"
pm market show --slug <slug>
pm market event --slug <slug>
```

Planned later additions may include list-style discovery or normalized series support, but only after the adapter layer and tests define a stable public contract.

### `pm clob`

Canonical namespace for public read-only CLOB data.

Primary read-only commands:

```text
pm clob book --token-id <id>
pm clob price --token-id <id>
```

This namespace is the long-term home for public order book, pricing, midpoint, spread, and similar read-only CLOB operations.

### Temporary compatibility aliases

The following commands are temporary backward-compatible aliases and should be treated as deprecated in docs and help text:

- `pm market book`
- `pm market price`

They exist only to avoid breaking existing read-only workflows during the namespace transition. They should not appear in the primary example set for the long-term CLI contract.

### Future namespaces

These namespaces remain part of the broader architecture, but are outside the current public read-only CLI scope:

- `pm wallet`
- `pm arkham`
- `pm strategy`
- `pm exec`
- `pm risk`
- `pm ops`

Any future mutating behavior under these namespaces must continue to respect the execution-only boundary for order placement and cancellation.

## Example Command Set

Canonical examples:

```text
pm market search --query "btc 15 min"
pm market show --slug <slug>
pm market event --slug <slug>
pm clob book --token-id <id>
pm clob price --token-id <id>
pm ops replay --from 2026-02-17T00:00:00Z --to 2026-02-17T12:00:00Z
```

Compatibility-only examples:

```text
pm market book --token-id <id>
pm market price --token-id <id>
```

## Storage Requirements

These are architecture targets, not a statement about the current implementation.

### Core database

Postgres is the preferred future relational store once persistence is introduced.

### Cache / queue

Redis is the preferred future cache or queue layer for:

- recent snapshots;
- transient locks;
- idempotency windows;
- work queues.

### Event log

An append-only event log should exist for:

- signals;
- approvals;
- trade intents;
- execution events;
- fills;
- reconciliations;
- alerts.

## Suggested Database Model

### Core tables

- `markets`
- `market_snapshots`
- `wallet_profiles`
- `wallet_events`
- `strategies`
- `signals`
- `candidate_intents`
- `trade_intents`
- `orders`
- `fills`
- `positions`
- `alerts`
- `audit_events`
- `risk_limits`

### Optional later

- `clusters`
- `entities`
- `news_briefs`
- `semantic_relationships`

## Observability

### Structured logging

Minimum fields:

- `timestamp`
- `module`
- `correlation_id`
- `intent_id`
- `wallet_id`
- `market_slug`
- `event_type`
- `status`
- `latency_ms`

### Metrics

- order submit latency
- market snapshot latency
- websocket reconnect count
- rate-limit events
- copied trades count
- skipped trades count
- rejected intents count
- pnl by strategy
- exposure by topic
- spread filter hit rate

### Alerts

- execution failure burst
- position reconciliation mismatch
- stale market data
- wallet monitor lag
- Arkham enrichment failure
- daily loss threshold breach
- kill switch activated

## Replay and Postmortem

Replay is a required operating mode. Operators should be able to:

- reconstruct system state at a timestamp `T`;
- see which signals arrived;
- inspect which checks passed or failed;
- understand which intent or order lifecycle path was taken;
- explain why a position remained open, was simulated, or was skipped.

Required retained artifacts:

- market snapshots
- signal history
- candidate intents
- approvals
- execution events
- final position state

## Risk Console in CLI

Representative future commands:
=======
The CLI is the first operator surface for this repository. It exists to expose deterministic, auditable workflows while keeping research, market intelligence, and execution boundaries explicit.

For the current phase, the CLI is read-only. It may read public Gamma, public CLOB, and public Data API data, and it may manage a local gitignored tracked-wallet registry. It must not authenticate, sign, place orders, cancel orders, manage live wallets, or persist state in a database.

## Current Read-Only CLI Contract

### Canonical namespaces

- `pm market`
  - Public Gamma market discovery
  - Search, market lookup, and event lookup
- `pm clob`
  - Public CLOB order book and price reads
  - Book, price, midpoint, and spread
- `pm data`
  - Public Data API reads
  - Trades, activity, positions, closed positions, holders, open interest, value, and traded-count reads
- `pm wallet`
  - Local tracked-wallet registry and read-only shadow intelligence
  - Registry CRUD, non-mutating wallet discovery, deterministic wallet scoring, tracked-wallet summary, tracked-wallet trades/activity/positions, and compact snapshots

### Temporary compatibility aliases

The following commands remain available for backward compatibility only:

- `pm market book`
- `pm market price`

They are deprecated aliases for:

- `pm clob book`
- `pm clob price`

Primary examples and new automation should use the canonical `pm clob` namespace.

## Output Contract

### Global output mode

All read-only commands support a root output contract:

```text
pm --output table market search --query "btc"
pm --output json clob book --token-id <id>
pm --json market event --slug <slug>
```

Rules:

- `--output table|json` is the canonical selector.
- `--json` is a convenience alias for `--output json`.
- Default output mode is `table`.
- Command-local `--json` remains supported for compatibility and overrides root `--output table`.

### Success JSON

Successful JSON responses must:

- remain deterministic;
- use normalized snake_case keys;
- avoid exposing raw Gamma or raw CLOB wire payloads as the user-facing contract.

### Error JSON

Error responses must use this envelope:

```json
{
  "ok": false,
  "error": {
    "code": "not_found",
    "message": "...",
    "resource": "...",
    "identifier": "..."
  }
}
```

Commands may add a sibling `hint` object when that improves operator UX without changing the base error shape.

## Current Commands

### Market discovery

```text
pm market search --query "<text>" --limit <n> [--json]
pm market show --slug <market-slug> [--json]
pm market event --slug <event-slug> [--json]
```

`pm market show` should help the operator recover from slug misuse. If the provided slug is not a market slug but resolves as an event slug, the CLI should return a clear hint directing the operator to `pm market event --slug ...` and include returned `market_slug` values when available.

### Public CLOB reads
>>>>>>> feat/02a-python-scaffold

```text
pm clob book --token-id <id> [--json]
pm clob price --token-id <id> [--json]
pm clob midpoint --token-id <id> [--json]
pm clob spread --token-id <id> [--json]
```

<<<<<<< HEAD
## Incident Operations

### Types of incidents

- duplicate execution
- stale data execution
- missed cancel
- overexposure
- wallet misclassification
- replay mismatch
- rate-limit degradation
- websocket data gap

### Incident workflow

1. detect
2. freeze or scope-limit
3. reconcile
4. produce postmortem
5. patch rule or spec
6. replay the affected window

## MVP Definition

CLI and operations support are considered minimally ready when:

1. the public read-only CLI surface is available through canonical namespaces;
2. JSON output mode exists with a stable normalized contract;
3. command behavior is auditable;
4. replay workflows exist;
5. a risk console can express operator controls;
6. kill switch behavior is defined globally and at the strategy level;
7. operators can understand what happened after a failure.

## Later Expansion

- TUI dashboard
- web control panel
- role-based access
- scheduled job UI
- alert routing in Slack, Telegram, or Discord
=======
These commands are public and read-only. They must not depend on auth, private keys, trading SDKs, or websocket sessions.

### Public Data API reads

```text
pm data trades --user <0x...> [--limit <n>] [--json]
pm data activity --user <0x...> [--limit <n>] [--json]
pm data positions --user <0x...> [--json]
pm data closed-positions --user <0x...> [--json]
pm data holders --market <market-slug-or-condition-id> [--limit <n>] [--json]
pm data open-interest --market <market-slug-or-condition-id> [--json]
pm data value --user <0x...> [--json]
pm data traded --user <0x...> [--json]
```

Rules:

- `--user` must be a public EVM address in `0x` + 40 hex format.
- `--market` may be either a market slug or a `0x` + 64 hex condition ID.
- Market references are resolved through the public Gamma adapter before Data API calls when needed.
- JSON output remains normalized, deterministic, and snake_case.
- These commands are public and read-only. They must not depend on auth, private keys, websocket sessions, or local persistence.

### Local tracked-wallet registry and shadow intelligence

```text
pm wallet add --address <0x...> [--label <text>] [--tag <text>] [--note <text>]
pm wallet list [--json]
pm wallet remove --address <0x...>
pm wallet discover leaderboard --limit <n> [--json]
pm wallet discover holders --market <market-slug-or-condition-id> --limit <n> [--json]
pm wallet summary --address <0x...> [--limit <n>] [--json]
pm wallet trades --address <0x...> [--limit <n>] [--json]
pm wallet activity --address <0x...> [--limit <n>] [--json]
pm wallet positions --address <0x...> [--json]
pm wallet monitor run --address <0x...> [--limit <n>] [--json]
pm wallet signals --address <0x...> [--limit <n>] [--json]
pm wallet shadow simulate --address <0x...> --fixed-size <usdc> --max-drift <pct> --max-spread <pct> [--entry-only] [--limit <n>] [--json]
pm wallet shadow report --address <0x...> [--json]
pm wallet score --address <0x...> [--json]
pm wallet rank tracked [--json]
pm wallet compare --address <0x...> --address <0x...> [--json]
pm wallet snapshot [--limit <n>] [--json]
```

Rules:

- Registry state lives only in `.pm/state/wallets.json`.
- Registry state is local-only and must be gitignored.
- Address-based `pm wallet` reads are tracked-wallet operations only; untracked addresses return a deterministic `not_tracked` error.
- `pm wallet discover` is non-mutating. It may read the public trader leaderboard and public holder data, but it must not auto-add discovered wallets to the local registry.
- `pm wallet monitor run`, `pm wallet signals`, `pm wallet shadow simulate`, and `pm wallet shadow report` are tracked-wallet operations only.
- The wallet shadow pipeline stores local gitignored append-only state under `.pm/state/`:
  - `wallet-events.json`
  - `wallet-signals.json`
  - `wallet-shadow-runs.json`
- `monitor run` merges recent public trades and activity rows, dedupes by `transaction_hash + token_id + side + timestamp`, and persists only new events plus their derived signals.
- `signals` reads persisted derived signals in deterministic reverse-chronological order.
- `shadow simulate` runs the same in-process monitor pass first, then produces candidate intents only. It must not call the execution module, create signed orders, or open any private session.
- `shadow report` summarizes stored shadow runs with cumulative `would_copy` / `skip` counts and the latest run details.
- `pm wallet score` and `pm wallet compare` accept any valid public address; `pm wallet rank tracked` is registry-only.
- `summary` aggregates tracked metadata plus holdings value, traded count, open-position count, closed-position count, recent trades, and recent activity from the existing public Data API client.
- `snapshot` is compact and deterministic: registry order, wallet metadata, holdings value, traded count, open-position count, closed-position count, and structured partial errors only.
- Discovery, scoring, compare, `summary`, and `snapshot` use partial-result mode for public sub-call failures; only registry and validation failures should make the whole command exit non-zero.
- `monitor run` and `shadow simulate` also use partial-result mode. Upstream Gamma, CLOB, and Data failures must be captured as structured errors instead of failing the whole command when other rows remain processable.
- Candidate intents from `shadow simulate` must include:
  - source wallet
  - market slug
  - condition ID
  - token ID
  - side and outcome
  - source price
  - current price
  - drift
  - spread
  - simulated size in USDC
  - `WOULD_COPY` or `SKIP`
  - deterministic skip reason when skipped
- Skip rules in the current phase are fixed and explainable:
  - duplicate event
  - inactive or closed market
  - entry-only filtering
  - drift above threshold
  - spread above threshold
  - partial upstream failures such as missing market context, price, spread, or book data
- The deterministic wallet score uses these explicit component weights:
  - `leaderboard_component = 0.25`
  - `realized_performance_component = 0.35`
  - `activity_component = 0.20`
  - `footprint_component = 0.20`
- Legitimate no-data cases count as available zero-score components. Request, transport, or parse failures become structured partial errors and are excluded from the available-weight denominator.
- This namespace is still shadow intelligence only: no auth, no signing, no live copy-trading, no daemon, and no execution logic.

## Human Output Expectations

Human-readable output should stay deterministic and operator-friendly:

- fixed field order for market and event output;
- explicit outcome-to-token mappings when token IDs align with outcomes;
- clear follow-up cues for public CLOB reads;
- stable wording for not-found and hint flows.

`table` refers to the human-readable mode name. It does not require literal grid rendering for every command in this phase.

## Storage and Observability Direction

Later phases may add:

- audit trails for command invocations;
- replay and postmortem workflows;
- structured logging and metrics;
- operational surfaces for health, replay, and incident response.

Those concerns remain part of this spec, but they are out of scope for the current read-only CLI phase.
>>>>>>> feat/02a-python-scaffold
