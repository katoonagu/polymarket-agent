# 02 — Market Intelligence Spec

## Назначение

Модуль Market Intelligence отвечает за **поиск, нормализацию, наблюдение и ранжирование** рынков Polymarket.

Это не execution module. Он не торгует. Он формирует **объекты наблюдения** и **market context** для остальных модулей.

## Основные задачи

1. Обнаруживать новые и существующие рынки.
2. Поддерживать watchlists.
3. Загружать market/event metadata.
4. Следить за ценами YES/NO, spread, volume, orderbook, price history.
5. Нормализовать recurring markets, например 5m/15m BTC.
6. Поддерживать pool:
   - выбранные рынки;
   - активные рынки;
   - наблюдаемые рынки;
   - рынки с открытыми позициями;
   - рынки в cooldown.

## Почему это важно

Для Polymarket самая частая ошибка в ботах — смешивать:
- market discovery;
- pricing;
- strategy logic;
- execution.

В итоге бот либо делает лишние запросы, либо принимает решение по неполному market state.

## Входы

- ручные команды оператора;
- strategy subscriptions;
- recurring discovery rules;
- wallet activity signals;
- Arkham-triggered market candidates;
- news / LLM suggestions;
- existing positions requiring monitoring.

## Выходы

### 1. MarketRecord
- `market_id`
- `slug`
- `event_id`
- `question`
- `description`
- `category/tag/topic`
- `outcome_yes_token_id`
- `outcome_no_token_id`
- `start_time`
- `end_time`
- `active/closed/archived`
- `fees_enabled`
- `liquidity metrics`
- `watch_status`

### 2. MarketSnapshot
- timestamp
- bid/ask YES
- bid/ask NO
- midpoint
- spread
- last trade
- book depth
- recent volume
- open interest if needed
- volatility proxy

### 3. Alerts
- spread widened
- price crossed threshold
- large move
- unusual size
- low liquidity
- recurring market rolled to next interval
- watched wallet entered watched market

## Подмодули

### A. Discovery
Ищет рынки по:
- slug;
- id;
- search query;
- tags;
- series-like rules;
- recurring templates.

### B. Normalizer
Приводит market metadata к одной внутренней схеме.

### C. Watchlist Manager
Поддерживает списки:
- manual watchlist;
- strategy watchlist;
- open-position watchlist;
- high-priority watchlist;
- archival watchlist.

### D. Snapshot Service
Снимает market state:
- polling;
- websocket subscription;
- fallback mode при деградации сети.

### E. Event Pool Classifier
Маркирует рынок по статусу:
- DISCOVERED
- WATCHING
- ELIGIBLE
- IN_POSITION
- EXIT_ONLY
- COOL_DOWN
- ARCHIVED

### F. Recurring Market Resolver
Нужен для рынков типа “Bitcoin Up or Down — 15 min”.
Его задача — не сканировать бесконечную историю, а уметь:
- вычислять активный временной слот;
- восстанавливать slug текущего события;
- переходить на следующий слот;
- архивировать прошлый слот.

## Поддержка recurring crypto markets

Этот тип рынков требует особого режима:

- внешний price feed для underlying;
- привязка к time bucket;
- fast refresh interval;
- более строгие latency thresholds;
- отдельные risk limits от политических/новостных рынков.

Для recurring markets нужна сущность:

### `SeriesTemplate`
- `template_id`
- `base_asset` (BTC, ETH, etc.)
- `interval` (5m, 15m, 1h)
- `slug_rule`
- `market_rollover_policy`
- `pre-close handling`
- `post-close archival`

## Приоритеты наблюдения

### Tier 1 — Open position markets
Любой рынок, где есть реальный риск, обновляется первым.

### Tier 2 — Execution candidates
Рынки, по которым стратегия близка к входу.

### Tier 3 — Research watchlist
Наблюдение для анализа без немедленного входа.

### Tier 4 — Historical archive
Для replay и postmortem.

## Ключевые метрики

- spread
- midpoint vs last trade discrepancy
- best executable price
- book depth at configured size
- time since last trade
- short-term price drift
- liquidity score
- market freshness
- event freshness
- number of watchers/strategies depending on market

## Объекты хранения

- `markets`
- `market_events`
- `market_snapshots`
- `market_watchlists`
- `series_templates`
- `market_alerts`
- `market_rollovers`

## CLI команды

```text
pm market show --slug <slug>
pm market event --slug <slug>
pm market search --query "btc 15 min"
pm market book --token-id <id>
pm market price --token-id <id>
pm market watch add --slug <slug>
pm market watch remove --slug <slug>
pm market watch list
pm market snapshot --slug <slug>
pm market alerts --slug <slug>
pm market pool show --status WATCHING
pm market recurring resolve --series btc-15m
pm market recurring roll --series btc-15m
```

## Правила проектирования

### 1. Market data is cacheable, but not forever
Нельзя полагаться на старые token IDs и stale snapshots.

### 2. Snapshot != execution price
Displayed price и реально исполнимая цена могут отличаться.

### 3. Watchlists must be explicit
У каждого рынка должен быть ответ на вопрос:
- зачем мы его держим?
- кто его подписал?
- когда можно удалить?

### 4. Discovery must be deterministic
Если recurring resolver сегодня нашёл рынок, завтра он должен найти тот же рынок по тем же правилам.

## Alerts policy

Модуль должен уметь генерировать алерты по условиям:

- `spread > X`
- `midpoint moved > Y bps in Z seconds`
- `watched wallet opened trade`
- `watched wallet averaged down`
- `price entered [a, b]`
- `liquidity below threshold`
- `resolution time < threshold`
- `market rolled to next interval`

## MVP definition

MVP готов, если умеет:

1. найти рынок по slug;
2. хранить token IDs;
3. вести watchlist;
4. получать snapshot bid/ask/spread;
5. поддерживать recurring resolver для одной серии (например BTC 15m);
6. поднимать алерт на crossing price threshold;
7. отдавать единый market context для execution и strategy module.

## Phase 2 expansion

- related markets graph;
- contradiction detection;
- semantic clustering;
- event summaries;
- auto-generated watchlists;
- cross-market hedging candidates.
