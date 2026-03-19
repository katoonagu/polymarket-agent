# Polymarket CLI UX Parity

Reviewed on March 18, 2026.

## Scope

This note treats the official Rust-based `Polymarket/polymarket-cli` as an upstream UX reference, not as an architectural replacement.

`polymarket-agent` remains:

- Python-native
- execution-isolated
- paper-first and guarded on the current branch
- structured around normalized public-data contracts rather than raw upstream payloads
- strict about keeping execution as the only module allowed to place or cancel orders

The goal of this note is to document which operator UX patterns from the official CLI are worth mirroring later, which fit this repo cleanly, and which should remain deferred or rejected.

## Upstream Sources

- Official README: <https://github.com/Polymarket/polymarket-cli/blob/main/README.md>
- Command tree and global flags: <https://github.com/Polymarket/polymarket-cli/blob/main/src/main.rs>
- Wallet commands: <https://github.com/Polymarket/polymarket-cli/blob/main/src/commands/wallet.rs>
- Approve commands: <https://github.com/Polymarket/polymarket-cli/blob/main/src/commands/approve.rs>
- Setup commands: <https://github.com/Polymarket/polymarket-cli/blob/main/src/commands/setup.rs>
- Interactive shell: <https://github.com/Polymarket/polymarket-cli/blob/main/src/shell.rs>
- Output helpers: <https://github.com/Polymarket/polymarket-cli/blob/main/src/output/mod.rs>

## What The Official CLI Provides Today

The official Polymarket CLI is broader than this repo's current read-only intelligence surface. In addition to public market, event, and CLOB reads, it exposes operator-oriented workflows such as:

- guided `setup`
- `wallet create`
- `wallet import`
- `wallet address`
- `wallet show`
- `wallet reset`
- `approve check`
- `approve set`
- `shell`
- `status`

It also provides global output selection through `--output table|json` and puts real emphasis on human-readable output, including richer table rendering and interactive shell ergonomics.

That broader UX lives alongside authenticated and trading-capable flows upstream. Those flows are real upstream features, but they are outside the scope of this repository's current read-only phase.

## What We Want To Mirror

These upstream UX patterns are desirable here:

- a setup guide that makes local onboarding and operator readiness easier
- clearer wallet verbs and wallet-surface discoverability
- explicit approval verbs instead of implicit side effects
- shell and status surfaces for operator navigation and quick situational awareness
- stronger table-first human-readable output across the CLI
- an eventual TUI-adjacent operator experience that still preserves machine-friendly JSON for automation

The parity target is operator experience, not implementation symmetry.

## Fits Our Architecture

The following parity ideas fit this repo cleanly:

- `pm shell` as a bounded operator surface over the existing intelligence and execution-safe commands
- `pm status` as a local-first health and workflow summary for local state and recent operator activity
- `pm setup guide` as non-mutating orchestration over env checks, readiness, and execution-module setup checkpoints
- richer human-readable tables layered on top of the existing normalized CLI contracts

Two areas fit only as future execution-adjacent modules, not as current read-only intelligence features:

- wallet creation and import UX
- approval inspection and mutation UX

That distinction matters. This repo should keep read-only intelligence usable without requiring any wallet setup.
Intelligence modules remain separate from execution modules, and later wallet or approval UX must not blur that boundary.

## Deferred

These parity items are intentionally deferred:

- auth-backed wallet management
- wallet creation and import behavior
- approval transactions
- fuller execution-integrated status surfaces
- a full interactive shell or TUI implementation beyond the bounded REPL
- any setup flow that can enable execution behavior end to end

They belong to future execution-adjacent work, not the current read-only branch contract.

## Explicitly Reject

The following upstream-adjacent patterns are not targets for this repo:

- adopting plaintext private-key config as the default strategy
- collapsing intelligence and execution into one module boundary
- making auth or execution prerequisites for public read-only usage
- copying upstream raw error or output contracts when they conflict with this repo's normalized contracts

This repo may borrow operator UX ideas from upstream, but not at the cost of its execution boundary or safer local-operator defaults.

## Parity Direction

| Upstream surface | Current or future `polymarket-agent` direction |
| --- | --- |
| `setup` | `pm setup doctor`, `pm setup guide`, broader setup flow later |
| `wallet create`, `wallet import`, `wallet show` | `pm wallet create`, `pm wallet import`, `pm wallet show` |
| `approve check`, `approve set` | `pm approve check`, `pm approve set` |
| `shell` | `pm shell` |
| `status` | `pm status`, `pm status --verbose` |

## First Implemented Slice

The current branch now includes the first operator-UX parity slice:

- `pm status`
- `pm status --verbose`
- `pm setup guide`
- `pm shell`
- richer table-first output for key operator commands

That slice intentionally improves workflow and human-readable output without changing the repo's execution boundaries, env-only secret policy, or live-write guardrails.
