# 06 - CLI, Storage, Observability, and Operations Spec

## Purpose

The CLI is the primary operator surface for this repository. It exists to expose deterministic, auditable workflows while keeping intelligence clearly separate from execution submission.

In the current phase, the CLI supports public intelligence plus authenticated paper-default execution and guarded live writes. It may:

- read public Gamma data
- read public CLOB data
- read bounded public market websocket data
- read bounded public RTDS crypto price data
- read public Data API data
- manage local gitignored watchlists and wallet state
- inspect authenticated balances and allowances
- derive ephemeral API credentials
- inspect and preview approval writes
- build and sign dry-run orders locally without submission
- preview paper-mode order posting and cancellation
- open bounded authenticated execution-watch sessions
- reconcile recent execution websocket events against authenticated REST order views
- bridge approved strategy intents into execution through explicit risk-gated dispatch
- submit or cancel live orders only behind explicit operator gates

It must not:

- open unbounded or background private websocket sessions
- start background daemons
- replace orders yet
- auto-submit from strategy or orchestration
- auto-dispatch from strategy or orchestration
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

### `pm setup`

Authenticated non-mutating readiness checks.

```text
pm setup doctor [--json]
```

Rules:

- `pm setup doctor` is the only implemented setup command in the current phase
- it must remain non-mutating
- it must not derive API credentials, post orders, or write approvals
- broader guided setup UX remains a future parity target

### `pm auth`

Authenticated setup and account inspection commands.

```text
pm auth show [--json]
pm auth derive-api-key [--json]
pm auth balances [--json]
pm auth allowances [--json]
```

Rules:

- private key material comes from environment only
- raw private keys must never be printed
- derived API credentials are ephemeral and are never persisted locally
- balances and allowances are read-only inspection commands

### `pm approve`

Guarded approval inspection and mutation commands.

```text
pm approve check [--json]
pm approve set --asset <usdc|ctf> [--live] [--confirm] [--json]
```

Rules:

- `check` is an authenticated live read
- `set` is preview-only by default
- real approval writes require both `--live` and `--confirm`
- geoblock must be checked before live approval writes
- raw private keys must never be printed
- approval plans and live approval results are persisted locally for audit

### `pm risk`

Guarded strategy-dispatch policy commands.

```text
pm risk show [--json]
pm risk init-defaults [--json]
```

Rules:

- `show` returns the effective policy set
- when the policy file does not exist yet, `show` returns built-in defaults with `persisted=false`
- `init-defaults` is idempotent and creates the versioned file only when missing
- dispatch policies remain local, deterministic, and gitignored

### `pm exec`

Authenticated execution planning and order lifecycle commands.

```text
pm exec dry-run --market <market-slug-or-condition-id> --outcome <yes|no> --side <buy|sell> --price <p> --size <n> [--json]
pm exec post --market <market-slug-or-condition-id> --outcome <yes|no> --side <buy|sell> --price <p> --size <n> [--order-type <gtc|gtd|fok>] [--expires-at <iso8601>] [--post-only] [--paper] [--live] [--confirm] [--json]
pm exec orders open [--market <condition_id>] [--token-id <asset_id>] [--json]
pm exec order get --order-id <id> [--json]
pm exec watch [--market <condition_id>] [--seconds <n>] [--max-events <n>] [--json]
pm exec order wait --order-id <id> --seconds <n> [--json]
pm exec events [--limit <n>] [--json]
pm exec reconcile [--json]
pm exec cancel --order-id <id> [--paper] [--live] [--confirm] [--json]
pm exec cancel-all [--paper] [--live] [--confirm] [--json]
pm exec cancel-market --market <condition_id> [--token-id <asset_id>] [--paper] [--live] [--confirm] [--json]
```

Rules:

- `dry-run` may build and sign an order locally
- `dry-run` must never post the signed order
- `dry-run` returns `WOULD_POST` or `SKIP` plus reason blocks
- `post`, `cancel`, `cancel-all`, and `cancel-market` are paper-by-default
- live order submission and live cancellations require both `--live` and `--confirm`
- `orders open` and `order get` are authenticated live reads
- `watch` and `order wait` use the authenticated user websocket only in bounded sessions
- `events` reads local persisted execution events only
- `reconcile` compares the latest persisted execution events with authenticated REST order views
- `gtd` requires `--expires-at`
- `--post-only` is valid only for `gtc` and `gtd`
- local execution audit records are persisted for preview, paper, and live lifecycle actions

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
- `pm stream` never opens the authenticated private user websocket or calls execution code

