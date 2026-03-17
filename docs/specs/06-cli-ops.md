# 06 - CLI, Storage, Observability, and Operations Spec

## Purpose

The CLI is the primary operator interface for this repository. That remains the correct starting point for v1 because it is:

- fast to build and audit
- easier to constrain than a web control plane
- compatible with deterministic replay and operator runbooks
- a clean foundation for future TUI or web surfaces

This spec defines the command contract, output contract, and operational expectations for CLI-led workflows.

## CLI Design Principles

### 1. Execution Boundary Is Visible

Read-only commands must stay read-only. Discovery, intelligence, and analysis surfaces must not place, replace, or cancel orders.

Only the execution module may own mutating trading commands.

### 2. Default Operator Experience Is Safe

Where a command can become execution-adjacent later, the default mode must remain safe and explicit. Dry-run and paper modes remain the default posture for any future execution-facing surface.

### 3. Human Output And Machine Output Are Both First-Class

Every operator-facing command should support:

- table output for interactive use
- JSON output for automation, tests, and scripting

### 4. Public Contracts Must Be Normalized

The CLI must not expose raw Gamma or CLOB payloads as the long-term user-facing contract. Public output should be normalized, stable, and snake_case for JSON.

### 5. Auditability Matters More Than Convenience

CLI workflows should make it easy to explain what was requested, what data source was consulted, what happened, and whether any side effects occurred.

## Global Output Contract

The canonical CLI output contract is:

```text
--output table|json
```

Rules:

- `table` is the default output mode.
- `json` is the machine-readable mode.
- `--json` is a compatibility alias for `--output json`.
- JSON output must be deterministic so tests and automation can rely on it.
- Successful JSON responses are command-specific normalized payloads, not raw upstream response bodies.

## Structured JSON Error Contract

When a command fails in JSON mode, the canonical error envelope is:

```json
{
  "ok": false,
  "error": {
    "code": "not_found",
    "message": "Market not found for slug 'example-market'.",
    "resource": "market",
    "identifier": "example-market"
  }
}
```

Rules:

- `code` is a short stable machine-readable error code.
- `message` is the operator-readable explanation.
- `resource` identifies the logical resource type such as `market`, `event`, `book`, or `price`.
- `identifier` is the slug, token ID, or other lookup value supplied by the user.
- Human-readable mode may render a concise text error, but JSON mode must use the structured envelope.

## Canonical Namespaces

### `pm market`

Canonical namespace for Gamma-backed public market discovery and event lookup.

Primary public read commands:

```text
pm market search --query <text>
pm market show --slug <slug>
pm market event --slug <slug>
```

### `pm clob`

Canonical namespace for public CLOB reads that work from market-discovered token IDs.

Primary public read commands:

```text
pm clob book --token-id <id>
pm clob price --token-id <id>
```

### Future Namespaces

These remain part of the long-term operator model, but are not part of the current read-only implementation phase:

- `pm wallet`
- `pm arkham`
- `pm strategy`
- `pm exec`
- `pm risk`
- `pm ops`

## Compatibility Aliases

The current branch still exposes:

```text
pm market book --token-id <id>
pm market price --token-id <id>
```

These are temporary backward-compatible aliases only.

Rules:

- They should be documented as deprecated compatibility commands.
- They should use the same normalized output contract as the canonical `pm clob` commands.
- New docs and examples should prefer `pm clob book` and `pm clob price`.
- They should be removed only after the canonical `pm clob` surface is implemented and stable.

## Example Public Read Command Set

```text
pm market search --query "btc 15 min"
pm market show --slug <slug>
pm market event --slug <slug>
pm clob book --token-id <id>
pm clob price --token-id <id>
```

## Storage Requirements

### Core Database

Postgres is the preferred primary system of record once persistence is added.

### Cache And Queue

Redis is the preferred cache and transient coordination layer for:

- recent snapshots
- transient locks
- idempotency windows
- work queues

### Event Log

The system should maintain append-only event history for:

- signals
- approvals
- trade intents
- execution events
- fills
- reconciliations
- alerts

## Suggested Database Model

### Core Tables

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

### Optional Later Tables

- `clusters`
- `entities`
- `news_briefs`
- `semantic_relationships`

## Observability

### Structured Logging

Minimum log fields:

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

## Replay And Postmortem

Replay is a required operational mode. Operators must be able to:

- reconstruct system state at a given timestamp
- inspect which signals arrived
- inspect which checks passed or failed
- inspect which intent or order was created
- inspect resulting fills or position changes
- explain why a position remained open, closed, or was skipped

### Replay Storage Requirements

To support replay, the system must retain:

- market snapshots
- signal history
- candidate intents
- approvals
- execution events
- final position state

## Risk Console In CLI

Illustrative future command set:

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

### Incident Types

- duplicate execution
- stale data execution
- missed cancel
- overexposure
- wallet misclassification
- replay mismatch
- rate-limit degradation
- websocket data gap

### Incident Workflow

1. detect
2. freeze or scope-limit
3. reconcile
4. produce a postmortem
5. patch the rule or spec
6. replay the affected window

## MVP Definition

CLI and operations readiness for the broader system is achieved when:

1. the critical operator workflows are available from the CLI
2. JSON output mode is stable and documented
3. audit trails exist for important actions
4. a risk console exists
5. replay is available
6. kill switch behavior works globally and at the strategy level
7. operators can explain failures after an incident

## Phase 2 Expansion

- TUI dashboard
- web control panel
- role-based access
- scheduled jobs UI
- alert routing in Slack, Telegram, or Discord
