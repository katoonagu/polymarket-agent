# Polymarket Agent Blueprint

## Цель

Собрать **модульного торгового агента для Polymarket**, который:

1. умеет **безопасно и детерминированно** исполнять торговые действия;
2. умеет **собирать, нормализовать и наблюдать** рынки, кошельки и сигналы;
3. умеет работать в режиме **CLI-first**;
4. допускает **ручные сигналы**, **правила стратегии**, а позже — **AI-слой** для исследований и генерации гипотез;
5. может быть поэтапно развит через **Codex + AGENTS.md + Skills + automations**.

## Главный принцип

Не смешивать:

- **execution** — то, что ставит ордера и двигает деньги;
- **intelligence** — то, что ищет сигналы и предлагает идеи;
- **policy/risk** — то, что решает, разрешена ли конкретная сделка;
- **ops** — логирование, мониторинг, аудит, алерты, replay, paper trading.

Это ключевое архитектурное решение. Иначе система быстро превращается в неуправляемый комбайн, где нельзя понять, почему был открыт риск.

## Почему именно так

Для Polymarket основной технический риск — не “написать модель”, а:

- корректно получать market/event/token data;
- правильно работать с order lifecycle;
- выдерживать rate limits;
- не путать displayed price, best bid/ask, last trade и midpoint;
- правильно обрабатывать partial fills, cancel/replace, idempotency;
- контролировать риск по рынку, кошельку, теме и времени;
- отделить исследовательские гипотезы от боевого исполнения.

## Логическая схема

```text
[CLI / Manual Commands]
          |
          v
[Orchestrator / Decision Policy]
    |           |            |
    |           |            |
    v           v            v
[Execution] [Market Intel] [Wallet / Arkham Intel]
    |           |            |
    |           |            |
    v           v            v
[Polymarket] [Polymarket] [Polymarket + Arkham]
    |
    v
[State Store + Audit Log + Metrics]
```

## Целевые режимы работы

### 1. Manual-first
Оператор руками добавляет рынок, кошелёк, правило или ордерную задачу. Система только исполняет, валидирует и логирует.

### 2. Rule-based
Сделка рождается из детерминированного набора правил:
- копировать адрес;
- покупать при достижении диапазона цены;
- ставить лимит на событие из watchlist;
- не превышать лимит риска.

### 3. Analyst mode
Система собирает сигналы и выдает:
- watchlist;
- suspicious wallet alerts;
- event briefs;
- recommended actions;
- confidence score.

### 4. Semi-auto
Система предлагает сделку, но перед исполнением нужен human approval.

### 5. Full-auto
Допустим только после paper trading, replay и стабильных risk guards.

## Стратегические блоки

### A. Execution kernel
Самый важный модуль. Он должен быть production-grade раньше любых “умных” агентов.

### B. Market intelligence
Поиск событий, токенов, цен, orderbook, crypto feeds, watchlists, наблюдение за избранными рынками.

### C. Wallet intelligence / copy trading
Наблюдение за адресами, activity feed, trade mirroring, sizing, cooldowns, deduplication.

### D. Arkham intelligence
Слежение за связанными адресами, entity attribution, funding paths, suspicious flows, counterparty patterns.

### E. Strategy engine
Правила, конфиги, сценарии, ручные сигналы, later AI prompts.

### F. Orchestration and policy
Сводит всё вместе и отвечает на вопрос: “можно ли сейчас открыть именно этот риск?”

## Рекомендуемая последовательность разработки

### Phase 0 — Specifications
Подготовить все README/spec, словарь сущностей, CLI grammar, state model, risk model.

### Phase 1 — Execution MVP
- auth;
- load market by slug/id;
- fetch token IDs;
- get best bid/ask;
- place/cancel order;
- dry-run;
- audit log;
- exposure limits.

### Phase 2 — Market ingestion
- market discovery;
- watchlists;
- websocket market feed;
- polling fallback;
- selected market pool.

### Phase 3 — Replay / paper trading
- event log;
- order simulation;
- replay by timestamp;
- metrics;
- acceptance tests.

### Phase 4 — Copy trading
- follow wallet;
- detect new trades;
- mirror with fixed caps;
- entry-only mode;
- optional close-follow mode.

### Phase 5 — Arkham module
- entity enrichment;
- address clustering;
- suspicious funding alerts;
- confidence scoring;
- human-review workflow.

### Phase 6 — Strategy portfolio
- strategy configs;
- scheduler;
- voting/priority;
- portfolio allocation by strategy.

### Phase 7 — AI analyst layer
- market brief generation;
- contradiction detection;
- event summarization;
- rule proposal;
- human-in-the-loop.

## Минимальный стек

- **Language**: Python or TypeScript; для CLI-first и аналитики Python удобнее, для rich SDK/infra тоже допустим TS.
- **Storage**: Postgres + Redis.
- **Event log**: append-only trade/event log.
- **Observability**: Prometheus/Grafana or simple structured logs + dashboards.
- **Config**: YAML/TOML strategy files + env secrets.
- **Secrets**: отдельный secrets manager, не в репозитории.
- **Testing**: unit + integration + replay tests.

## Что не делать в v1

- Не начинать с “LLM сам решает, что купить”.
- Не смешивать live trading и research notebooks.
- Не запускать multi-wallet routing без общего risk allocator.
- Не делать auto-trade только на одном сигнале “подозрительный кошелёк”.
- Не строить сразу и copy-trading, и market making, и microstructure BTC, и geopolitical insider bot в одном релизе.

## Рекомендуемый первый продукт

Самый рациональный v1:

1. **Execution engine**
2. **Market/watchlist module**
3. **Copy-trading module c жесткими лимитами**
4. **Paper trading + replay**
5. Потом — **Arkham intelligence** как alerting-система, а не как автотрейдер

## Suggested repository layout

```text
/docs
  /specs
    README.md
    01-execution-engine.md
    02-market-intel.md
    03-copytrading-wallet-intel.md
    04-arkham-intel.md
    05-strategy-orchestrator.md
    06-cli-ops.md
    07-codex-workflow.md

/app
  /execution
  /market_intel
  /wallet_intel
  /arkham_intel
  /strategy
  /orchestrator
  /cli
  /storage
  /ops

/tests
  /unit
  /integration
  /replay
```

## Acceptance criteria для программы в целом

Система считается готовой к limited live use, если:

- execution module умеет открывать/отменять ордера и восстанавливаться после сбоя;
- risk policy гарантирует, что стратегия не откроет риск выше лимита;
- все решения и ордера аудируются;
- есть dry-run и paper mode;
- есть replay для инцидентов;
- copy-trading не ломается на burst activity;
- Arkham module не создает auto-trades без policy gate;
- operator может управлять всем из CLI.

## Документы в этом пакете

- `01-execution-engine.md`
- `02-market-intel.md`
- `03-copytrading-wallet-intel.md`
- `04-arkham-intel.md`
- `05-strategy-orchestrator.md`
- `06-cli-ops.md`
- `07-codex-workflow.md`