### `pm strategy`

Seeded strategy registry, local manual review orchestration, and guarded manual dispatch.

```text
pm strategy list [--json]
pm strategy show --name <name> [--json]
pm strategy validate --name <name> [--json]
pm strategy evaluate --name <name> [--limit <n>] [--json]
pm strategy intents [--limit <n>] [--json]
pm strategy review --intent-id <id> [--json]
pm strategy approve --intent-id <id> [--json]
pm strategy reject --intent-id <id> --reason <text> [--json]
pm strategy dispatch --intent-id <id> [--paper] [--live] [--confirm] [--json]
pm strategy dispatch pending [--limit <n>] [--paper] [--json]
pm strategy executions [--limit <n>] [--json]
pm strategy execution get --execution-id <id> [--json]
```

Rules:

- strategy definitions are seeded locally and deterministic
- evaluation produces candidate intents only
- `APPROVE` is manual only and recorded locally
- `approve` and `reject` do not call execution code by themselves
- dispatch is a separate explicit operator action after approval
- only approved intents may dispatch
- paper mode is the default for dispatch
- live dispatch requires both `--live` and `--confirm`
- `dispatch pending` is paper-only in this phase
- v1 dispatch is intentionally wallet-first; only `wallet_shadow_copy` is dispatch-enabled by default
- execution remains the only module allowed to place or cancel orders
- strategy state is file-backed, append-only where appropriate, and gitignored

## Local Gitignored State

Current file-backed state under `.pm/state/`:

- `wallets.json`
- `wallet-events.json`
- `wallet-signals.json`
- `wallet-shadow-runs.json`
- `market-watchlist.json`
- `market-snapshots.json`
- `stream-events.jsonl`
- `strategies.json`
- `strategy-intents.json`
- `strategy-decisions.json`
- `risk-policies.json`
- `strategy-execution-links.json`
- `strategy-dispatch-results.json`
- `approval-plans.json`
- `approval-results.json`
- `execution-order-plans.json`
- `execution-order-results.json`
- `execution-events.jsonl`
- `execution-reconciliations.json`

Rules:

- versioned JSON documents
- atomic writes
- deterministic append order where applicable
- validation failures must surface as explicit state errors
- the current execution phase adds no local auth cache or API-key cache

## Partial Error Handling

Some higher-level commands are aggregations over multiple public sub-calls. They should not fail the whole command when a single sub-call fails and other results remain useful.

Current partial-result flows include:

- `pm exec watch`
- `pm exec order wait`
- `pm exec reconcile`
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
- `pm strategy evaluate`
- `pm strategy review`
- `pm strategy dispatch`
- `pm strategy dispatch pending`

Structured partial errors should look like:

```json
{
  "section": "open_interest",
  "code": "request_failed",
  "message": "..."
}
```

Full-command failures should remain limited to validation errors, missing tracked or watched objects, local state corruption, or unrecoverable CLI usage errors.

## Future CLI/TUI Parity Surface

The current branch already includes `pm setup doctor`, `pm approve check`, and `pm approve set`. The following broader parity targets remain future and are not implemented yet:

- `pm setup`
- `pm wallet create`
- `pm wallet import`
- `pm wallet show`
- `pm shell`
- `pm status`

Intended direction:

- `pm setup`: guided onboarding over future local config, wallet readiness, and approval checks
- `pm wallet create`, `pm wallet import`, `pm wallet show`: future execution-adjacent wallet configuration UX
- `pm shell`: future interactive operator shell over existing and later command surfaces
- `pm status`: future high-level operator health and readiness summary

Guardrails:

- these are documentation targets only on the current branch
- they must not imply current wallet-create behavior or broader live execution behavior beyond the explicitly implemented guarded commands
- existing read-only commands must remain usable without any wallet setup
- intelligence modules remain separate from execution modules
- execution remains the only module allowed to place or cancel orders

Richer human-readable tables are also a future parity direction across the CLI, while JSON remains normalized and machine-friendly.

## Operational Direction

Later phases may add:

- replay tooling
- structured audit logs
- richer observability
- incident workflows
- execution-specific operational controls

Those capabilities remain part of the long-term operations surface, but they are outside the current guarded manual-dispatch phase.
