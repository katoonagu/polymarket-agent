# 02 - Market Intelligence Spec

## Purpose

The market module owns read-only Polymarket market discovery, watchlists, saved snapshots, and deterministic recurring-market resolution. It does not place orders, manage keys, sign transactions, or call execution code.

In the current phase, the market module composes:

- public Gamma discovery
- public CLOB reads
- bounded public market websocket reads
- bounded public RTDS crypto price reads
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

## Public Streaming Layer

The market intelligence surface now includes bounded read-only public stream sessions. These sessions are operator-triggered only. They do not start a daemon, do not open user-authenticated channels, and do not call execution code.

Current commands:

```text
pm stream market --token-id <id> --seconds <n> [--max-events <n>] [--json]
pm stream crypto --symbol <symbol> --source <binance|chainlink> --seconds <n> [--max-events <n>] [--json]
pm stream watch --slug <market-slug> --seconds <n> [--max-events <n>] [--json]
pm stream recurring --query <text> --interval <5m|15m|1h> --seconds <n> [--max-events <n>] [--json]
```

Rules:

- all sessions are bounded by required `--seconds`
- `--max-events` is optional and may end the session early
- market stream normalization handles `book`, `best_bid_ask`, `price_change`, `last_trade_price`, and `tick_size_change`
- RTDS normalization supports Binance and Chainlink public crypto price feeds
- captured events are appended to `.pm/state/stream-events.jsonl`
- reconnects are limited and deterministic
- recurring streams reuse the recurring resolver and infer supported crypto symbols from resolved market text

### Planned BTC 15m Chainlink ladder support

The current market and stream layer already provides the core public inputs that
the planned BTC 15m Chainlink ladder track will need:

- recurring Gamma resolution for BTC 15m markets
- public CLOB reads for bid, ask, midpoint, and spread
- public RTDS crypto reads with `--source chainlink`
- public RTDS crypto reads with `--source binance`
- public Binance REST overlays for `bookTicker`, `depth`, and closed `1m`
  klines inside the bounded BTC15m research path

However, the current branch does not yet provide the full future recorder
contract for that strategy. In particular:

- `pm stream recurring` is still a generic recurring-context stream surface
- the ladder track will require explicit per-window Chainlink and Binance
  capture plus start and end boundary recording
- the ladder track now also records bounded Binance liquidity and volatility
  overlays, but that overlay remains strategy-specific rather than part of the
  generic stream CLI contract
- the ladder track will require minute-5 decision-state persistence and ladder
  microstructure recording
- canonical boundary selection rules still need empirical validation
- current generic stream capture must not be treated as settlement-equivalent
  Chainlink boundary truth or as the full future recorder contract

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
pm stream market --token-id <id> --seconds <n> [--max-events <n>] [--json]
pm stream crypto --symbol <symbol> --source <binance|chainlink> --seconds <n> [--max-events <n>] [--json]
pm stream watch --slug <market-slug> --seconds <n> [--max-events <n>] [--json]
pm stream recurring --query <text> --interval <5m|15m|1h> --seconds <n> [--max-events <n>] [--json]
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
- private websocket subscriptions
- background daemons
- hidden ranking weights or unsupported recurring APIs
