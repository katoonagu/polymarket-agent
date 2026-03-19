# 08 - Portfolio Ledger Spec

## Purpose

The portfolio layer gives the operator a deterministic account-level truth surface on top of the existing intelligence, strategy, risk, dispatch, and execution stack. It does not introduce automation. It reads public account state, reconciles it against local execution and strategy linkage, and persists append-only local portfolio records for audit.

## Current Phase

Implemented commands:

- `pm portfolio summary`
- `pm portfolio positions`
- `pm portfolio closed`
- `pm portfolio market`
- `pm portfolio exposure`
- `pm portfolio pnl`
- `pm portfolio reconcile`

This phase adds:

- fresh portfolio snapshots from the public Data API
- gross and net exposure aggregation
- realized and unrealized PnL aggregation
- per-market exposure and PnL slices
- per-strategy exposure and PnL slices where explicit local linkage exists
- discrepancy reporting against authenticated execution reconciliation state

This phase still does not add:

- a fill ledger database
- a daemon or scheduler
- automatic rebalancing
- portfolio-driven order placement
- full account-wide strategy attribution heuristics

## Account Resolution

Portfolio ownership resolves through the existing authenticated context:

1. `funder_address` when present
2. otherwise `signer_address`

If neither address is available, portfolio commands return a structured CLI error with guidance to inspect auth context through `pm auth show` or `pm setup guide`.

## Snapshot Sources

Fresh snapshots reuse the existing public Data API client:

- current positions
- closed positions
- holdings value

Snapshots also reuse local state for attribution and reconciliation context:

- strategy execution links
- strategy dispatch results
- execution order results
- execution reconciliation history

## Aggregation Rules

### PnL

- realized PnL = sum of closed-position `realized_pnl`
- unrealized PnL = sum of current-position `cash_pnl`
- total PnL = realized + unrealized

### Exposure

- gross exposure = sum of current-position `current_value`
- per-market gross exposure = sum of all current position values for that market
- per-market net exposure = absolute value of `YES current_value - NO current_value` within one `condition_id`
- any non-`YES`/`NO` outcomes contribute to a separate non-netted bucket
- top-level net exposure = sum of per-market net exposures

## Strategy Attribution Limits

Per-strategy attribution is intentionally narrow and tool-local in this phase.

Rules:

- attribution uses only explicit local linkage from strategy dispatch and execution records
- only live `POSTED` strategy dispatches participate in the linkage map
- current and closed positions are attributed only when a unique linked `(condition_id, token_id)` pair exists
- positions with no pair match remain `unlinked`
- positions that match more than one distinct strategy name become `ambiguous`
- ambiguous or unlinked positions are not heuristically back-allocated

This is not a full portfolio accounting engine for arbitrary external activity.

## Reconciliation

`pm portfolio reconcile` performs:

1. a fresh portfolio snapshot
2. a fresh authenticated execution reconciliation pass
3. discrepancy classification and health summarization
4. append-only local persistence

Current discrepancy classes:

- `execution_state_mismatch`
- `unlinked_current_position`
- `linked_execution_missing_from_positions`
- `ambiguous_strategy_link`

Health states:

- `healthy` when there are no discrepancies
- `warning` when only unlinked or ambiguous attribution issues exist
- `mismatch` when execution-state mismatches or missing linked executions are present

## Local State

Append-only local state under `.pm/state/`:

- `portfolio-snapshots.json`
- `portfolio-reconciliations.json`

Rules:

- versioned JSON documents
- atomic writes
- append-only records
- explicit state errors on invalid files

## Module Boundaries

- the portfolio layer may read public Data API state and local execution or strategy state
- the portfolio layer may run a fresh authenticated execution reconciliation pass
- the portfolio layer may not place, cancel, or replace orders
- execution remains the only module allowed to mutate exchange state

## Non-Goals

- no daemon loop
- no background scheduler
- no auto-submit
- no auto-retry
- no external portfolio protocol integrations
