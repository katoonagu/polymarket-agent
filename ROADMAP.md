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

**Non-goals**

- Order placement or cancellation
- Strategy-driven auto-trading
- Live wallet following

**Exit Criteria**

- Operator can discover and inspect markets from CLI or internal interfaces
- Watched markets can produce normalized snapshots
- Recurring market resolution is deterministic for the first supported series
- Canonical read-only CLI contracts are documented for both Gamma discovery and public CLOB reads
- No read-only component contains direct execution logic

### Part 02B: Official CLI Alignment

**Objective**

Align this repo's CLI documentation with the strongest read-only command-surface and output-contract patterns from the official `Polymarket/polymarket-cli`, without adopting its Rust architecture or authenticated command set.

**Scope / Deliverables**

- Upstream research note under `docs/research/`
- Canonical namespace split for public reads:
  - `pm market`
  - `pm clob`
- Global output contract for future CLI implementation:
  - `--output table|json`
  - `--json` compatibility alias
- Structured JSON error contract for CLI failures
- Alias and deprecation policy for temporary compatibility commands
- README and CLI spec consistency for the canonical read-only surface

**Non-goals**

- Code changes
- Adopting the official Rust CLI architecture
- Authenticated wallet, approval, or trading command work
- Any mutating or execution-capable CLI behavior

**Exit Criteria**

- Upstream analysis explicitly states what is adopted now, later, and rejected
- `README.md`, `ROADMAP.md`, and `docs/specs/06-cli-ops.md` agree on the canonical public read command surface
- The CLI spec documents normalized success JSON and structured JSON errors
- `pm market book` and `pm market price` are documented as temporary aliases, not long-term canonical commands

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

## Phase 7: Live Readiness

**Objective**

Define the controls and evidence required before considering any live trading implementation.

**Scope / Deliverables**

- Manual approval paths
- Kill switch and risk stop requirements
- Secret management expectations
- Replay confidence and integration test thresholds
- Operational runbooks for reconciliation, incident response, and rollback

**Non-goals**

- Turning on live trading by default
- Shipping production trading code in bootstrap tasks
- Enabling live wallet automation

**Exit Criteria**

- Readiness requirements are documented and testable
- Replay and integration coverage are strong enough to validate behavior changes
- Secret handling and operator approval paths are explicit
- Live mode remains gated behind deliberate future implementation work
