# 01 — Execution Engine Spec

## Назначение

Execution Engine — это **единственный модуль**, которому разрешено создавать, отменять и заменять ордера. Его задача — превратить намерение:

> “Купить YES на рынке X по цене не хуже Y на сумму Z”

в **валидированное, безопасное и аудируемое действие**.

## Почему это отдельный модуль

Execution нельзя доверять:
- LLM напрямую;
- ad-hoc скриптам;
- аналитическим модулям;
- копитрейдинг-модулю.

Все внешние модули должны выдавать только **trade intent**, а не исполнять ордера сами.

## Область ответственности

Execution Engine отвечает за:

- загрузку и валидацию market/token metadata;
- подготовку order request;
- pre-trade checks;
- подпись и отправку ордера;
- cancel / cancel-all / replace;
- idempotency;
- проверку fill status;
- синхронизацию с order lifecycle;
- structured audit trail;
- dry-run / paper execution abstraction.

## Не входит в зону ответственности

- поиск рынков;
- генерация сигналов;
- copy-trading логика;
- выявление инсайдеров;
- AI-анализ новостей;
- портфельная аллокация между стратегиями.

## Входы

### 1. TradeIntent
Обязательная структура:

- `intent_id`
- `strategy_id`
- `wallet_id`
- `market_slug` или `market_id`
- `token_id` (если уже известен)
- `side` = BUY / SELL
- `outcome` = YES / NO
- `order_style` = marketable_limit / resting_limit
- `price_limit`
- `size_usdc` или `size_shares`
- `time_in_force`
- `max_slippage_bps`
- `reason`
- `created_at`
- `approval_mode` = manual / auto / dry-run

### 2. ExecutionPolicySnapshot
Снимок ограничений на момент исполнения:

- max per order;
- max per market;
- max per topic;
- max per wallet;
- daily loss limit;
- allowed strategies;
- kill switches;
- jurisdiction/compliance flags;
- market eligibility flags.

### 3. MarketSnapshot
Нужные данные о рынке:

- event id / market id / slug;
- token IDs YES/NO;
- best bid/ask;
- midpoint;
- last trade;
- tick size;
- fee enabled / fee rate if needed;
- negative risk flags;
- market status.

## Выходы

### 1. ExecutionResult
- `intent_id`
- `status` = REJECTED / ACCEPTED / SUBMITTED / PARTIAL / FILLED / CANCELLED / FAILED
- `order_id`
- `client_order_id`
- `submitted_price`
- `submitted_size`
- `fees_estimated`
- `reason_code`
- `reason_text`
- `exchange_timestamp`
- `local_timestamp`

### 2. Audit Events
Append-only события:
- INTENT_RECEIVED
- PRECHECK_PASSED
- PRECHECK_FAILED
- ORDER_SIGNED
- ORDER_SUBMITTED
- ORDER_ACK
- ORDER_PARTIAL_FILL
- ORDER_FILLED
- ORDER_CANCELLED
- ORDER_REJECTED
- ORDER_TIMEOUT
- POSITION_UPDATED

## Внутренняя декомпозиция

### A. Market Resolver
Находит рынок по slug/id, подтягивает token IDs, проверяет active/closed/archived.

### B. Pricing Adapter
Получает:
- best bid/ask;
- orderbook snapshot;
- midpoint;
- spread;
- optional last trade.

Используется для slippage и sanity checks.

### C. Pre-Trade Validator
Выполняет:

- market is tradable;
- strategy allowed;
- wallet allowed;
- size within limits;
- exposure after fill within limits;
- no duplicate intent;
- no stale market snapshot;
- no blocked jurisdiction/compliance failure;
- no kill switch.

### D. Order Builder
Преобразует внутренний intent в exchange-specific order payload.

### E. Submitter
Отправка, retry policy, idempotency key, timeout handling.

### F. Lifecycle Tracker
Следит за:
- order accepted/rejected;
- partial fills;
- open order aging;
- cancel/replace;
- stale open order cleanup.

### G. Position Reconciler
Периодически сверяет локальное состояние с exchange state.

## Типы исполнения

### 1. Dry-run
Ничего не отправляет в Polymarket, только прогоняет валидации и оценивает:
- theoretical fill;
- exposure delta;
- expected fee;
- risk impact.

### 2. Paper mode
Ведет симулированную книгу сделок на основе реальных market snapshots.

### 3. Live mode
Отправляет реальные ордера.

## Risk checks

Минимальный набор:

- max order notional;
- max market exposure;
- max event exposure;
- max strategy exposure;
- max wallet exposure;
- max correlated exposure;
- min liquidity threshold;
- max spread threshold;
- max slippage threshold;
- cool-down after stop loss;
- daily realized loss stop;
- daily submitted notional cap.

## Ошибки и edge cases

Execution Engine обязан корректно обрабатывать:

- slug найден, но рынок уже закрыт;
- token IDs устарели;
- spread слишком широкий;
- order partially filled;
- order ack получен, но локальная запись не сохранилась;
- сеть недоступна;
- rate limit / throttling;
- insufficient balance;
- allowance / gas / funder mismatch;
- duplicate submit after timeout;
- reconnect and resync after crash.

## Idempotency model

Каждый intent должен иметь:
- `intent_id`
- `client_order_id`

Повторная подача того же intent:
- не должна создавать второй независимый ордер,
- пока первый статус не выяснен.

## Хранилища

### Tables / collections
- `trade_intents`
- `execution_results`
- `open_orders`
- `fills`
- `positions`
- `audit_events`
- `wallet_balances`
- `market_snapshots`

## CLI команды

```text
pm exec dry-run --market <slug> --side yes --price 0.62 --size 10
pm exec buy --market <slug> --side yes --price 0.62 --size 10 --wallet main
pm exec sell --market <slug> --side no --price 0.41 --size 8 --wallet hedge
pm exec cancel --order <id>
pm exec cancel-market --market <slug>
pm exec status --order <id>
pm exec reconcile --wallet main
pm exec kill-switch on
pm exec kill-switch off
```

## Security requirements

- приватные ключи не логируются;
- order payload логируется без чувствительных секретов;
- dry-run по умолчанию в dev;
- live mode требует явного подтверждения/флага;
- multi-wallet подпись изолирована;
- секреты не должны быть доступны AI-слою.

## MVP definition

MVP считается готовым, если модуль умеет:

1. получить рынок по slug;
2. извлечь YES/NO token IDs;
3. получить best bid/ask;
4. сделать dry-run;
5. отправить buy/sell limit order;
6. отменить ордер;
7. записать audit trail;
8. выдержать повторный запуск без потери состояния.

## Phase 2 expansion

- replace logic;
- partial fill management;
- advanced time-in-force;
- batched intents;
- portfolio-aware pricing guards;
- automatic resync on reconnect.
