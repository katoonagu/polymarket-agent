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
- aggregate local strategy, risk, and execution state into a compact operator control plane
- expose portfolio truth, exposure, PnL, and reconciliation views from public account data plus local execution linkage
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

### `pm status`

Local-first operator summary command.

```text
pm status [--verbose] [--json]
```

Rules:

- `status` is local-first and does not perform authenticated live reads in this phase
- it summarizes active session state, pending review work, dispatch-ready work, recent dispatches, recent execution events, and risk-policy persistence
- `--verbose` adds a queue preview plus recent strategy-execution and execution-event previews
- it remains an operator workflow surface, not a daemon or live control loop

### `pm setup`

Authenticated non-mutating readiness checks.

```text
pm setup doctor [--json]
pm setup guide [--json]
pm setup wizard [--json]
```

Rules:

- `pm setup doctor`, `pm setup guide`, and `pm setup wizard` are the implemented setup commands in the current phase
- it must remain non-mutating
- it must not derive API credentials, post orders, or write approvals
- `pm setup guide` is also non-mutating and env-only
- `pm setup wizard` is bounded and interactive in human mode, but non-interactive in JSON mode
- `pm setup guide` summarizes required env vars, signature and funder expectations, geoblock status, and balance or allowance checkpoints
- `pm setup wizard` may accept a hidden session-only private key for one wizard run only
- no setup command may print raw private keys or create plaintext wallet config by default

### `pm shell`

Bounded interactive operator shell.

```text
pm shell
```

Rules:

- `pm shell` is a bounded REPL over existing commands, not a daemon or full-screen TUI
- it executes one command at a time and returns to the prompt
- it supports a small alias set for common workflows plus direct passthrough commands without the `pm` prefix
- it also supports a quick menu, numeric shortcuts, and `menu` / `back` pseudo-commands for common workflows
- it exits on `exit`, `quit`, EOF, or interrupt
- it does not add background jobs, polling, saved history, or hidden execution behavior

### `pm auth`

Authenticated setup and account inspection commands.

```text
pm auth show [--json]
pm auth profile show [--json]
pm auth profile init --signature-type <0|1|2> --signer <0x...> --funder <0x...> [--chain-id <n>] [--label <text>] [--json]
pm auth profile from-env [--json]
pm auth profile doctor [--json]
pm auth profile clear [--json]
pm auth derive-api-key [--json]
pm auth balances [--json]
pm auth allowances [--json]
```

Rules:

- private key material comes from environment only
- the local operator profile stores non-secret identity fields only
- non-secret resolution precedence is CLI override, then operator profile, then env-derived context
- authenticated commands must reject signer mismatches against the current private key
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
- in interactive human mode, `--live` without `--confirm` may trigger a Y/N confirmation prompt; JSON and non-TTY flows still require explicit `--confirm`
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

### `pm arkham`

Arkham-backed external wallet intelligence enrichment.

```text
pm arkham status [--json]
pm arkham enrich --address <0x...> [--json]
pm arkham dossier --address <0x...> [--json]
pm arkham sync tracked [--limit <n>] [--json]
pm arkham suspicious tracked [--limit <n>] [--json]
```

Rules:

- Arkham secrets are env-only
- `ARKHAM_API_KEY` is canonical and `PM_ARKHAM_API_KEY` is a supported compatibility alias
- missing Arkham credentials should return a readiness or help payload instead of crashing the command
- enrichment uses documented Arkham REST endpoints only
- local enrichment state is cache-style and gitignored
- `suspicious tracked` is cache-only and must not make implicit Arkham network calls
- Arkham outputs are heuristic watch flags and dossier context only; they must not auto-dispatch or auto-execute anything

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
- authenticated execution commands may also accept non-secret account overrides for signer, funder, signature type, and chain id
- `post`, `cancel`, `cancel-all`, and `cancel-market` are paper-by-default
- live order submission and live cancellations require both `--live` and `--confirm`
- in interactive human mode, `--live` without `--confirm` may trigger a Y/N confirmation prompt; JSON and non-TTY flows still require explicit `--confirm`
- `orders open` and `order get` are authenticated live reads
- `watch` and `order wait` use the authenticated user websocket only in bounded sessions
- `events` reads local persisted execution events only
- `reconcile` compares the latest persisted execution events with authenticated REST order views
- `gtd` requires `--expires-at`
- `--post-only` is valid only for `gtc` and `gtd`
- local execution audit records are persisted for preview, paper, and live lifecycle actions

