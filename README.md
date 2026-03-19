# polymarket-agent

`polymarket-agent` is a docs-first, execution-first workspace for building a modular Polymarket system. The current branch combines a strong public intelligence stack with the first authenticated execution foundation and a guarded strategy-dispatch bridge. It uses public Gamma, public CLOB, public Data API, public streams, local gitignored operator state, authenticated setup and local order-signing, guarded approval and order lifecycle paths, and explicit risk-gated dispatch from approved strategy intents into execution. Live behavior exists only behind explicit operator flags and is never the default.

## Principles

- Only the execution module may ever place, replace, or cancel orders.
- Research, market intelligence, and wallet intelligence may produce context, rankings, signals, and candidate intents only.
- Live behavior is never the default.
- Secrets and real credentials must never be committed.
- Every module should keep a matching spec under `docs/specs/`.

## Current Intelligence Surface

### Market discovery and watchlists

```powershell
.venv\Scripts\pm market search --query btc --limit 2 --json
.venv\Scripts\pm market show --slug <market-slug> --json
.venv\Scripts\pm market event --slug <event-slug> --json
.venv\Scripts\pm market watch add --slug <market-slug> --label "btc desk" --tag btc
.venv\Scripts\pm market watch list --json
.venv\Scripts\pm market watch snapshot --slug <market-slug> --json
.venv\Scripts\pm market watch refresh --json
.venv\Scripts\pm market recurring latest --query "btc" --interval 15m --json
.venv\Scripts\pm market recurring list --query "btc" --interval 15m --limit 5 --json
```

### Public CLOB reads

```powershell
.venv\Scripts\pm clob book --token-id <token-id> --json
.venv\Scripts\pm clob price --token-id <token-id> --json
.venv\Scripts\pm clob midpoint --token-id <token-id> --json
.venv\Scripts\pm clob spread --token-id <token-id> --json
```

`pm market book` and `pm market price` still exist as compatibility aliases, but the canonical public namespace is `pm clob`.

### Public bounded streams

```powershell
.venv\Scripts\pm stream market --token-id <token-id> --seconds 5 --max-events 20 --json
.venv\Scripts\pm stream crypto --symbol BTC --source binance --seconds 5 --max-events 20 --json
.venv\Scripts\pm stream watch --slug <market-slug> --seconds 5 --max-events 20 --json
.venv\Scripts\pm stream recurring --query "btc" --interval 15m --seconds 5 --max-events 20 --json
```

These sessions are always bounded, persist normalized captured events locally, and never open private user streams or call execution code.

### Public Data API reads

```powershell
.venv\Scripts\pm data trades --user <0x...> --limit 20 --json
.venv\Scripts\pm data activity --user <0x...> --limit 20 --json
.venv\Scripts\pm data positions --user <0x...> --json
.venv\Scripts\pm data closed-positions --user <0x...> --json
.venv\Scripts\pm data holders --market <market-slug-or-condition-id> --limit 20 --json
.venv\Scripts\pm data open-interest --market <market-slug-or-condition-id> --json
.venv\Scripts\pm data value --user <0x...> --json
.venv\Scripts\pm data traded --user <0x...> --json
```

### Local tracked-wallet intelligence

```powershell
.venv\Scripts\pm wallet add --address <0x...> --label "desk-1"
.venv\Scripts\pm wallet list --json
.venv\Scripts\pm wallet summary --address <0x...> --json
.venv\Scripts\pm wallet discover leaderboard --limit 20 --json
.venv\Scripts\pm wallet discover holders --market <market-slug-or-condition-id> --limit 20 --json
.venv\Scripts\pm wallet score --address <0x...> --json
.venv\Scripts\pm wallet rank tracked --json
.venv\Scripts\pm wallet compare --address <0x...> --address <0x...> --json
.venv\Scripts\pm wallet monitor run --address <0x...> --limit 20 --json
.venv\Scripts\pm wallet signals --address <0x...> --limit 20 --json
.venv\Scripts\pm wallet shadow simulate --address <0x...> --fixed-size 25 --max-drift 5 --max-spread 5 --entry-only --json
.venv\Scripts\pm wallet shadow report --address <0x...> --json
```

### Strategy registry, review, and guarded dispatch

