# 06 - CLI, Storage, Observability & Operations Spec

## Purpose

The CLI is the first operator surface for this repository. It exists to expose deterministic, auditable workflows while keeping research, market intelligence, and execution boundaries explicit.

For the current phase, the CLI is read-only. It may read public Gamma and public CLOB data, but it must not authenticate, place orders, cancel orders, manage wallets, or persist state in a database.

## Current Read-Only CLI Contract

### Canonical namespaces

- `pm market`
  - Public Gamma market discovery
  - Search, market lookup, and event lookup
- `pm clob`
  - Public CLOB order book and price reads
  - Book, price, midpoint, and spread

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

```text
pm clob book --token-id <id> [--json]
pm clob price --token-id <id> [--json]
pm clob midpoint --token-id <id> [--json]
pm clob spread --token-id <id> [--json]
```

These commands are public and read-only. They must not depend on auth, private keys, trading SDKs, or websocket sessions.

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
