# 06 - CLI, Storage, Observability, and Operations Spec

## Purpose

The CLI is the primary operator surface for this repository. It exists to expose deterministic, auditable workflows while keeping read-only intelligence clearly separate from any later execution module.

In the current phase, the CLI is read-only. It may:

- read public Gamma data
- read public CLOB data
- read bounded public market websocket data
- read bounded public RTDS crypto price data
- read public Data API data
- manage local gitignored watchlists and wallet state

It must not:

- authenticate wallets
- sign transactions
- place or cancel orders
- open private websocket sessions
- start background daemons
- depend on a database

## Global Output Contract

All commands should honor the same root output contract:

```text
pm --output table market search --query "btc"
pm --output json clob book --token-id <id>
pm --json market event --slug <slug>
```

Rules:

- `--output table|json` is the canonical selector.
- `--json` is a convenience alias for JSON mode.
- default output mode is `table`.
- command-local `--json` remains supported and overrides root `--output table`.

### Successful JSON

Successful JSON responses must:

- use normalized snake_case keys
- stay deterministic for tests and automation
- avoid exposing raw upstream wire payloads as the public contract

### Error JSON

When JSON mode is active, errors must use this envelope:

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

Commands may add a sibling `hint` object when recovery guidance is useful.

Canonical error codes in the current phase:

- `not_found`
- `request_failed`
- `invalid_argument`
- `unknown_command`
- `usage_error`
- `already_watched`
- `not_watched`
- `already_tracked`
- `not_tracked`

## Canonical Namespaces

### `pm market`

Public Gamma market discovery, local market watchlists, saved snapshots, and recurring-market resolution.

```text
pm market search --query "<text>" --limit <n> [--json]
pm market show --slug <market-slug> [--json]
pm market event --slug <event-slug> [--json]
pm market watch add --slug <market-slug> [--label <text>] [--tag <text>]
pm market watch remove --slug <market-slug>
pm market watch list [--json]
pm market watch snapshot --slug <market-slug> [--json]
pm market watch refresh [--json]
pm market recurring latest --query <text> --interval <5m|15m|1h> [--json]
pm market recurring list --query <text> --interval <5m|15m|1h> --limit <n> [--json]
```

Operator UX rules:

- `pm market show` should return an event-slug hint if the supplied slug resolves as an event rather than a market.
- market output should make token IDs easy to reuse with `pm clob` commands.
- recurring resolution must stay Gamma-search-based and heuristic, not rely on unsupported recurring APIs.

### `pm clob`

Canonical public CLOB read namespace.

```text
pm clob book --token-id <id> [--json]
pm clob price --token-id <id> [--json]
pm clob midpoint --token-id <id> [--json]
pm clob spread --token-id <id> [--json]
```

Temporary compatibility aliases remain available:

```text
pm market book --token-id <id>
pm market price --token-id <id>
```

They should be treated as deprecated and not used in primary examples.

### `pm data`

Public Data API reads.

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

Validation rules:

- `--user` must be `0x` plus 40 hex characters.
- `--market` may be a market slug or a `0x` plus 64 hex condition ID.

### `pm wallet`

Local tracked-wallet registry and read-only shadow intelligence.

```text
pm wallet add --address <0x...> [--label <text>] [--tag <text>] [--note <text>]
pm wallet list [--json]
pm wallet remove --address <0x...>
pm wallet summary --address <0x...> [--limit <n>] [--json]
pm wallet trades --address <0x...> [--limit <n>] [--json]
pm wallet activity --address <0x...> [--limit <n>] [--json]
pm wallet positions --address <0x...> [--json]
pm wallet snapshot [--limit <n>] [--json]
pm wallet discover leaderboard --limit <n> [--json]
pm wallet discover holders --market <market-slug-or-condition-id> --limit <n> [--json]
pm wallet score --address <0x...> [--json]
pm wallet rank tracked [--json]
pm wallet compare --address <0x...> --address <0x...> [--json]
pm wallet monitor run --address <0x...> [--limit <n>] [--json]
pm wallet signals --address <0x...> [--limit <n>] [--json]
pm wallet shadow simulate --address <0x...> --fixed-size <usdc> --max-drift <pct> --max-spread <pct> [--entry-only] [--limit <n>] [--json]
pm wallet shadow report --address <0x...> [--json]
```

Rules:

- wallet registry and shadow state are local-only and gitignored
- discovery is non-mutating
- monitor and shadow commands never execute trades
- scoring and compare remain deterministic and explainable

### `pm stream`

Bounded read-only public stream sessions for market and crypto context.

```text
pm stream market --token-id <id> --seconds <n> [--max-events <n>] [--json]
pm stream crypto --symbol <symbol> --source <binance|chainlink> --seconds <n> [--max-events <n>] [--json]
pm stream watch --slug <market-slug> --seconds <n> [--max-events <n>] [--json]
pm stream recurring --query <text> --interval <5m|15m|1h> --seconds <n> [--max-events <n>] [--json]
```

Rules:

- every stream command requires `--seconds`
- sessions are bounded and operator-driven, not daemonized
- captured events are normalized and appended to `.pm/state/stream-events.jsonl`
- market stream commands use the public market websocket only
- crypto stream commands use public RTDS feeds only
- `pm stream recurring` reuses the recurring resolver and combines market stream context with Binance RTDS context
- no command opens a private user websocket or calls execution code

## Local Gitignored State

Current file-backed state under `.pm/state/`:

- `wallets.json`
- `wallet-events.json`
- `wallet-signals.json`
- `wallet-shadow-runs.json`
- `market-watchlist.json`
- `market-snapshots.json`
- `stream-events.jsonl`

Rules:

- versioned JSON documents
- atomic writes
- deterministic append order where applicable
- validation failures must surface as explicit state errors

## Partial Error Handling

Some higher-level commands are aggregations over multiple public sub-calls. They should not fail the whole command when a single sub-call fails and other results remain useful.

Current partial-result flows include:

- `pm market watch snapshot`
- `pm market watch refresh`
- `pm wallet summary`
- `pm wallet snapshot`
- `pm wallet discover`
- `pm wallet score`
- `pm wallet compare`
- `pm wallet monitor run`
- `pm wallet shadow simulate`
- `pm wallet shadow report`
- `pm stream recurring`

Structured partial errors should look like:

```json
{
  "section": "open_interest",
  "code": "request_failed",
  "message": "..."
}
```

Full-command failures should remain limited to validation errors, missing tracked or watched objects, local state corruption, or unrecoverable CLI usage errors.

## Operational Direction

Later phases may add:

- replay tooling
- structured audit logs
- richer observability
- incident workflows
- execution-specific operational controls

Those capabilities remain part of the long-term operations surface, but they are outside the current read-only CLI phase.
