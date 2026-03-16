# AGENTS.md

## Mission

This repository is a docs-first, execution-first workspace for a modular Polymarket trading system. Codex must preserve strict boundaries between execution, intelligence, strategy, and operations so the repo can evolve without hidden live-trading behavior.

## Architecture Boundaries

- `src/pm/execution` is the only module allowed to place, replace, or cancel orders.
- `src/pm/market` is read-only market discovery and monitoring.
- `src/pm/wallet` is wallet intelligence and copy-trading signal generation, not live wallet automation.
- `src/pm/arkham` is on-chain enrichment, clustering, dossier, and alert logic only.
- `src/pm/strategy` is for signal evaluation, orchestration, approvals, and policy decisions.
- `src/pm/cli` exposes operator workflows and must respect safe defaults.
- `src/pm/common` contains shared types and helpers, not cross-cutting business logic that hides module boundaries.

## Mandatory Rules

- Do not add production trading code in bootstrap tasks.
- Do not create live wallet logic.
- Do not add dependencies unless the user explicitly requests them.
- Do not place or cancel orders outside the execution module.
- AI, research, and intelligence modules may emit signals, candidate intents, analyses, alerts, or watchlist updates only.
- Default any execution-facing behavior to `dry-run` or `paper` unless the task explicitly requires otherwise.
- Never commit secrets, private keys, API credentials, or real wallet material.
- Use `.env.example` as the committed pattern for config placeholders.

## Workflow Conventions

- Follow docs-first workflow. Update docs before or alongside behavior changes, not after.
- Follow spec-first workflow. Every new module and every material behavior change must have a matching spec entry under `docs/specs`.
- Keep Python package code under `src/pm`.
- Keep tests under `tests/unit`, `tests/integration`, and `tests/replay`.
- Prefer small adapters and explicit interfaces over monolithic service classes.
- Keep strategy logic, intelligence logic, and execution logic separated even when code reuse is tempting.
- Treat replay support and auditability as first-class requirements for execution, policy, and ops changes.

## Required Update Behavior

- When adding a new module, add or update its matching spec in `docs/specs` in the same task.
- When changing execution, strategy, or policy behavior, update the relevant docs and add or update tests.
- When introducing CLI surface, document command intent, safe defaults, and any confirmation requirements.
- When touching secrets or configuration flows, update `.env.example` patterns only; never commit real values.
- When adding new signal-producing logic, ensure the output stops at signal, alert, watchlist, or candidate intent boundaries unless the work is explicitly inside execution.

## Done Criteria

- Architecture boundaries are preserved.
- Matching specs are added or updated for any new module or material behavior change.
- Tests are added or updated when behavior changes.
- No secrets are committed.
- No accidental live behavior is enabled by default.
- Execution remains the only path for order placement and cancellation.

## Review Checklist

- Does the change keep order placement and cancellation inside `src/pm/execution` only?
- Does the change preserve `dry-run` or `paper` as the default for execution-facing flows?
- Does the change avoid adding live wallet automation?
- Does the change update the relevant spec and tests?
- Does the change avoid introducing secrets or credential leakage?
