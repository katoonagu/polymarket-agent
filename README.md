# polymarket-agent

`polymarket-agent` is a docs-first, execution-first workspace for building a modular Polymarket system. The current branch combines a strong public intelligence stack with guarded authenticated execution, a risk-gated strategy-dispatch bridge, a local-first operator control plane, a bounded one-cycle runbook layer, the first CLI/TUI parity slice, the first interactive CLI UX polish pass, the first Arkham enrichment slice for external wallet intelligence, a portfolio truth plus reconciliation layer, and the first paper/research runtime for a market-specific BTC 15-minute strategy plus a bounded campaign runner, Binance liquidity overlays, and a dense BTC15m current-window operator terminal. It uses public Gamma, public CLOB, public Data API, public streams, public Binance REST market-data overlays, Arkham REST intelligence, local gitignored operator state, authenticated setup and local order-signing, guarded approval and order lifecycle paths, explicit manual dispatch from approved strategy intents into execution, workflow-session tooling for operator review, bounded runbook commands for queueing and dispatch, a bounded interactive shell, an env-only setup wizard, richer Rich-based framed terminal output for the main operator workflows, portfolio snapshots derived from public account state plus local execution linkage, and dedicated BTC15m recorder, replay, liquidity-sample, campaign, dashboard, auto-roll, and terminal-session artifacts for paper research. Live behavior exists only behind explicit operator flags and is never the default.

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

### Arkham enrichment overlay

```powershell
.venv\Scripts\pm arkham status --json
.venv\Scripts\pm arkham enrich --address <0x...> --json
.venv\Scripts\pm arkham dossier --address <0x...> --json
.venv\Scripts\pm arkham sync tracked --limit 20 --json
.venv\Scripts\pm arkham suspicious tracked --limit 20 --json
```

Rules:

- Arkham API keys are env-only: `ARKHAM_API_KEY` is canonical and `PM_ARKHAM_API_KEY` is a supported compatibility alias
- raw Arkham credentials are never printed or persisted locally
- enrichment uses only documented Arkham REST endpoints for address intelligence, enriched address intelligence, entity intelligence, counterparties, and readiness checks
- `pm arkham suspicious tracked` is cache-only and ranks watch candidates from local Arkham enrichments plus local wallet-pipeline context; it does not make implicit network calls
- Arkham output is heuristic operator context only and never triggers execution behavior

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

### BTC15m paper research strategy

```powershell
.venv\Scripts\pm strategy btc15m record start --seconds 60 --json
.venv\Scripts\pm strategy btc15m record window --slug <market-slug> --json
.venv\Scripts\pm strategy btc15m replay --from 2026-03-19T00:00:00Z --to 2026-03-20T00:00:00Z --json
.venv\Scripts\pm strategy btc15m paper-run --limit 20 --json
.venv\Scripts\pm strategy btc15m paper-run --slug <market-slug> --mode paper --json
.venv\Scripts\pm strategy btc15m liquidity sample --seconds 30 --json
.venv\Scripts\pm strategy btc15m campaign next-window --json
.venv\Scripts\pm strategy btc15m campaign next-window --slug <market-slug> --mode paper --json
.venv\Scripts\pm strategy btc15m campaign run --hours 2 --json
.venv\Scripts\pm strategy btc15m campaign run --hours 2 --slug <market-slug> --mode paper --json
.venv\Scripts\pm strategy btc15m campaign report --json
.venv\Scripts\pm strategy btc15m terminal --current --json
.venv\Scripts\pm strategy btc15m terminal --current --mode paper
.venv\Scripts\pm strategy btc15m terminal --current --mode live --confirm
.venv\Scripts\pm strategy btc15m terminal report --json
.venv\Scripts\pm strategy btc15m report --json
```

Rules:

