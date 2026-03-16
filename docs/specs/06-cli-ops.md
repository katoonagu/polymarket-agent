# 06 — CLI, Storage, Observability & Operations Spec

## Назначение

Управление системой начинается с CLI. Это правильно для v1, потому что:

- быстро разрабатывать;
- легко аудировать команды;
- меньше surface area, чем у веб-панели;
- проще накладывать операционные ограничения;
- легко подключить later TUI or web console.

## CLI design principles

### 1. Verb-first grammar
Команды должны быть читаемыми:

```text
pm market watch add ...
pm wallet copy enable ...
pm exec buy ...
pm arkham enrich ...
```

### 2. Dry-run by default where possible
Любая опасная операция должна поддерживать:
- `--dry-run`
- `--confirm`
- `--json`

### 3. Deterministic output
CLI должен уметь печатать:
- human view;
- machine view (JSON).

### 4. Auditability
Каждая команда должна логироваться с:
- actor
- timestamp
- params hash
- result
- side effects

## Основные CLI namespace

### `pm market`
Работа с рынками, watchlists, snapshots, alerts.

### `pm wallet`
Работа с адресами, статистикой, copy configs.

### `pm arkham`
Обогащение адресов, графы, dossiers, alerts.

### `pm strategy`
Стратегии, сигналы, approve/reject.

### `pm exec`
Dry-run/live execution, order status, cancel.

### `pm risk`
Лимиты, kill switches, exposure tables.

### `pm ops`
Health, metrics, reconciliation, replay, incidents.

## Пример командного набора

```text
pm market search --query "btc 15 min"
pm market show --slug <slug>
pm market event --slug <slug>
pm market book --token-id <id>
pm market price --token-id <id>
pm market watch add --slug btc-updown-15m-...
pm wallet add --address 0x...
pm wallet copy enable --address 0x... --mode fixed --size 1
pm arkham enrich --address 0x...
pm strategy list
pm exec dry-run --market <slug> --side yes --price 0.57 --size 5
pm exec buy --market <slug> --side yes --price 0.57 --size 5 --confirm
pm risk exposure
pm ops health
pm ops replay --from 2026-02-17T00:00:00Z --to 2026-02-17T12:00:00Z
```

## Storage requirements

### Core database
Postgres preferred.

### Cache / queue
Redis for:
- recent snapshots;
- transient locks;
- idempotency windows;
- work queues.

### Event log
Append-only log for:
- signals;
- approvals;
- trade intents;
- execution events;
- fills;
- reconciliations;
- alerts.

## Suggested database model

### Core tables
- `markets`
- `market_snapshots`
- `wallet_profiles`
- `wallet_events`
- `strategies`
- `signals`
- `candidate_intents`
- `trade_intents`
- `orders`
- `fills`
- `positions`
- `alerts`
- `audit_events`
- `risk_limits`

### Optional later
- `clusters`
- `entities`
- `news_briefs`
- `semantic_relationships`

## Observability

### Structured logging
Минимум:
- `timestamp`
- `module`
- `correlation_id`
- `intent_id`
- `wallet_id`
- `market_slug`
- `event_type`
- `status`
- `latency_ms`

### Metrics
- order submit latency
- market snapshot latency
- websocket reconnect count
- rate-limit events
- copied trades count
- skipped trades count
- rejected intents count
- pnl by strategy
- exposure by topic
- spread filter hit rate

### Alerts
- execution failure burst
- position reconciliation mismatch
- stale market data
- wallet monitor lag
- Arkham enrichment failure
- daily loss threshold breach
- kill switch activated

## Replay and postmortem

Обязательный операционный режим:
- восстановить состояние на timestamp T;
- понять, какие сигналы пришли;
- какие проверки прошли/не прошли;
- какой ордер был отправлен;
- какой fill получен;
- почему позиция осталась открытой или была пропущена.

### Для этого нужно хранить
- market snapshots
- signal history
- candidate intents
- approvals
- execution events
- final position state

## Risk console in CLI

```text
pm risk exposure
pm risk exposure --by strategy
pm risk exposure --by wallet
pm risk limits show
pm risk limits set --market-cap 25
pm risk kill-switch on
pm risk kill-switch off
pm risk daily-stop show
```

## Incident operations

### Types of incidents
- duplicate execution
- stale data execution
- missed cancel
- overexposure
- wallet misclassification
- replay mismatch
- rate-limit degradation
- websocket data gap

### Incident workflow
1. detect
2. freeze or scope-limit
3. reconcile
4. produce postmortem
5. patch rule/spec
6. replay affected window

## MVP definition

CLI/ops считается готовым, если:

1. все боевые функции доступны из CLI;
2. есть JSON output mode;
3. есть audit trail;
4. есть risk console;
5. есть replay;
6. kill switch работает глобально и на уровне стратегии;
7. можно понять, что произошло после сбоя.

## Phase 2 expansion

- TUI dashboard;
- web control panel;
- role-based access;
- scheduled jobs UI;
- alert routing in Slack/Telegram/Discord.
