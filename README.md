# polymarket-agent

`polymarket-agent` is a docs-first, execution-first workspace for building a modular Polymarket trading system. The repo is structured to keep execution, intelligence, strategy, and operations separate so research code cannot silently become trading code.

## Principles

- Only the execution module may place, replace, or cancel orders.
- AI, research, and intelligence modules may produce signals, alerts, candidate intents, and context only.
- Default operating modes are `dry-run` and `paper`; live behavior is never the default.
- Every new module must have a matching spec in `docs/specs`.
- Secrets and real credentials must never be committed.

## Module Map

- `execution`
  - Purpose: validated order lifecycle, policy checks, audit events, dry-run and paper abstractions.
  - Spec: `docs/specs/01-execution-engine.md`
- `market`
  - Purpose: market discovery, watchlists, snapshots, recurring market support, and market context.
  - Spec: `docs/specs/02-market-intel.md`
- `wallet`
  - Purpose: tracked-wallet registry, read-only shadow intelligence, and later copy-trading signal generation with strict policy gating.
  - Spec: `docs/specs/03-copytrading-wallet-intel.md`
- `arkham`
  - Purpose: on-chain enrichment, clustering, dossiers, and watchlist-grade intelligence.
  - Spec: `docs/specs/04-arkham-intel.md`
- `strategy`
  - Purpose: strategy definitions, signal evaluation, orchestration, approvals, and conflict resolution.
  - Spec: `docs/specs/05-strategy-orchestrator.md`
- `data`
  - Purpose: normalized read-only Data API access for public user and market analytics.
  - Spec: `docs/specs/06-cli-ops.md`
- `cli` and `ops`
  - Purpose: operator workflows, replay, audit visibility, and operational controls.
  - Spec: `docs/specs/06-cli-ops.md`

## Repository Layout

```text
docs/specs/                      Source-of-truth module and workflow specs
src/pm/
  execution/                     Execution-only order handling boundary
  market/                        Read-only market discovery and monitoring
  data/                          Read-only Data API clients and normalized models
  wallet/                        Wallet intelligence and copy-trade signals
  arkham/                        Arkham intelligence and enrichment
  strategy/                      Strategy and orchestration logic
  cli/                           Operator-facing command surface
  common/                        Shared internal utilities and types
tests/
  unit/                          Fast module-level tests
  integration/                   Cross-module and adapter tests
  replay/                        Deterministic replay and incident tests
fixtures/
  market_snapshots/              Snapshot fixtures for pricing and discovery
  wallet_activity/               Wallet activity fixtures
  replay/                        Replay scenarios and event streams
scripts/                         Development and repo automation scripts
```

## Development Phases

- Bootstrap
  - Establish repo rules, top-level docs, module boundaries, and env hygiene.
- Read-only market discovery
  - Add discovery, watchlists, snapshots, and recurring market support without execution.
- Paper trading
  - Add dry-run and paper execution flow, audit events, and replay-friendly artifacts.
- Wallet intelligence
  - Add wallet registry, activity ingestion, scoring, and shadow copy analysis.
- Arkham intelligence
  - Add enrichment, clustering, dossiers, and watchlist-grade alerts.
- Replay
  - Add deterministic incident reconstruction across signals, intents, execution events, and positions.
- Live readiness
  - Add controls, tests, approval gates, and operational checks required before any live mode discussion.

## Not In This Bootstrap

- No production trading code.
- No live wallet automation.
- No new dependencies.

## Python Bootstrap

This repo now includes a minimal Python 3.11+ scaffold for read-only market discovery over the public Gamma API.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\pm --help
.venv\Scripts\pm market search --query btc --limit 2 --json
.venv\Scripts\pm market show --slug <market-slug> --json
.venv\Scripts\pm market event --slug <event-slug> --json
.venv\Scripts\pm clob book --token-id <token-id> --json
.venv\Scripts\pm clob price --token-id <token-id> --json
.venv\Scripts\pm data trades --user <0x...> --limit 20 --json
.venv\Scripts\pm data closed-positions --user <0x...> --json
.venv\Scripts\pm data holders --market <market-slug-or-condition-id> --limit 20 --json
.venv\Scripts\pm wallet add --address <0x...> --label "desk-1"
.venv\Scripts\pm wallet discover leaderboard --limit 20 --json
.venv\Scripts\pm wallet discover holders --market <market-slug-or-condition-id> --limit 20 --json
.venv\Scripts\pm wallet summary --address <0x...> --json
.venv\Scripts\pm wallet score --address <0x...> --json
.venv\Scripts\pm wallet rank tracked --json
.venv\Scripts\pm wallet compare --address <0x...> --address <0x...> --json
.venv\Scripts\pm wallet snapshot --limit 20 --json
.venv\Scripts\pm wallet monitor run --address <0x...> --limit 20 --json
.venv\Scripts\pm wallet signals --address <0x...> --limit 20 --json
.venv\Scripts\pm wallet shadow simulate --address <0x...> --fixed-size 25 --max-drift 5 --max-spread 5 --entry-only --json
.venv\Scripts\pm wallet shadow report --address <0x...> --json
```

The current CLI is intentionally small. It is read-only, uses only public Gamma, public CLOB, and public Data API endpoints, and does not include wallet auth, order placement, websocket, database, or execution logic.

`pm market book` and `pm market price` remain temporary compatibility aliases for `pm clob book` and `pm clob price`.

`pm data` currently supports `trades`, `activity`, `positions`, `closed-positions`, `holders`, `open-interest`, `value`, and `traded`. For market-scoped reads, `--market` accepts either a market slug or a condition ID and resolves it through the public Gamma adapter before calling the Data API.

`pm wallet` manages a local tracked-wallet registry at `.pm/state/wallets.json`. That file is gitignored, repo-local, and used only for read-only shadow intelligence in this phase. Tracked-wallet summaries and snapshots are built from the existing public Data API client; there is still no auth, signing, polling daemon, or live copy-trading.

`pm wallet discover` is non-mutating. It surfaces candidate wallets from the public trader leaderboard and from public holder data without auto-adding them to the local registry.

`pm wallet score`, `pm wallet rank tracked`, and `pm wallet compare` use a transparent deterministic score built from four weighted components:

- `leaderboard_component` = `0.25`
- `realized_performance_component` = `0.35`
- `activity_component` = `0.20`
- `footprint_component` = `0.20`

Legitimate no-data cases score as available zeroes. Real request or parsing failures are returned as structured partial errors and are excluded from the available-weight denominator.

`pm wallet monitor run` persists deduped public wallet events to `.pm/state/wallet-events.json`, derived signals to `.pm/state/wallet-signals.json`, and `pm wallet shadow simulate` stores shadow-copy runs in `.pm/state/wallet-shadow-runs.json`. Those files are local-only, gitignored, append-only JSON state.

`pm wallet shadow simulate` never calls execution code. It only produces candidate intents with deterministic `WOULD_COPY` or `SKIP` decisions based on market activity, duplicate detection, entry-only mode, drift thresholds, and spread thresholds. `pm wallet shadow report` summarizes those stored runs and their latest partial upstream errors.

## Related Docs

- `docs/specs/README.md`
- `docs/specs/01-execution-engine.md`
- `docs/specs/02-market-intel.md`
- `docs/specs/03-copytrading-wallet-intel.md`
- `docs/specs/04-arkham-intel.md`
- `docs/specs/05-strategy-orchestrator.md`
- `docs/specs/06-cli-ops.md`
- `docs/specs/07-codex-workflow.md`
