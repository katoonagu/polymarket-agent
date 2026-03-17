# 03 — Copy Trading & Wallet Intelligence Spec

## Назначение

Этот модуль следит за выбранными кошельками и преобразует их публичную активность в:

- наблюдение;
- статистику;
- candidate intents;
- copy-trade intents;
- risk-scored wallet profiles.

Он объединяет два режима:

1. **Wallet Intelligence** — аналитика по адресам;
2. **Copy Trading** — ограниченное воспроизведение сделок целевых адресов.

## Главный принцип

Сигнал от чужого кошелька **никогда не должен автоматически обходить risk policy**.

Кошелёк — это источник сигнала, а не authority.

## Типы целевых кошельков

### A. Manual wallets
Оператор вручную добавил адрес.

### B. Smart wallets
Кошельки с исторической результативностью, но без сильной уверенности в причине результата.

### C. Insider-risk wallets
Кошельки с подозрительным паттерном:
- узкая тематическая специализация;
- сверхточные входы;
- новые адреса;
- связанное фондирование;
- синхронная активность.

### D. Decoy / ignore wallets
Адреса, которые выглядят шумно или используются как отвлечение.

## Объекты

### WalletProfile
- `wallet_address`
- `wallet_alias`
- `source` (manual, discovered, imported)
- `classification`
- `status` (active, paused, ignored)
- `notes`
- `created_at`

### WalletStats
- total trades
- win rate
- realized pnl
- avg entry price deviation
- avg holding time
- categories traded
- concentration score
- burst activity score
- freshness score

### CopyConfig
- sizing mode
- fixed size / percentage / portfolio-weighted
- per-trade cap
- per-market cap
- daily cap
- price range filter
- slippage cap
- entry-only / entry+exit
- follow averaging down: yes/no
- follow scaling out: yes/no
- cool-down after copied loss
- max simultaneous copied positions

## Detection pipeline

### 1. Activity ingestion
Собираем публичную активность целевого кошелька.

### 2. Event classification
Классифицируем событие:
- new trade;
- add to position;
- reduce position;
- close;
- hedge;
- noise.

### 3. Deduplication
Одна и та же сделка не должна копироваться дважды.

### 4. Intent generation
Превращаем событие кошелька в candidate intent.

### 5. Policy gate
Прогоняем через risk policy.

### 6. Execution
Если разрешено — создаем trade intent для execution engine.

## Подмодули

### A. Wallet Registry
Хранит список кошельков, статусы, теги, alias, whitelist/blacklist.

### B. Wallet Monitor
Следит за activity/trades/positions.

### C. Wallet Scorer
Считает качество кошелька:
- edge stability;
- topic specialization;
- risk-adjusted score;
- similarity to other wallets;
- latency tolerance.

### D. Copy Translator
Преобразует сделку кошелька в нашу сделку.

### E. Exposure Guard
Запрещает копитрейдинг, если:
- рынок уже переполнен;
- цена ушла слишком далеко;
- размер не соответствует лимитам;
- позиция конфликтует с нашей стратегией.

## Схемы sizing

### 1. Fixed
Каждая copied trade = фиксированная сумма.
Лучший режим для MVP.

### 2. Percentage
Берем процент от текущего доступного капитала.

### 3. Portfolio-weighted
Повторяем относительную нагрузку на портфель трейдера.

## Рекомендуемый порядок запуска

### MVP
- Fixed only
- Entry-only
- Hard per-trade cap
- Hard per-market cap
- Hard daily cap
- No martingale / no averaging-down follow

### Later
- percentage sizing
- exit following
- partial close tracking
- portfolio-weighted mode
- confidence-weighted wallet allocation

## Anti-blowup rules

- не копировать более N сделок в минуту с одного адреса;
- не копировать averaging down без отдельного флага;
- не копировать late entries выше configured drift threshold;
- не копировать illiquid markets;
- не копировать при spread > threshold;
- не копировать новый кошелёк без quarantine period;
- не копировать закрытие позиции без уверенности, что это именно close, а не hedge rotation.

## Wallet scoring ideas

### Signal quality
- стабильность win rate;
- число независимых рынков;
- средний edge after fees;
- нет ли “одного lucky run”.