### `pm portfolio`

Portfolio truth and reconciliation commands.

```text
pm portfolio summary [--json]
pm portfolio positions [--json]
pm portfolio closed [--limit <n>] [--json]
pm portfolio market --market <condition_id> [--json]
pm portfolio exposure [--json]
pm portfolio pnl [--json]
pm portfolio reconcile [--json]
```

Rules:

- portfolio commands accept explicit non-secret account overrides through `--signer` and `--funder`
- account resolution precedence is CLI override, then operator profile, then env-derived context
- within each precedence tier, ownership resolves to `funder_address` first, then `signer_address`
- fresh portfolio snapshots come from the public Data API for current positions, closed positions, and holdings value
- `market` filters locally by `condition_id`
- gross and net exposure stay deterministic; net exposure offsets `YES` vs `NO` within the same market
- per-strategy exposure and PnL are tool-local only and require explicit strategy-dispatch or execution linkage
- `reconcile` runs a fresh authenticated execution reconciliation pass, compares it with current portfolio state, and writes local append-only reconciliation records only
- portfolio commands remain operator-driven and add no daemon, scheduler, or auto-trading loop

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
- in interactive human mode, `--live` without `--confirm` may trigger a Y/N confirmation prompt; JSON and non-TTY flows still require explicit `--confirm`
- `dispatch pending` is paper-only in this phase
- v1 dispatch is intentionally wallet-first; only `wallet_shadow_copy` is dispatch-enabled by default
- execution remains the only module allowed to place or cancel orders
- strategy state is file-backed, append-only where appropriate, and gitignored

### `pm ops`

Local-first operator workflow and session commands.

```text
pm ops bootstrap [--json]
pm ops queue [--limit <n>] [--json]
pm ops session start [--label <text>] [--json]
pm ops session end [--json]
pm ops review next [--json]
pm ops dispatch approved [--limit <n>] [--paper] [--json]
pm ops cycle queue [--limit <n>] [--json]
pm ops cycle approved [--limit <n>] [--paper] [--live] [--confirm] [--json]
pm ops cycle report [--json]
pm ops report [--json]
```

Rules:

- `bootstrap` is a local idempotent readiness initializer
- `bootstrap` initializes default risk policies when missing and ensures one active ops session exists
- `queue` combines review work and dispatch-ready work into one deterministic list
- review ordering is unreviewed `WAIT` first, then unreviewed `OBSERVE`, both newest-first
- dispatch-ready ordering follows the guarded strategy dispatch rules and stays paper-first
- `review next` returns the next reviewable item or `queue_empty=true`
- `dispatch approved` is paper-only in this phase and delegates to the existing guarded strategy dispatch bridge
- `cycle queue` evaluates all seeded strategies once in deterministic registry order
- `cycle queue --limit` is the per-strategy evaluation limit, not a cap on the number of strategies
- `cycle approved` is a bounded manual dispatch batch over already approved and dispatch-eligible intents
- `cycle approved` is paper-default and requires both `--live` and `--confirm` for live dispatch
- in interactive human mode, `--live` without `--confirm` may trigger a Y/N confirmation prompt; JSON and non-TTY flows still require explicit `--confirm`
- `cycle report` is local-only and summarizes persisted queue, dispatch, event, and reconciliation state without triggering a fresh reconcile call
- sessions are optional but, when used, allow only one active session at a time
- `report` prefers the active session scope, then the latest completed session, then a global local snapshot
- `ops` is an operator UX layer only; it does not add a daemon, scheduler, or new execution path

## Human Output Direction

The current branch now uses stronger Rich-based framed panels and tables for key operator commands:

- `pm status`
- `pm ops queue`
- `pm ops cycle report`
- `pm strategy intents`
- `pm strategy executions`
- `pm exec events`
- `pm arkham status`
- `pm arkham dossier`
- `pm arkham suspicious tracked`
- `pm setup guide`
- `pm setup wizard`
- `pm shell`

Rules:

- JSON remains the canonical machine-facing contract
- richer human output must not change JSON shapes
- table output may shorten long ids for readability, but JSON must continue to return full values
- root help, setup flows, and shell now use an operator-style banner treatment
- `pm status --verbose` is the showcase surface for grouped summary, queue, and recent-activity framing

## Local Gitignored State

Current file-backed state under `.pm/state/`:

