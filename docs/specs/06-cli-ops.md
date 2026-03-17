# 06 - CLI, Storage, Observability & Operations Spec

## Purpose

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

```text
pm risk exposure
pm risk exposure --by strategy
pm risk exposure --by wallet
pm risk limits show
pm risk limits set --market-cap 25
pm risk kill-switch on
pm risk kill-switch off
pm risk daily-stop show
```

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