### Execution friendliness
- торгует ли кошелёк в ликвидных рынках;
- как часто заходит слишком рано/слишком поздно;
- можно ли копировать маленьким капиталом.

### Suspicion / anomaly
- слишком узкий набор событий;
- новые кошельки без истории;
- синхронное фондирование;
- coordinated entries;
- highly concentrated profits from few geopolitical markets.

## CLI команды

```text
pm wallet add --address <0x...> --alias <name>
pm wallet pause --address <0x...>
pm wallet stats --address <0x...>
pm wallet watch list
pm wallet copy enable --address <0x...> --mode fixed --size 1
pm wallet copy disable --address <0x...>
pm wallet copy config --address <0x...>
pm wallet activity --address <0x...>
pm wallet signal review --address <0x...>
```

## Хранилища

- `wallet_profiles`
- `wallet_stats`
- `wallet_events`
- `wallet_copy_configs`
- `wallet_copy_runs`
- `wallet_signal_candidates`
- `wallet_relationships`

## Особые режимы

### Quarantine mode
Новый кошелёк сначала только наблюдается, без торговли.

### Shadow mode
Система считает, что бы она скопировала, но не торгует.

### Approved mode
Кошелёк допущен к live copy-trading.

## MVP definition

Готово, если модуль умеет:

1. добавить кошелёк в реестр;
2. читать его activity;
3. определить новое торговое действие;
4. дедуплицировать событие;
5. рассчитать fixed copy size;
6. проверить per-trade / per-market caps;
7. создать trade intent для execution engine;
8. вести статистику по copied vs skipped trades.

## Phase 2 expansion

- multi-wallet allocator;
- wallet clustering;
- similarity graph;
- exit inference;
- strategy attribution by wallet;
- public leaderboard import;
- confidence decay over time.

## Read-Only Addendum (Current Phase)

This branch only implements the read-only foundation for the wallet module. The current scope is intentionally narrower than the full copy-trading vision above.

### Implemented now

- Local tracked-wallet registry at `.pm/state/wallets.json`
- Registry metadata:
  - `address`
  - `label`
  - `tags`
  - `note`
  - `added_at`
- Read-only wallet inspection commands:
  - `pm wallet add`
  - `pm wallet list`
  - `pm wallet remove`
  - `pm wallet discover leaderboard`
  - `pm wallet discover holders`
  - `pm wallet summary`
  - `pm wallet trades`
  - `pm wallet activity`
  - `pm wallet positions`
  - `pm wallet score`
  - `pm wallet rank tracked`
  - `pm wallet compare`
  - `pm wallet snapshot`
- Shadow intelligence built only from the existing public Data API client
- Non-mutating wallet discovery from:
  - the public trader leaderboard
  - public market holder data
- Deterministic wallet scoring with transparent components and weights:
  - `leaderboard_component = 0.25`
  - `realized_performance_component = 0.35`
  - `activity_component = 0.20`
  - `footprint_component = 0.20`

### Explicitly not implemented now

- wallet auth or signing
- live wallet management
- polling daemons
- live copy-trading
- order generation
- execution coupling
- database-backed wallet state

### Current summary contract

`pm wallet summary --address <0x...>` aggregates:

- tracked metadata from the local registry
- holdings value
- traded count
- current positions count
- closed positions count
- recent trades
- recent activity

`pm wallet snapshot` is compact and registry-ordered. It returns per-wallet metadata, holdings value, traded count, current positions count, closed positions count, and structured partial errors when a public sub-call fails.

`pm wallet discover` is non-mutating. It returns candidate wallets from public holder and leaderboard reads, preserves deterministic order, and includes local tracked-wallet metadata when the candidate is already in the registry.

`pm wallet score --address <0x...>` works for any valid public address. The score is deterministic and explainable:

- leaderboard rank contributes `25%`
- realized PnL across closed positions contributes `35%`
- traded-count activity contributes `20%`
- current footprint contributes `20%`

Legitimate no-data cases score as available zeroes. Real request or payload failures are returned as structured partial errors and are excluded from the available-weight denominator.

`pm wallet rank tracked` scores and ranks all tracked wallets with deterministic tie-breaks. `pm wallet compare` preserves left/right input order and returns the winner, score delta, and per-component deltas without mutating the local registry.