- `wallets.json`
- `wallet-events.json`
- `wallet-signals.json`
- `wallet-shadow-runs.json`
- `market-watchlist.json`
- `market-snapshots.json`
- `stream-events.jsonl`
- `arkham-enrichments.json`
- `strategies.json`
- `strategy-intents.json`
- `strategy-decisions.json`
- `risk-policies.json`
- `strategy-execution-links.json`
- `strategy-dispatch-results.json`
- `ops-sessions.json`
- `approval-plans.json`
- `approval-results.json`
- `execution-order-plans.json`
- `execution-order-results.json`
- `execution-events.jsonl`
- `execution-reconciliations.json`
- `portfolio-snapshots.json`
- `portfolio-reconciliations.json`

Rules:

- versioned JSON documents
- atomic writes
- deterministic append order where applicable
- validation failures must surface as explicit state errors
- the current execution phase adds no local auth cache or API-key cache
- the bounded runbook slice reuses existing risk, session, strategy, dispatch, event, and reconciliation files instead of adding a scheduler-specific state file

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
- `pm ops cycle queue`
- `pm arkham enrich`
- `pm arkham dossier`
- `pm arkham sync tracked`

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

The current branch already includes `pm setup doctor`, `pm setup guide`, `pm setup wizard`, `pm approve check`, `pm approve set`, `pm status`, and `pm shell`. The following broader parity targets remain future and are not implemented yet:

- `pm wallet create`
- `pm wallet import`
- `pm wallet show`
- fuller TUI-style operator workflows beyond the bounded shell

One strategy-specific exception now exists on the current branch:

- `pm strategy btc15m terminal --follow-current`
- `pm strategy btc15m terminal --current`
- `pm strategy btc15m terminal --follow-current --observe-only`
- `pm strategy btc15m terminal --wait-next`
- `pm strategy btc15m terminal replay --session-id <id>`
- `pm strategy btc15m terminal report [--session-id <id>]`

This BTC15m surface is a current-window-first attached operator screen with
page-parity-first live metrics, automatic rollover across BTC15m slugs while
the operator stays attached, and an explicit bounded `--wait-next` mode for
arming exactly one next window. It is not a generic daemonized shell
replacement.

Intended direction:

- broader `pm setup`: guided onboarding over future local config, wallet readiness, and approval checks
- `pm wallet create`, `pm wallet import`, `pm wallet show`: future execution-adjacent wallet configuration UX
- broader shell and TUI work: future interactive operator experience over existing and later command surfaces

Guardrails:

- these are documentation targets only on the current branch
- they must not imply current wallet-create behavior or broader live execution behavior beyond the explicitly implemented guarded commands
- existing read-only commands must remain usable without any wallet setup
- intelligence modules remain separate from execution modules
- execution remains the only module allowed to place or cancel orders

Richer human-readable tables are now implemented for selected operator commands and remain a broader parity direction across the rest of the CLI while JSON stays normalized and machine-friendly.

## Intentional Differences From Official CLI

- secrets remain env-only by default instead of plaintext wallet or private-key config
- JSON output stays normalized and stable instead of exposing raw upstream payloads as the public contract
- live order and approval writes remain explicitly gated behind `--live --confirm`
- `pm shell` is bounded and operator-invoked, not a daemonized or full-screen terminal process
- `pm strategy btc15m terminal --follow-current` is a strategy-specific
  operator terminal, not a generic unattended TUI loop
- live data stays on in both BTC15m `paper` and `live`; execution behavior is
  the only mode difference
- late attach on `pm strategy btc15m terminal --follow-current` may degrade
  into observe-only rather than failing the attached session immediately
- `pm strategy btc15m terminal --wait-next` remains bounded to exactly one next
  armed BTC15m window; it is not an auto-roll daemon
- the BTC15m terminal now prioritizes the active Polymarket market display and
  keeps operator display truth separate from internal strategy state
- displayed BTC, price-to-beat, and Up/Down page values are slug-first and
  provenance-aware: `page_exact` requires structured public page state,
  `page_estimated` covers bounded page-text fallback, `clob_emulated` covers
  public CLOB display emulation, and `page_unavailable` is preferred over
  misleading reused prices; strategy start proxies are never reused as display
  values
- Binance remains a compact secondary diagnostics panel and may collapse when
  Polymarket page-truth display is healthy
- intelligence, strategy, ops, and execution remain separate modules; execution alone may place or cancel orders

## Operational Direction

Later phases may add:

- replay tooling
- structured audit logs
- richer observability
- incident workflows
- execution-specific operational controls

Those capabilities remain part of the long-term operations surface, but they are outside the current guarded manual-dispatch phase.
