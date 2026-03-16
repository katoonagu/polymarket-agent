# 07 — Codex Workflow Spec

## Назначение

Codex здесь используется не как торговый агент, а как **агент разработки**:

- пишет и правит код;
- помогает поддерживать архитектурную дисциплину;
- запускает стандартизированные workflows;
- ускоряет разбиение задачи на модули;
- помогает держать репозиторий в консистентном состоянии.

## Главный принцип

**Codex не должен быть production execution runtime.**

Он должен помогать строить систему, но live-торговля должна идти через ваш собственный deterministic runtime.

## Что положить в репозиторий сразу

### 1. `AGENTS.md`
Это главный файл правил для Codex.

Он должен фиксировать:
- архитектурные границы модулей;
- кодстайл;
- правила тестирования;
- структуру каталогов;
- запрет на хранение секретов;
- обязательность dry-run/replay тестов;
- запрет на прямой вызов execution из AI-модулей.

### 2. `docs/specs/*.md`
Текущие спецификации.

### 3. `TODO.md` / `ROADMAP.md`
Крупные этапы.

### 4. `skills/`
Набор task-specific skills для Codex.

## Рекомендуемые Skills

### Skill 1 — Add new Polymarket adapter
Что должен делать:
- добавить client wrapper;
- описать config;
- добавить unit tests;
- обновить docs.

### Skill 2 — Add CLI command
Что должен делать:
- создать команду;
- добавить help text;
- добавить JSON mode;
- обновить command reference.

### Skill 3 — Add strategy skeleton
Что должен делать:
- создать strategy definition;
- добавить config schema;
- добавить dummy signal path;
- написать tests.

### Skill 4 — Add replay test
Что должен делать:
- взять event log fixture;
- воспроизвести сценарий;
- сравнить expected and actual outcomes.

### Skill 5 — Add integration contract
Что должен делать:
- описать interface между модулями;
- зафиксировать input/output schema;
- обновить docs/spec.

## Рекомендуемый `AGENTS.md` каркас

```text
- Do not mix execution logic with strategy research code.
- Any change to live trading flow must include replay/integration tests.
- Never print secrets or private keys.
- All CLI commands must support --help and JSON output when reasonable.
- New modules require a spec file under docs/specs/.
- Strategy modules produce signals; only execution module places orders.
- Prefer small, testable adapters over monolithic service classes.
```

## Multi-agent режим

Полезно использовать параллельных агентов для:

- чтения документации;
- генерации адаптеров;
- написания тестов;
- проектирования схем БД;
- написания CLI команд;
- обновления docs/spec.

### Recommended agent roles
- `docs-agent`
- `execution-agent`
- `market-agent`
- `wallet-agent`
- `arkham-agent`
- `qa-agent`

## Automations

Хорошие автоматизации для проекта:

### 1. Spec drift checker
Проверяет, не ушёл ли код от спецификации.

### 2. CLI surface checker
Собирает список доступных команд и сравнивает с docs.

### 3. Replay regression
Запускает набор replay fixtures после изменений в execution/strategy.

### 4. Risk contract audit
Проверяет, что ни один модуль кроме execution не имеет права ставить ордера.

### 5. Changelog / release notes
Автоматически собирает изменения по модульным зонам.

## Workflow по фазам

### Phase 0 — Docs first
Codex помогает:
- разложить документы;
- сформировать interfaces;
- сделать initial schemas.

### Phase 1 — Execution first
Codex делает:
- adapters;
- auth wrappers;
- order lifecycle tests;
- dry-run CLI.

### Phase 2 — Market intel
Codex делает:
- watchlists;
- snapshot services;
- recurring market resolver.

### Phase 3 — Wallet copy
Codex делает:
- activity ingestion;
- dedupe;
- copy translator;
- limits.

### Phase 4 — Arkham
Codex делает:
- enrichment adapter;
- cache layer;
- dossier generator;
- scoring heuristics.

### Phase 5 — Orchestrator
Codex делает:
- signal bus;
- policy gate;
- approval workflows.

## Definition of done for Codex-driven tasks

Любой PR/task считается завершённым, если:

- есть код;
- есть тесты;
- обновлены спецификации;
- нет нарушения архитектурных границ;
- новые CLI команды документированы;
- replay suite не сломан.

## Anti-patterns

- “пусть Codex сам решит архитектуру на лету”
- “сначала напишем код, потом задокументируем”
- “дадим AI-модулю доступ к execution secrets”
- “сделаем один гигантский bot.py”
- “смешаем paper/live режим в одном сервисе без границ”

## MVP definition

Codex workflow готов, если:

1. в репозитории есть `AGENTS.md`;
2. есть skill-пакеты под типовые задачи;
3. CI умеет запускать replay/integration tests;
4. docs/spec обновляются как часть стандартного workflow;
5. multi-agent режим используется для параллельных подзадач, а не для live-trading.
