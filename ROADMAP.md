# ROADMAP

This roadmap defines delivery phases for the bootstrap and early evolution of `polymarket-agent`. Each phase is outcome-based, keeps execution isolated from intelligence modules, and avoids committing to timelines or dependency choices before the architecture is proven.

## Phase 1: Bootstrap

**Objective**

Create a coherent repo contract so future work starts from explicit module boundaries and safe defaults.

**Scope / Deliverables**

- Top-level repo docs: `README.md`, `ROADMAP.md`, `AGENTS.md`
- Spec-to-module mapping across `docs/specs` and `src/pm`
- Environment hygiene based on `.env.example` and `.gitignore`
- Clear statement that dry-run and paper are the default operating modes

**Non-goals**

- Production trading code
- Live trading flows
- New runtime dependencies

**Exit Criteria**

- Repo entry docs are complete and internally consistent
- Execution-only order placement rule is explicit
- Secret handling rules are documented
- Each current module area points to a matching spec

## Phase 2: Read-Only Market Discovery

**Objective**

Build reliable market discovery and monitoring without creating any order-placement path.

**Scope / Deliverables**

- Market search by slug, id, or query
- Watchlist management
- Market metadata normalization
- Snapshot capture for bid, ask, spread, and freshness
- Recurring market support for time-bucketed markets

### Part 02B: Official CLI Alignment

**Objective**

Align the documented read-only CLI surface with the most useful command and output patterns from the official Polymarket CLI while preserving this repo's Python-native architecture and execution boundaries.

**Scope / Deliverables**

- Upstream research note in `docs/research/polymarket-cli-analysis.md`
- Canonical public namespace split between `pm market` and `pm clob`
- Global CLI output contract and structured JSON error contract in the CLI spec
- Alias and deprecation policy for `pm market book` and `pm market price`
- README and spec examples aligned to the canonical read-only command surface

**Non-goals**

- Code changes to current command implementations
- Adopting the Rust CLI architecture as the repo architecture
- Adding auth, wallet, approval, bridge, CTF, or other mutating CLI flows

**Exit Criteria**

- Upstream reference note is published and linked from the repo docs
- The CLI spec defines canonical namespaces and output and error behavior
- README examples reflect the canonical read-only command surface
- Temporary aliases are documented as compatibility-only, not permanent API

**Non-goals**

- Order placement or cancellation
- Strategy-driven auto-trading
- Live wallet following

**Exit Criteria**

- Operator can discover and inspect markets from CLI or internal interfaces
- The canonical read-only CLI contract is documented for both market discovery and public CLOB reads
- Watched markets can produce normalized snapshots
- Recurring market resolution is deterministic for the first supported series
- No read-only component contains direct execution logic

## Phase 3: Paper Trading

**Objective**

Introduce execution-shaped workflows in `dry-run` and `paper` modes only.

**Scope / Deliverables**

- Trade intent validation flow
- Dry-run result generation
- Paper order simulation and position tracking
- Audit events for prechecks, submissions, fills, and cancellations in simulated modes
- Replay-friendly event artifacts

**Non-goals**

- Live order submission
- Live wallet credential use
- Production fund movement

**Exit Criteria**

- Execution-facing paths default to dry-run or paper
- Trade intents can be validated without live side effects
- Paper positions can be reconstructed from stored events
- Audit trails exist for simulated lifecycle events

## Phase 4: Wallet Intelligence

**Objective**

Add wallet observation and analysis that can inform strategy without enabling live wallet automation.

**Scope / Deliverables**

- Wallet registry and status controls
- Wallet activity ingestion
- Event classification and deduplication
- Wallet scoring and profiling
- Shadow copy analysis and candidate intent generation

**Non-goals**

- Live copy-trading
- Unbounded wallet mirroring
- Automatic policy bypass based on wallet activity

**Exit Criteria**

- Wallets can be registered, paused, and analyzed
- New wallet actions can be detected and deduplicated
- Candidate intents are routed through policy concepts, not execution shortcuts
- Shadow-mode reporting distinguishes copied versus skipped opportunities

