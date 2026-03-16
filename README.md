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
  - Purpose: wallet intelligence and copy-trading signal generation with strict policy gating.
  - Spec: `docs/specs/03-copytrading-wallet-intel.md`
- `arkham`
  - Purpose: on-chain enrichment, clustering, dossiers, and watchlist-grade intelligence.
  - Spec: `docs/specs/04-arkham-intel.md`
- `strategy`
  - Purpose: strategy definitions, signal evaluation, orchestration, approvals, and conflict resolution.
  - Spec: `docs/specs/05-strategy-orchestrator.md`
- `cli` and `ops`
  - Purpose: operator workflows, replay, audit visibility, and operational controls.
  - Spec: `docs/specs/06-cli-ops.md`

## Repository Layout

```text
docs/specs/                      Source-of-truth module and workflow specs
src/pm/
  execution/                     Execution-only order handling boundary
  market/                        Read-only market discovery and monitoring
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

## Related Docs

- `docs/specs/README.md`
- `docs/specs/01-execution-engine.md`
- `docs/specs/02-market-intel.md`
- `docs/specs/03-copytrading-wallet-intel.md`
- `docs/specs/04-arkham-intel.md`
- `docs/specs/05-strategy-orchestrator.md`
- `docs/specs/06-cli-ops.md`
- `docs/specs/07-codex-workflow.md`
