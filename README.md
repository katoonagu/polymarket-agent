# polymarket-agent

`polymarket-agent` is a docs-first, execution-first workspace for building a modular Polymarket system. The current branch is intentionally read-only: it uses public Gamma, public CLOB, and public Data API reads plus local gitignored state for watchlists and wallet intelligence.

## Principles

- Only the execution module may ever place, replace, or cancel orders.
- Research, market intelligence, and wallet intelligence may produce context, rankings, signals, and candidate intents only.
- Live behavior is never the default.
- Secrets and real credentials must never be committed.
- Every module should keep a matching spec under `docs/specs/`.

## Current Read-Only Surface

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

They are append-only or registry-style JSON documents used for deterministic operator workflows. They are not a database and they do not enable background daemons or live execution.

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

- no wallet auth
- no signing
- no order placement
- no execution engine calls
- no user websocket
- no background daemon
- no database

## Related Specs

- `docs/specs/01-execution-engine.md`
- `docs/specs/02-market-intel.md`
- `docs/specs/03-copytrading-wallet-intel.md`
- `docs/specs/06-cli-ops.md`