## Phase 5: Arkham Intelligence

**Objective**

Add on-chain enrichment and investigation workflows as intelligence inputs only.

**Scope / Deliverables**

- Address enrichment and caching
- Counterparty and funding-chain views
- Suspicious cluster heuristics
- Dossier generation
- Watchlist-grade alerts for strategy and operator review

**Non-goals**

- Auto-trading directly from Arkham signals
- Treating heuristic attribution as fact
- Replacing policy review with intelligence labels

**Exit Criteria**

- Addresses can be enriched and revisited from cache
- Clusters and dossiers include confidence and provenance
- Arkham outputs are limited to alerts, analysis, and watchlist suggestions
- No Arkham path can submit or cancel orders

## Phase 6: Replay

**Objective**

Make system behavior reconstructable for debugging, incident response, and regression safety.

**Scope / Deliverables**

- Deterministic replay inputs and fixtures
- Reconstruction of signals, candidate intents, execution events, and positions
- Postmortem-friendly CLI or internal workflows
- Replay coverage for key execution and policy scenarios

**Non-goals**

- UI-heavy incident tooling
- Live mode rollout
- Ad hoc debugging that bypasses stored events

**Exit Criteria**

- A historical window can be replayed from stored artifacts
- Investigators can explain why an intent was approved, rejected, or simulated
- Replay scenarios cover dry-run and paper execution paths
- Regression testing can use replay fixtures as a stable contract

## Parallel Track: CLI/TUI Parity

**Objective**

Deliver a more operator-friendly CLI and TUI surface inspired by the official Polymarket CLI without collapsing this repo's intelligence and execution boundaries.

**Scope / Deliverables**

- Upstream UX parity research note in `docs/research/polymarket-cli-ux-parity.md`
- First implemented parity slice:
  - `pm status` and `pm status --verbose`
  - stronger table-first human-readable output for key operator commands
  - `pm setup guide`
  - `pm shell`
- First interactive CLI polish slice:
  - `pm setup wizard`
  - blue operator-style banners and framed sections for root, setup, shell, and operator-status flows
  - menu-driven shell shortcuts for common workflows
  - interactive Y/N confirmations for sensitive live actions in human mode
- Future command placeholders for broader wallet and setup surfaces
- Explicit architectural boundaries for future execution-adjacent UX
- Guardrails that keep read-only intelligence phases separate from auth and live operator flows

**Non-goals**

- Adopting plaintext private-key storage as the default operator strategy
- Replacing the current normalized JSON contract with upstream raw payloads
- Adding a full-screen daemon UI in this slice
- Adding auto-trading, auto-submit loops, or new protocol integrations in this slice

**Exit Criteria**

- The parity research note exists and is linked from repo docs
- The roadmap explicitly names the CLI/TUI parity track
- `pm setup guide`, `pm shell`, and `pm status --verbose` are documented as implemented
- `pm setup wizard` and the first interactive confirmation and banner/menu polish slice are documented as implemented
- The CLI spec distinguishes the delivered parity slice from still-deferred parity targets
- Repo docs clearly separate current UX parity work from future live/operator expansions

## Phase 7: Live Readiness

**Objective**

Define the controls and evidence required before considering any live trading implementation.

**Scope / Deliverables**

- Manual approval paths
- Kill switch and risk stop requirements
- Secret management expectations
- Replay confidence and integration test thresholds
- Bounded operator runbooks for bootstrap, queue, approved dispatch, and reporting
- Operational runbooks for reconciliation, incident response, and rollback

**Non-goals**

- Turning on live trading by default
- Shipping production trading code in bootstrap tasks
- Enabling live wallet automation

**Exit Criteria**

- Readiness requirements are documented and testable
- Replay and integration coverage are strong enough to validate behavior changes
- Secret handling and operator approval paths are explicit
- Operator workflow commands exist for one-cycle bootstrap, queueing, approved dispatch, and reporting without adding a daemon
- Live mode remains gated behind deliberate future implementation work
