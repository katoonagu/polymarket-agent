# 05 — Strategy Engine & Orchestrator Spec

## Назначение

Strategy Engine генерирует торговые идеи.
Orchestrator решает, что из них можно превратить в live intent.

Именно здесь должно происходить разделение между:

- “интересно”
- “наблюдаем”
- “разрешено к торговле”
- “исполняем сейчас”

## Почему это критично

Без Orchestrator система превращается в набор автономных модулей, каждый из которых считает себя правым:
- copy module хочет копировать;
- AI analyst хочет открыть новую идею;
- operator вручную добавляет ещё один сигнал;
- Arkham module поднимает suspicious alert.

Нужен один центр policy arbitration.

## Уровни стратегии

### Level 0 — Manual
Оператор задаёт конкретную сделку.

### Level 1 — Rule-based
Простые правила:
- price in range;
- wallet entered;
- market is active;
- spread <= max;
- position size <= cap.

### Level 2 — Composite
Несколько условий:
- wallet signal + market liquidity + event freshness;
- Arkham alert + manual approval;
- recurring BTC signal + microstructure filter.

### Level 3 — AI-assisted
LLM анализирует:
- рынок;
- связанные события;
- новости;
- комментарии;
- watchlist context.

Но результатом всё равно должен быть структурированный signal, а не свободный текст.

## Сущности

### StrategyDefinition
- `strategy_id`
- `name`
- `mode` = manual / rules / ai-assisted
- `status` = active / paused / shadow
- `markets_scope`
- `wallet_scope`
- `risk_profile`
- `approval_policy`
- `priority`
- `cooldown_rules`

### Signal
- `signal_id`
- `source_module`
- `strategy_id`
- `signal_type`
- `market_slug`
- `side`
- `confidence`
- `reasoning_summary`
- `expires_at`

### CandidateIntent
Это уже почти сделка, но ещё не execution:
- signal data
- proposed size
- proposed price
- wallet
- urgency
- risk score
- approval requirement

## Подмодули

### A. Strategy Registry
Реестр стратегий, версий и статусов.

### B. Signal Bus
Единый intake для сигналов от:
- manual CLI;
- market intel;
- copy-trading;
- Arkham;
- AI analyst.

### C. Signal Evaluator
Оценивает signal:
- не устарел ли;
- есть ли рынок;
- есть ли конфликт;
- соответствует ли области действия стратегии.

### D. Portfolio Allocator
Решает:
- какой кошелёк использовать;
- какой размер выделить;
- не конфликтует ли новая позиция с существующими.

### E. Approval Gate
Режимы:
- auto
- manual
- dual confirmation
- shadow only

### F. Conflict Resolver
Например:
- strategy A хочет BUY YES
- strategy B хочет BUY NO
- copy module уже открыл similar exposure

Нужен единый policy:
- reject
- reduce size
- hedge
- queue
- ask human

## Рекомендуемые первые стратегии

### Strategy A — Manual trader
Все действия идут вручную, но через execution policy.

### Strategy B — Smart wallet copier
Только fixed size, only-entry, tight caps.

### Strategy C — BTC recurring watcher
Следит за 15m рынком, но сначала только watch/alert, не auto-trade.

### Strategy D — Arkham suspicious alert
Только создаёт watchlist и human review task.

## Что не делать в v1

- Не использовать LLM для final price selection.
- Не давать модели прямой доступ к execution secrets.
- Не объединять все сигналы в “black-box score”, который нельзя объяснить.
- Не делать dynamic sizing без жёстких потолков.

## Decision states

Для каждого signal/candidate:

- OBSERVE
- ENRICH
- WAIT
- APPROVE
- REJECT
- EXECUTE
- CANCEL
- ESCALATE_TO_HUMAN

## Пример policy

```text
IF source = wallet_copy
AND wallet_status = approved
AND market_spread <= 0.03
AND copy_price_drift <= 0.02
AND market_exposure_after_trade <= cap
THEN candidate_intent = APPROVED_AUTO
ELSE candidate_intent = REJECTED or HUMAN_REVIEW
```

## Пример composite policy

```text
IF source = arkham_alert
AND suspicion_score >= 70
THEN add_to_watchlist
AND require manual review
AND prohibit direct auto-trade
```

## Аллокация по кошелькам

Orchestrator должен уметь:

- выбрать wallet pool;
- исключить paused wallets;
- применить wallet-specific caps;
- избежать концентрации одной стратегии в одном кошельке;
- учитывать already-open exposure.

## CLI команды

```text
pm strategy list
pm strategy show --id <strategy>
pm strategy pause --id <strategy>
pm strategy resume --id <strategy>
pm strategy signal review --id <signal>
pm strategy approve --id <candidate>
pm strategy reject --id <candidate>
pm strategy alloc show
pm strategy alloc rebalance --dry-run
```

## Хранилища

- `strategies`
- `strategy_versions`
- `signals`
- `candidate_intents`
- `approval_decisions`
- `portfolio_allocations`
- `strategy_metrics`

## MVP definition

MVP готов, если система умеет:

1. регистрировать несколько стратегий;
2. принимать signal из разных модулей;
3. проверять approval policy;
4. решать конфликт сигналов;
5. строить candidate intent;
6. передавать только approved intent в execution engine;
7. логировать причину каждого reject/approve.

## Phase 2 expansion

- probabilistic portfolio allocation;
- confidence decay;
- strategy voting;
- event-topic exposure graph;
- AI-generated market briefs;
- auto-suggested rules from analyst mode.