- the runtime implementation name is `btc_15m_chainlink_directional_ladder_v1`
- this surface is paper/research only and stays outside the generic strategy review and dispatch registry in this phase
- `--mode paper` is the default and uses live public market/oracle data with simulated fills and PnL only
- `--mode live` remains reserved on the recorder, replay, campaign, dashboard, and paper-run flows; bounded live execution exists only inside `pm strategy btc15m terminal --current --mode live --confirm`
- `paper-run --slug <market-slug>` is the direct explicit-market paper testing path for one live window
- `campaign next-window --slug <market-slug>` and `campaign run --slug <market-slug>` target that exact market instead of relying on recurring discovery
- `terminal --current` is the dense bounded operator session for the current BTC15m window and reuses slug-first timing as the authoritative source
- `terminal --json` is snapshot-only and exits immediately; it never tries to animate JSON
- `terminal --mode live --confirm` is the only BTC15m live execution surface on this branch and still requires inline per-action confirmation before posting or cancelling any rung
- recorder artifacts persist under `.pm/state/` as dedicated BTC15m boundary, window, replay, liquidity-sample, campaign-run, and paper-run state
- terminal summaries now persist under `.pm/state/btc-15m-chainlink-terminal-sessions.json`, while per-refresh terminal snapshots reuse the BTC15m dashboard snapshot log with `view_kind="terminal"`
- start and end boundaries persist the last Chainlink tick before or at the boundary and the first Chainlink tick at or after the boundary
- `start_price_proxy_v1` and `end_price_proxy_v1` now use the first Chainlink tick at or after the relevant boundary, with bounded grace windows and explainable partial skips when the post-boundary tick is missing
- the minute-5 directional lock uses recorded Chainlink and Binance context against the hardened Chainlink start proxy
- bounded campaigns record exactly one recurring BTC 15m window at a time and stop cleanly when no additional full window fits inside the requested duration
- Binance REST `bookTicker`, `depth`, and closed `1m` kline reads enrich decision-time liquidity and volatility context without adding any authenticated or mutating behavior
- anti-manipulation and thin-liquidity guards may skip paper entries when spread, visible liquidity, or underlying divergence looks poor
- if recurring BTC 15m discovery cannot find a candidate, the BTC15m commands return a structured hint that points operators to `pm market recurring list --query btc --interval 15m` and the explicit `--slug` path
- the paper ladder is buy-only at `0.30`, `0.20`, and `0.10`, with one fill per rung at most
- all non-terminal BTC15m flows remain paper-first; no daemon or unattended auto-roll live loop exists

### Operator control plane

```powershell
.venv\Scripts\pm status --json
.venv\Scripts\pm status --verbose
.venv\Scripts\pm ops queue --limit 20 --json
.venv\Scripts\pm ops bootstrap --json
.venv\Scripts\pm ops session start --label "morning desk" --json
.venv\Scripts\pm ops session end --json
.venv\Scripts\pm ops review next --json
.venv\Scripts\pm ops dispatch approved --limit 5 --json
.venv\Scripts\pm ops cycle queue --limit 5 --json
.venv\Scripts\pm ops cycle approved --limit 5 --json
.venv\Scripts\pm ops cycle approved --limit 5 --live --confirm --json
.venv\Scripts\pm ops cycle report --json
.venv\Scripts\pm ops report --json
.venv\Scripts\pm shell
```

This layer stays local-first and operator-driven. It aggregates pending review work, approved dispatch-ready intents, recent dispatch results, recent execution events, and the latest persisted reconciliation state into a compact workflow surface. Sessions are optional, append-only, and limited to one active session at a time. The bounded runbook commands remain explicit one-cycle actions only: `bootstrap` ensures local risk and session readiness, `cycle queue` evaluates all seeded strategies once, `cycle approved` dispatches only already-approved intents with paper as the default, and `cycle report` stays local-only.

### Portfolio truth and reconciliation

```powershell
.venv\Scripts\pm portfolio summary --json
.venv\Scripts\pm portfolio positions --json
.venv\Scripts\pm portfolio closed --limit 20 --json
.venv\Scripts\pm portfolio market --market <condition-id> --json
.venv\Scripts\pm portfolio exposure --json
.venv\Scripts\pm portfolio pnl --json
.venv\Scripts\pm portfolio reconcile --json
```

Rules:

- portfolio account resolution now uses CLI override, then operator profile, then env-derived auth context
- within each precedence tier, ownership resolves to `funder_address` first, then `signer_address`
- fresh portfolio snapshots come from the public Data API for current positions, closed positions, and holdings value
- gross and net exposure are deterministic; net exposure offsets `YES` vs `NO` within the same `condition_id`
- per-strategy exposure and PnL are tool-local only and are reported only where explicit strategy dispatch or execution linkage exists
- `pm portfolio reconcile` combines fresh portfolio state with a fresh authenticated execution reconciliation pass and writes append-only local records only
- this layer adds no daemon, no scheduler, and no auto-trading behavior

### First CLI/TUI parity slice

```powershell
.venv\Scripts\pm setup guide --json
.venv\Scripts\pm setup wizard
.venv\Scripts\pm status --verbose
.venv\Scripts\pm shell
```

This first parity slice stays intentionally narrow:

- `pm setup guide` is env-only and non-mutating
- `pm setup wizard` is bounded, interactive, and never persists plaintext private keys
- `pm status --verbose` adds richer queue and recent-activity previews without live reads
- `pm shell` is a bounded REPL with quick-menu shortcuts, not a daemon or full-screen TUI
- selected commands now use richer framed human-readable sections while JSON stays normalized
- interactive live confirmations add ergonomics in human mode without weakening `--live --confirm` safety in JSON or non-TTY flows

