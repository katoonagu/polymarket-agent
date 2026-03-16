# 04 — Arkham Intelligence Spec

## Назначение

Arkham module — это **on-chain intelligence layer**, который помогает:

- обогащать адреса сущностями и тегами;
- искать связанные адреса;
- отслеживать funding patterns;
- строить counterparty graph;
- выявлять unusual flows;
- давать operator-у evidence pack по подозрительным кошелькам.

Этот модуль **не должен** напрямую открывать сделки без policy gate.

## Почему он нужен

Polymarket публичен на блокчейне, но “один адрес = один игрок” — почти всегда неверное допущение.

Нужен отдельный слой, который отвечает на вопросы:

- этот адрес изолирован или связан с другими?
- кто его фондировал?
- есть ли повторяющиеся counterparties?
- совпадает ли всплеск on-chain activity со ставками на Polymarket?
- это известная entity, prediction, cluster или непонятный адрес?

## Главный принцип

Arkham возвращает **вероятностную атрибуцию**, а не абсолютную истину.

Поэтому любой результат модуля должен хранить:
- confidence;
- provenance;
- freshness;
- human note.

## Целевые use cases

### 1. Address enrichment
Оператор вводит адрес, модуль возвращает:
- labels;
- entities;
- tags;
- known counterparties;
- portfolio hints.

### 2. Funding chain analysis
Находим:
- кто фондировал кошелёк;
- с каких бирж/мостов пришли средства;
- есть ли совпадения с другими наблюдаемыми адресами.

### 3. Suspicious cluster detection
Если несколько адресов:
- созданы недавно;
- финансируются связанно;
- торгуют одну и ту же тему;
- входят почти синхронно,

то модуль помечает их как cluster candidate.

### 4. Event-correlated surveillance
Смотрим, что происходило on-chain:
- за X часов до входа;
- за Y часов после выхода;
- вокруг ключевых геополитических окон.

### 5. Manual investigation notebook
Оператор вручную исследует адрес и сохраняет dossier.

## Подмодули

### A. Address Enricher
Обогащает адрес:
- labels;
- entities;
- confidence;
- risk notes;
- historical summary.

### B. Counterparty Graph
Строит граф:
- address -> counterparties
- address -> entities
- entity -> related flows
- cluster -> funding sources

### C. Flow Watcher
Следит за:
- inbound transfers;
- outbound transfers;
- swap activity;
- sudden funding spikes.

### D. Cluster Builder
Собирает candidate clusters по эвристикам:
- common funder;
- time proximity;
- same market timing;
- same topic concentration;
- same off-ramp / bridge patterns.

### E. Dossier Generator
Собирает краткое заключение по адресу или группе адресов:
- что известно;
- почему адрес интересен;
- что подтверждено;
- что является лишь гипотезой.

## Data model

### ArkhamEntityRecord
- `entity_id`
- `entity_name`
- `entity_type`
- `confidence`
- `source_timestamp`
- `notes`

### ArkhamAddressRecord
- `address`
- `labels`
- `predicted_labels`
- `entity_links`
- `confidence_summary`
- `last_enriched_at`

### SuspiciousCluster
- `cluster_id`
- `member_addresses`
- `shared_funders`
- `shared_counterparties`
- `time_correlation_score`
- `market_overlap_score`
- `confidence`
- `status` = hypothesis / reviewed / approved / rejected

## Важные проектные ограничения

### 1. Не auto-trade only on Arkham
Любой “insider-like” сигнал:
- noisy;
- вероятностный;
- юридически и этически чувствительный.

Поэтому Arkham сигнал должен быть одним из факторов, а не trigger без проверки.

### 2. Separate facts from hypotheses
Нужно хранить отдельно:
- **verified intelligence**
- **predicted label**
- **heuristic suspicion**
- **operator comment**

### 3. Evidence-first UX
Для каждого suspicious flag должна быть трассировка:
- какие адреса связаны;
- какой funder общий;
- какие transfers совпали;
- какие рынки торговались;
- какой confidence.

## Suspicion scoring

Примерный скоринг:

- +30: общий funder с известным cluster
- +20: синхронное пополнение перед входом
- +15: новая история кошелька + узкая тема
- +15: аномально высокая точность на few markets
- +10: counterparties overlap
- +10: bridge/exchange overlap
- -20: длинная разнообразная история торгов
- -15: сигнал устарел
- -10: нет market overlap

Итог:
- 0–29 low
- 30–59 medium
- 60–79 high
- 80+ review now

## Outputs

### 1. Intelligence Alert
- address
- label summary
- suspicion score
- cluster id if any
- key reasons
- freshness
- suggested action

### 2. Dossier
Markdown/JSON объект:
- executive summary
- addresses
- entities
- counterparty notes
- flow chronology
- linked markets
- operator notes
- review status

### 3. Strategy Input
Ограниченный формат для strategy layer:
- signal type
- confidence
- affected addresses
- affected markets
- recommended watchlist addition
- no direct trade command

## CLI команды

```text
pm arkham enrich --address <0x...>
pm arkham graph --address <0x...>
pm arkham flow --address <0x...> --hours 72
pm arkham cluster build --address <0x...>
pm arkham dossier --address <0x...>
pm arkham review --cluster <id>
pm arkham watch add --address <0x...>
pm arkham alerts
```

## Хранилища

- `arkham_address_cache`
- `arkham_entity_cache`
- `arkham_flows`
- `arkham_counterparties`
- `arkham_clusters`
- `intelligence_alerts`
- `intelligence_dossiers`

## MVP definition

MVP готов, если модуль умеет:

1. обогащать адрес;
2. кэшировать результат;
3. строить простой counterparty view;
4. собирать suspicious score по набору эвристик;
5. генерировать dossier;
6. передавать только alert в strategy/orchestrator.

## Phase 2 expansion

- websocket flow monitoring;
- incremental graph updates;
- cluster comparison;
- alert subscriptions;
- automatic market correlation reports;
- entity-level portfolio tracking.
