# Interactive CLI Design

Reviewed on March 19, 2026.

## Purpose

This note defines the first interactive CLI UX layer for `polymarket-agent`.

It is a UX layer over the existing modular operator stack. It is not:

- a new execution architecture
- a daemon
- a full-screen TUI
- an automation loop

The design goal is a more polished operator experience that feels closer in spirit to the official `polymarket-cli` while preserving this repo's stricter execution boundaries and safety defaults.

## UX Goals

- Make the main CLI feel intentional and operator-grade at first contact.
- Reduce friction for common setup, review, dispatch, and execution-observation workflows.
- Keep human-readable output strong without weakening the normalized JSON contract.
- Preserve paper-first and explicit live gating.
- Keep interactive flows bounded, reversible, and one-command-at-a-time.

## What We Borrow From Official `polymarket-cli`

- a branded terminal entry experience
- guided setup flow
- interactive shell ergonomics
- richer framed terminal sections instead of plain raw text dumps
- human-friendly confirmation prompts for sensitive live actions

These are UX borrowings only. They do not imply a Rust architecture, plaintext config, or upstream-style output contracts.

## What We Intentionally Keep Different

- Secrets remain env-only by default.
- JSON stays normalized and stable instead of exposing raw upstream payloads.
- Live writes remain paper-first and explicitly gated.
- The shell stays bounded and non-daemonized.
- Strategy, risk, ops, and execution remain separate layers.
- Execution alone may place or cancel orders.

## Secret Handling Policy

Default policy:

- environment-only secrets
- no plaintext private-key config by default
- no local auth cache by default

Wizard exception:

- `pm setup wizard` may accept a hidden session-only private key
- that secret lives only in memory for the wizard run
- it is never printed
- it is never persisted to local config or state

This repo does not adopt plaintext wallet import or private-key config as a default operator strategy.

## Implemented Interactive Slice

### Entry and setup

- root help now shows a branded operator banner
- `pm setup guide` uses framed Rich sections
- `pm setup wizard` adds a bounded guided flow with yes/no prompts and optional hidden session-only secret entry

### Shell

- `pm shell` remains a bounded REPL
- it now includes:
  - a startup banner
  - a quick menu
  - numeric workflow shortcuts
  - `menu` and `back` pseudo-commands
- it still supports direct passthrough commands and short aliases

### Human-readable command output

The current framed Rich treatment is applied to key operator commands:

- `pm status`
- `pm ops queue`
- `pm strategy intents`
- `pm strategy executions`
- `pm exec events`

### Live confirmations

Interactive human mode may prompt for Y/N confirmation when the operator requests a live action without `--confirm`:

- `pm approve set --live`
- live strategy dispatch
- live ops cycle approved
- `pm exec post --live`
- `pm exec cancel --live`
- `pm exec cancel-all --live`
- `pm exec cancel-market --live`

Guardrails:

- `--live --confirm` still bypasses the prompt and remains valid
- JSON mode never prompts
- non-TTY mode never prompts
- JSON and non-TTY flows still require explicit `--confirm`

## Deferred

- full-screen TUI
- daemonized shell or watch surface
- wallet create/import flows
- plaintext config onboarding
- any hidden automation layer behind shell or wizard UX

## Design Rule

Interactive polish may improve operator workflow, but it must never weaken:

- env-only default secret handling
- explicit live intent
- deterministic JSON contracts
- the execution boundary
