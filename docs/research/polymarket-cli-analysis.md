# Polymarket CLI Upstream Analysis

Snapshot date: March 17, 2026

## Scope

This note analyzes the official `Polymarket/polymarket-cli` as an upstream reference for read-only command-surface and output-contract patterns.

It does not propose replacing this repository's Python architecture with the official Rust CLI. This repo remains docs-first, execution-first, and Python-native.

## Sources

- Official repository README: <https://github.com/Polymarket/polymarket-cli>
- Command tree and global flags: <https://github.com/Polymarket/polymarket-cli/blob/main/src/main.rs>
- Market commands: <https://github.com/Polymarket/polymarket-cli/blob/main/src/commands/markets.rs>
- Event commands: <https://github.com/Polymarket/polymarket-cli/blob/main/src/commands/events.rs>
- CLOB commands: <https://github.com/Polymarket/polymarket-cli/blob/main/src/commands/clob.rs>
- Output contract helpers: <https://github.com/Polymarket/polymarket-cli/blob/main/src/output/mod.rs>

## What The Official CLI Does

The official CLI is a broad Rust command-line application for Polymarket operations. Its top-level command tree includes public read commands and authenticated operational or trading commands in the same binary:

- `markets`
- `events`
- `tags`
- `series`
- `comments`
- `profiles`
- `sports`
- `clob`
- `wallet`
- `approve`
- `ctf`
- `data`
- `bridge`
- `setup`
- `shell`
- `status`
- `upgrade`

Two upstream patterns are immediately relevant to this repo:

1. It uses a global output switch: `--output table|json`, with `table` as the default.
2. It separates Gamma-style discovery commands from CLOB commands at the namespace level instead of nesting CLOB reads under `markets`.

For read-only discovery, upstream currently exposes:

- `markets list`, `markets get`, `markets search`, `markets tags`
- `events list`, `events get`, `events tags`
- `clob book`, `clob price`, `clob batch-prices`, `clob midpoint`, `clob spread`, `clob tick-size`, `clob last-trade`, `clob time`, and related read-only market metadata commands

For output, upstream uses tables for human-readable mode and JSON for machine-readable mode, with shared output helpers rather than per-command ad hoc formatting.

## Translation To This Repo

This repo should adopt the useful upstream read-only conventions while keeping its own architecture and normalized data contract.

| Upstream command | Canonical command in this repo | Notes |
| --- | --- | --- |
| `polymarket markets search` | `pm market search` | Keep singular `market` namespace in this repo. |
| `polymarket markets get` | `pm market show` | `show` stays intentional repo grammar. |
| `polymarket events get` | `pm market event` | Event lookup stays grouped under market discovery here. |
| `polymarket clob book` | `pm clob book` | Adopt now as canonical namespace split. |
| `polymarket clob price --side buy|sell` | `pm clob price` | This repo intentionally returns both BUY and SELL prices in one normalized result. |

## Adopt Now

- A global output contract: `--output table|json`, with `table` as the default.
- `--json` as a compatibility alias for `--output json`.
- Canonical public read namespaces:
  - `pm market` for Gamma discovery
  - `pm clob` for public CLOB reads
- Deterministic table output for operators and deterministic normalized JSON for automation.
- Normalized snake_case JSON instead of raw Gamma or CLOB wire payloads.
- An explicit alias policy:
  - `pm market book`
  - `pm market price`
  - These remain temporary backward-compatible aliases only.

## Adopt Later

- `pm market list` for broader discovery parity with upstream `markets list`.
- `pm event list` or equivalent event-listing support if event-centric workflows become common enough to justify their own surface.
- Additional read-only CLOB commands where they materially help operators:
  - `midpoint`
  - `spread`
  - `tick-size`
  - `last-trade`
  - `time`
  - batch reads
- More table-oriented rendering conventions once the read-only command set is broader and stable.

## Explicitly Reject

- Replacing this repository with the official Rust CLI or mirroring its entire architecture.
- Mixing authenticated wallet, approval, bridge, CTF, or trading flows into non-execution modules.
- Copying upstream order submission, cancellation, balance, reward, or account-management commands into this phase.
- Treating raw upstream Gamma or CLOB response bodies as this repo's long-term public contract.
- Keeping `pm market book` and `pm market price` as the permanent namespace for CLOB reads.

## Practical Guidance For This Repo

The upstream CLI is most useful here as a reference for:

- namespace boundaries
- output-mode ergonomics
- read-only operator workflows

It is not the reference for:

- repo architecture
- execution safety boundaries
- strategy design
- wallet or trading policy

This repo should stay strict about module separation:

- `pm market` discovers and normalizes public market and event data
- `pm clob` reads public order book and pricing data
- execution remains isolated to the execution module and is out of scope for this alignment pass
