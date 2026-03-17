# Polymarket CLI Analysis

Reviewed on March 17, 2026.

## Scope

This note treats the official Rust-based `Polymarket/polymarket-cli` as an upstream reference for read-only command-surface and output-contract patterns only. It does not change this repo's architecture, language choice, or execution boundary.

`polymarket-agent` remains:

- Python-native;
- docs-first;
- execution-first;
- read-only by default outside the execution module.

## Upstream Sources

- Official README: <https://github.com/Polymarket/polymarket-cli/blob/main/README.md>
- Command tree and global flags: <https://github.com/Polymarket/polymarket-cli/blob/main/src/main.rs>
- Markets commands: <https://github.com/Polymarket/polymarket-cli/blob/main/src/commands/markets.rs>
- Events commands: <https://github.com/Polymarket/polymarket-cli/blob/main/src/commands/events.rs>
- CLOB commands: <https://github.com/Polymarket/polymarket-cli/blob/main/src/commands/clob.rs>
- Output helpers: <https://github.com/Polymarket/polymarket-cli/blob/main/src/output/mod.rs>

## What The Official CLI Does

The official CLI is a broad Rust command-line tool that covers both public data access and authenticated account workflows. The read-only command families most relevant to this repo are:

- `markets`
- `events`
- `clob`

The wider upstream CLI also includes operational and account-oriented namespaces such as:

- `wallet`
- `approve`
- `bridge`
- `ctf`
- `data`
- `status`
- `setup`
- `shell`

Two upstream patterns are immediately useful as reference material:

- a global output mode with `--output table|json`;
- a clean split between human-readable output and JSON output for scripts.

## Translation To This Repo's Canonical Read Surface

| Upstream command family | Upstream pattern | `polymarket-agent` canonical command |
| --- | --- | --- |
| markets | `markets search`, `markets get` | `pm market search`, `pm market show` |
| events | `events get` | `pm market event` |
| clob | `clob book` | `pm clob book` |
| clob | `clob price --side ...` | `pm clob price` returning both buy and sell prices |

This repo intentionally keeps `pm market show` and `pm market event` instead of copying the upstream names verbatim.

## Adopt Now

These patterns are worth adopting immediately at the docs and contract level:

- global output handling through `--output table|json`;
- `--json` as a compatibility alias for `--output json`;
- canonical top-level read-only namespaces:
  - `pm market`
  - `pm clob`
- normalized `snake_case` success JSON instead of raw Gamma or CLOB wire payloads;
- deterministic separation between human output and machine output;
- explicit compatibility-alias policy for `pm market book` and `pm market price` during the namespace transition.

One upstream pattern is useful as a prompt for improvement, but not as a contract to copy directly: upstream JSON errors are lightweight, while this repo should keep a more structured nested error envelope for operators and tests.

## Adopt Later

These read-only upstream ideas are useful, but should wait until the local adapter layer and tests justify them:

- broader list-style discovery commands beyond the current search and slug lookups;
- normalized series support after the market adapter has a stable series contract;
- richer public CLOB reads such as midpoint, spread, tick size, last trade, time, or batch reads if they materially improve operator workflows;
- additional public data surfaces only after they are specified in `docs/specs` and backed by normalized models and tests.

## Explicitly Reject

The following are not goals for this repo:

- replacing this repo with the official Rust CLI;
- importing wallet, auth, approve, bridge, CTF, trading, or account-management flows into non-execution modules;
- treating raw upstream API payloads as this repo's long-term public contract;
- keeping `pm market book` and `pm market price` as the permanent namespace for public CLOB reads.

This repo may borrow useful CLI ergonomics from upstream, but the architectural boundary remains unchanged: only the execution module may own order placement and cancellation.
