# 02 - Market Intelligence Spec

## Purpose

The market module owns read-only Polymarket market discovery, watchlists, saved snapshots, and deterministic recurring-market resolution. It does not place orders, manage keys, sign transactions, or call execution code.

In the current phase, the market module composes:

- public Gamma discovery
- public CLOB reads
- public Data API summaries
- local gitignored market state under `.pm/state/`

## Current Responsibilities

### Public market discovery

The market module must support:

- free-text market search
- market lookup by slug
- event lookup by slug
- market lookup by condition ID when higher-level services need it

Normalized public market outputs must include at least:

- `market_slug`
- `event_slug`
- `question`
- `event_title`
- `active`
- `closed`
- `enable_order_book`
- `condition_id`
- `token_ids`
- `outcomes`

When outcomes and token IDs align by index, the CLI should display explicit outcome-to-token mappings.

### Local market watchlist

The market watchlist is a local gitignored registry stored at:

- `.pm/state/market-watchlist.json`

It is versioned JSON and must use:

- deterministic append order
- atomic writes
- schema validation errors instead of silent resets

Each watched market entry includes:

- `market_slug`
- `event_slug`
- `question`
- `label`
- `tags`
- `added_at`

Current commands:

```text
pm market watch add --slug <market_slug> [--label <text>] [--tag <text>]
pm market watch remove --slug <market_slug>
pm market watch list [--json]
```

Rules:

- `watch add` validates the slug through the public Gamma adapter first.
- duplicate watches are rejected deterministically with `already_watched`.
- tags are stored as unique sorted strings.
- `watch list` reads only local state.

### Saved market snapshots

Saved market snapshots are append-only records stored at:

- `.pm/state/market-snapshots.json`

Current commands:

```text
pm market watch snapshot --slug <market_slug> [--json]
pm market watch refresh [--json]
```

Rules:

- `snapshot --slug ...` may snapshot any valid market slug.
- `snapshot --slug ...` does not auto-add the market to the watchlist.
- `refresh` snapshots every watched market in watchlist order.
- both commands remain read-only and save local artifacts only.

## Snapshot Assembly Contract

Snapshots are composed from existing public adapters only:

- Gamma for market and event context
- CLOB for midpoint, spread, and book summaries
- Data API for open interest and top holders

Each snapshot record should include:

- `snapshot_at`
- `market_slug`
- `event_slug`
- `question`
- `event_title`
- `condition_id`
- `token_ids`
- `outcomes`
- `active`
- `closed`
- `watch_metadata` when the market is already watched
- `tokens`
- `open_interest`
- `top_holders`
- `holders_total_returned`
- `errors`

Token summaries are compact, not raw full-book dumps. Each token summary should include:

- `token_id`
- `outcome`
- `midpoint`
- `spread`
- `best_bid`
- `best_ask`
- `bid_level_count`
- `ask_level_count`

Holder summaries should keep the first 5 normalized holder rows in Data API order.

Upstream partial failures must not prevent snapshot persistence. They should be stored as structured errors:

```json
{
  "section": "open_interest",
  "code": "request_failed",
  "message": "..."
}
```

## Recurring-Market Resolver

The recurring resolver does not use special recurring-market APIs. It works by applying deterministic heuristics to public Gamma search results.

Current commands:

```text
pm market recurring latest --query <text> --interval <value> [--json]
pm market recurring list --query <text> --interval <value> --limit <n> [--json]
```

Supported intervals:

- `5m`
- `15m`
- `1h`

Built-in interval markers:

- `5m`: `5m`, `5 min`, `5 minute`, `5 minutes`
- `15m`: `15m`, `15 min`, `15 minute`, `15 minutes`
- `1h`: `1h`, `1 hour`, `60 min`, `60 minutes`

### Ranking rules

Candidates are ranked deterministically in this order:

1. active markets before inactive
2. open markets before closed
3. exact interval-marker matches before weaker matches
4. stronger query-token match score across question, event title, market slug, and event slug
5. newer or upcoming candidate by Gamma time-like fields when present:
   - `endDate`
   - `resolutionDate`
   - `startDate`
6. original API order when no recency field exists
7. `market_slug` ascending as the final tie-break

`latest` returns the single top-ranked candidate from the same ranking logic.

`list` returns ranked candidates plus explainability fields:

- `rank`
- `match_score`
- `matched_interval`
- `recency_source`

## CLI Contract

The current market namespace is:

```text
pm market search --query "<text>" --limit <n> [--json]
pm market show --slug <market-slug> [--json]
pm market event --slug <event-slug> [--json]
pm market watch add --slug <market-slug> [--label <text>] [--tag <text>]
pm market watch remove --slug <market-slug>
pm market watch list [--json]
pm market watch snapshot --slug <market-slug> [--json]
pm market watch refresh [--json]
pm market recurring latest --query <text> --interval <5m|15m|1h> [--json]
pm market recurring list --query <text> --interval <5m|15m|1h> --limit <n> [--json]
```

Temporary compatibility aliases also exist:

```text
pm market book --token-id <id>
pm market price --token-id <id>
```

These aliases forward to the canonical public CLOB namespace and should be treated as deprecated.

## Determinism and Non-Goals

The market module must stay:

- read-only
- deterministic
- explainable
- file-backed instead of database-backed in this phase

It must not add:

- wallet auth
- order placement
- execution engine calls
- websocket subscriptions
- background daemons
- hidden ranking weights or unsupported recurring APIs