## Authenticated Execution Foundation

The first authenticated layer now covers non-mutating setup, approval inspection, paper-default order lifecycle planning, explicitly gated live writes, and bounded operator-driven user-channel observation.

```powershell
.venv\Scripts\pm setup doctor --json
.venv\Scripts\pm auth show --json
.venv\Scripts\pm auth profile show --json
.venv\Scripts\pm auth profile init --signature-type 1 --signer <0x...> --funder <0x...> --chain-id 137 --label "desk-a" --json
.venv\Scripts\pm auth profile from-env --json
.venv\Scripts\pm auth profile doctor --json
.venv\Scripts\pm auth profile clear --json
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
- the non-secret operator profile stores signer, funder, signature type, chain id, label, and source only
- operator profile data never stores raw private keys or derived API credentials
- raw private keys are never printed
- derived L2 API credentials are ephemeral and never persisted locally
- non-secret account resolution is deterministic: CLI override > operator profile > env-derived context
- authenticated commands enforce strict signer consistency against the current private key
- `pm approve set` is preview-only unless `--live --confirm` is present
- `pm exec post`, `pm exec cancel`, `pm exec cancel-all`, and `pm exec cancel-market` are paper-by-default
- real approval writes and real exchange mutations require explicit `--live --confirm`
- interactive human mode may prompt for Y/N confirmation when `--live` is supplied without `--confirm`; JSON and non-TTY flows still require explicit `--confirm`
- geoblock checks run before live approval writes and live order writes
- `pm exec dry-run` still builds and signs locally without posting
- `pm exec watch` and `pm exec order wait` use the authenticated user websocket only in bounded operator-driven sessions
- `pm exec reconcile` compares recent persisted websocket events against authenticated REST order views
- approved strategy intents may hand off only through explicit `pm strategy dispatch` plus risk policy
- `pm status` and `pm ops` aggregate local strategy, risk, and execution state without adding a daemon or auto-submit loop
- `pm setup guide` summarizes env requirements, signature/funder expectations, geoblock, balances, and allowances without writing config
- `pm setup wizard` may accept a hidden session-only private key for one wizard run, but it never persists plaintext secrets
- `pm shell` is a bounded operator shell over existing command workflows only
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
- `arkham-enrichments.json`
- `operator-profile.json`
- `strategies.json`
- `strategy-intents.json`
- `strategy-decisions.json`
- `risk-policies.json`
- `strategy-execution-links.json`
- `strategy-dispatch-results.json`
- `btc-15m-chainlink-boundary-observations.jsonl`
- `btc-15m-chainlink-boundary-decisions.json`
- `btc-15m-chainlink-windows.jsonl`
- `btc-15m-chainlink-replays.json`
- `btc-15m-chainlink-paper-runs.json`
- `btc-15m-chainlink-liquidity-samples.jsonl`
- `btc-15m-chainlink-campaign-runs.json`
- `ops-sessions.json`
- `approval-plans.json`
- `approval-results.json`
- `execution-order-plans.json`
- `execution-order-results.json`
- `execution-events.jsonl`
- `execution-reconciliations.json`
- `portfolio-snapshots.json`
- `portfolio-reconciliations.json`

They are append-only or registry-style JSON documents used for deterministic operator workflows. They are not a database and they do not enable background daemons or live execution. This phase does not add any local auth cache, API-key cache, or private-key state file.

The bounded runbook slice does not add a new state file. It reuses the existing risk, ops-session, strategy-dispatch, execution-event, and reconciliation artifacts.

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
- no background scheduler
- no full-screen daemon UI
- no infinite loop
- no automatic retry loop
- no strategy auto-submit
- no auto-dispatch loop
- no database

## Intentional Differences From Official CLI

- Secrets stay env-only by default; this branch does not create or import plaintext wallet config.
- `pm setup wizard` may use a hidden session-only private key during one wizard run, but it still does not persist plaintext secret material.
- JSON responses use normalized contracts instead of mirroring raw upstream payloads.
- Paper/default mode and explicit `--live --confirm` gates remain the only path to live writes.
- `pm shell` is a bounded REPL, not a daemonized or full-screen terminal UI.
- Intelligence, strategy, ops, and execution remain separate surfaces; only execution may place or cancel orders.

## Related Specs

- `docs/specs/01-execution-engine.md`
- `docs/specs/02-market-intel.md`
- `docs/specs/03-copytrading-wallet-intel.md`
- `docs/specs/05-strategy-orchestrator.md`
- `docs/specs/06-cli-ops.md`
- `docs/specs/08-portfolio-ledger.md`