```powershell
.venv\Scripts\pm risk show --json
.venv\Scripts\pm risk init-defaults --json
.venv\Scripts\pm strategy list --json
.venv\Scripts\pm strategy show --name wallet_shadow_copy --json
.venv\Scripts\pm strategy validate --name wallet_shadow_copy --json
.venv\Scripts\pm strategy evaluate --name wallet_shadow_copy --limit 20 --json
.venv\Scripts\pm strategy intents --limit 20 --json
.venv\Scripts\pm strategy review --intent-id <intent-id> --json
.venv\Scripts\pm strategy approve --intent-id <intent-id> --json
.venv\Scripts\pm strategy reject --intent-id <intent-id> --reason "operator veto" --json
.venv\Scripts\pm strategy dispatch --intent-id <intent-id> --json
.venv\Scripts\pm strategy dispatch --intent-id <intent-id> --live --confirm --json
.venv\Scripts\pm strategy dispatch pending --limit 5 --json
.venv\Scripts\pm strategy executions --limit 20 --json
.venv\Scripts\pm strategy execution get --execution-id <execution-id> --json
```

Strategy evaluation is still read-only and persists candidate intents plus review decisions only. The only bridge into execution is an explicit operator dispatch step after manual approval and risk-policy checks. Execution remains the only module that can actually post or cancel orders.

## Authenticated Execution Foundation

The first authenticated layer now covers non-mutating setup, approval inspection, paper-default order lifecycle planning, explicitly gated live writes, and bounded operator-driven user-channel observation.

```powershell
.venv\Scripts\pm setup doctor --json
.venv\Scripts\pm auth show --json
.venv\Scripts\pm auth derive-api-key --json
.venv\Scripts\pm auth balances --json
.venv\Scripts\pm auth allowances --json
.venv\Scripts\pm approve check --json
.venv\Scripts\pm approve set --asset usdc --json
.venv\Scripts\pm approve set --asset usdc --live --confirm --json
.venv\Scripts\pm exec dry-run --market <market-slug-or-condition-id> --outcome yes --side buy --price 0.55 --size 10 --json
.venv\Scripts\pm exec post --market <market-slug-or-condition-id> --outcome yes --side buy --price 0.55 --size 10 --json
.venv\Scripts\pm exec post --market <market-slug-or-condition-id> --outcome yes --side buy --price 0.55 --size 10 --live --confirm --json
.venv\Scripts\pm exec orders open --json
.venv\Scripts\pm exec order get --order-id <id> --json
.venv\Scripts\pm exec watch --market <condition-id> --seconds 5 --max-events 20 --json
.venv\Scripts\pm exec order wait --order-id <id> --seconds 10 --json
.venv\Scripts\pm exec events --limit 20 --json
.venv\Scripts\pm exec reconcile --json
.venv\Scripts\pm exec cancel --order-id <id> --json
.venv\Scripts\pm exec cancel-all --json
.venv\Scripts\pm exec cancel-market --market <condition-id> [--token-id <asset-id>] --json
```

Rules:

- private auth material comes from environment only
- raw private keys are never printed
- derived L2 API credentials are ephemeral and never persisted locally
- `pm approve set` is preview-only unless `--live --confirm` is present
- `pm exec post`, `pm exec cancel`, `pm exec cancel-all`, and `pm exec cancel-market` are paper-by-default
- real approval writes and real exchange mutations require explicit `--live --confirm`
- geoblock checks run before live approval writes and live order writes
- `pm exec dry-run` still builds and signs locally without posting
- `pm exec watch` and `pm exec order wait` use the authenticated user websocket only in bounded operator-driven sessions
- `pm exec reconcile` compares recent persisted websocket events against authenticated REST order views
- approved strategy intents may hand off only through explicit `pm strategy dispatch` plus risk policy
- strategy and orchestrator flows still do not auto-submit anything

## Output Contract

The root CLI supports:

- `--output table|json`
- `--json` as a convenience alias for JSON mode

Successful JSON responses use normalized snake_case keys. Error responses use a structured envelope:

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

Some commands may include a sibling `hint` object when recovery guidance is useful. For example, `pm market show` will return an event-slug hint if the supplied slug resolves as an event instead of a market.

## Local Gitignored State

This branch uses local file-backed state under `.pm/state/`. These files are repo-local and gitignored:

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

They are append-only or registry-style JSON documents used for deterministic operator workflows. They are not a database and they do not enable background daemons or live execution. This phase does not add any local auth cache, API-key cache, or private-key state file.

## Development

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\pm --help
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check src tests
.venv\Scripts\python -m mypy src
```

## Current Non-Goals

- no replace flow yet
- no public stream daemon
- no background daemon
- no background user-websocket daemon
- no automatic retry loop
- no strategy auto-submit
- no database

## Related Specs

- `docs/specs/01-execution-engine.md`
- `docs/specs/02-market-intel.md`
- `docs/specs/03-copytrading-wallet-intel.md`
- `docs/specs/05-strategy-orchestrator.md`
- `docs/specs/06-cli-ops.md`
