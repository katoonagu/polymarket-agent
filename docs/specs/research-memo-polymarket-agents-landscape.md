# Research memo  
## Ландшафт Polymarket agents  
**Тема:** copy bots, smart-wallet trackers, crypto interval bots, maker/reward bots, research/semantic agents, surveillance tools  
**Дата:** 2026-03-16  
**Формат:** market + technical memo

---

## 0) Executive summary

Ландшафт Polymarket-агентов уже нельзя описывать как один рынок “ботов для ставок”. На практике это **шесть разных сегментов**, которые используют одни и те же базовые примитивы Polymarket — **Gamma API** для discovery рынков, **Data API** для позиций/сделок/активности/leaderboards и **CLOB API + WebSocket** для стакана и исполнения ордеров.[1][2][4]

**Ключевой тезис:** самый зрелый и коммерчески понятный слой — это не “умные AI-трейдеры”, а **execution + wallet intelligence**:
- **copy bots** и **smart-wallet trackers** уже имеют понятную упаковку, UX и risk-settings;
- **crypto interval bots** — самая насыщенная open-source ниша, потому что recurring 5m/15m/1h crypto markets удобны для автоматизации и дают короткий цикл обратной связи;
- **maker/reward bots** — технически наиболее “квантовый” сегмент: там меньше нарратива про AI и больше реальной микроструктуры, инвентарного риска и rebate/lp-механик;
- **research/semantic agents** быстро растут, но пока чаще дают **analysis / MCP / paper trading / signal generation**, чем проверенный live-autonomy;
- **surveillance tools** — один из самых быстрорастущих сегментов на фоне общественного интереса к “инсайдерским” кошелькам и официального акцента Polymarket на suspicious-activity monitoring в sports markets.[11][12][36][40][41][42]

Для вашего проекта это означает: **не надо строить “LLM, который сам торгует” как ядро продукта**. Конкурентоспособная позиция — это:
1. **execution core**;
2. **wallet + surveillance intelligence**;
3. **watchlists / selected pools / operator approvals**;
4. **стратегии как отдельные модули**;
5. **AI-аналитика поверх жёсткого policy-gate**, а не вместо него.

---

## 1) Что считать “агентом” на Polymarket

На Polymarket-рынке слово “agent” используется как минимум в четырёх смыслах:

1. **Execution agent** — умеет найти рынок, прочитать стакан, подписать/отправить/отменить ордер.
2. **Strategy agent** — решает, когда купить YES/NO, когда сделать hedge, когда выйти.
3. **Research agent** — собирает и суммирует внешний контекст: новости, соцсигналы, академические/макро-источники, cross-market связи.
4. **Surveillance agent** — отслеживает кошельки, кластеры, аномалии и потенциально инсайдерское поведение.

Официальные документы Polymarket фактически подтверждают это разделение: platform primitives разделены на market discovery, public/private market data, real-time streams, order execution, builder routing, market-making operations и reward programs.[1][2][5][6][7][8][9]

---

## 2) Таксономия рынка

| Сегмент | Что делает | Основной edge | Техпримитивы | Степень зрелости |
|---|---|---|---|---|
| **Copy bots** | Автоматически зеркалят сделки выбранных трейдеров | Latency + translation + sizing/risk controls | Data API trades/activity, market/user WS, CLOB execution | Высокая |
| **Smart-wallet trackers** | Находят/ранжируют “умные” кошельки, дают алерты и профили | Wallet curation + analytics + alerting | Data API, public profiles, trades/activity, dashboards | Высокая |
| **Crypto interval bots** | Торгуют recurring crypto Up/Down рынки (5m/15m/1h/4h/день) | Микроструктура, recurring slug patterns, быстрый feedback loop | Gamma slugs, CLOB book, RTDS crypto prices, auto-redeem/merge | Средне-высокая |
| **Maker/reward bots** | Котируют обе стороны, пытаются зарабатывать на spread + rewards/rebates | Quote quality, inventory control, reward optimization | CLOB, WS, fee/rebate endpoints, split/merge/redeem | Средне-высокая |
| **Research/semantic agents** | Делают deep research, clustering, contradiction detection, AI briefs | Better context synthesis and relationship discovery | Gamma/Data + external search/news/LLM + MCP/RAG | Средняя |
| **Surveillance tools** | Ищут whales, suspicious wallets, entity links, insider-like patterns | Faster anomaly detection + attribution + routing to human/trader | Data API + onchain analytics + Arkham-like enrichment | Быстро растущая |

---

## 3) Copy bots

### Что это
Copy bot — это execution wrapper над чужим order flow. Он не обязан “понимать рынок”; его задача — **обнаружить сделку целевого кошелька** и **транслировать её на ваш кошелёк** с заданными риск-ограничениями.

### Почему сегмент зрелый
PolyGun уже productized этот сегмент как retail UX inside Telegram. В документации у них есть законченный флоу copy trading:
- указание wallet address трейдера;
- nickname;
- **sizing modes**: fixed / percentage / portfolio-weighted;
- **hard cap per trade**;
- **price range filter**;
- **slippage tolerance**.[13][14][15][16][17][18]

Это важный индикатор зрелости рынка: copy trading продаётся не как “магия AI”, а как **управляемая обвязка вокруг чужого execution**.

QuickNode в своём гайде по Polymarket copy trading bot описывает почти канонический технический паттерн: бот мониторит target wallet, детектит его сделки в реальном времени, ведёт position tracking и накладывает risk caps перед зеркалированием через Polymarket API.[22]

### Representative examples
- **PolyGun** — retail copy-trading Telegram product c развитым UX и risk settings.[13][14][15][16][17][18]
- **QuickNode guide** — reference architecture для self-built copy bot.[22]
- В open-source GitHub есть отдельные copy-trading repos и даже гибриды “copy + arbitrage”, что говорит о высокой спросовой базе и низком пороге клонирования базовой логики.[44]

### Где edge на самом деле
Copy bot выигрывает не потому, что “лучше думает”, а потому что:
1. быстро видит сделку;
2. правильно переводит size под ваш капитал;
3. защищает вас от плохих fill’ов;
4. не копирует мусорный flow.

### Основные failure modes
- **size mismatch**: исходный трейдер работает суммами, которые ваш депозит не выдерживает;
- **late fill**: вы копируете не трейдера, а хвост его цены;
- **wallet overfitting**: один красивый PnL-скрин не значит устойчивую стратегию;
- **delegation risk**: если execution отдан третьему инструменту, operational/security risk становится критическим. В конце 2025 Polymarket публично связывал часть account breach reports с уязвимостью стороннего authentication/login provider, а не с core infrastructure, что усиливает требования к архитектуре доступа и делегирования прав.[42]

### Вывод по сегменту
Copy bots — самый понятный для запуска сегмент, но и самый “commoditized”. Ваш будущий продукт не должен быть просто ещё одним generic copier. Если идти сюда, то только через **wallet selection + surveillance + portfolio allocator + policy gating**.

---

## 4) Smart-wallet trackers

### Что это
Это соседний, но отличный от copy trading сегмент. Smart-wallet tracker:
- ранжирует трейдеров;
- показывает PnL, активность, biggest wins/losses, patterns;
- отправляет алерты;
- иногда даёт прямой переход к trade/copy execution.

### Почему этот сегмент силён
Polymarket делает базовые данные публичными: **Data API** покрывает user positions, trades, activity, holder data, leaderboards и search по профилям/рынкам.[1][4]  
На этом строится целый слой инструментов поверх “public order flow”.

### Representative examples
- **PolyGun Smart Wallets** — curated “high performing traders” с категориями Sports / Crypto / Politics / Insider Wallets.[19][20][21]
- **Polymarket Analytics** — глобальная analytics-платформа по трейдерам, рынкам, позициям и activity; на сайте прямо заявлены leaderboard/trader activity и near real-time refresh cadence.[23][24]
- **Polysights** — analytics + “Insider Finder” + market intelligence layer.[25][26]
- **MobyScreener / PolyWallet / PredScan / PredictFolio / PolyWatch** и др. — community ecosystem показывает, что wallet tracking уже выделился в самостоятельный продуктовый вертикаль, а не просто feature inside one bot.[26][27][43][44]

### Чем smart-wallet tracker отличается от copy bot
| Smart-wallet tracker | Copy bot |
|---|---|
| Intelligence-first | Execution-first |
| Нужен для discovery и monitoring | Нужен для mirror execution |
| Часто без права торговать за пользователя | Часто требует execution permissions |
| Подходит для “basket watching” | Подходит для “follow this wallet now” |

### Что здесь реально продаётся
Не просто “список китов”, а:
- ranking & scoring,
- cluster/watchlists,
- category segmentation,
- alerting speed,
- trader dossiers,
- behavioral analytics.

### Вывод по сегменту
Это очень хороший кандидат для **первого слоя вашего продукта**. В отличие от “AI agent trader”, smart-wallet intelligence:
- ценен сам по себе;
- безопаснее;
- проще монетизируется;
- естественно соединяется с ручным или полуавтоматическим исполнением.

---

## 5) Crypto interval bots

### Что это
Это боты под recurring markets вроде **BTC/ETH/SOL/XRP Up or Down** на 5m / 15m / 1h и выше. Этот сегмент особенно активен, потому что:
- рынки повторяются по шаблону;
- их удобно искать по slug;
- есть быстрый feedback loop;
- доступны real-time crypto price feeds;
- на части crypto markets теперь есть taker fees / maker rebates, что создаёт отдельную микроэкономику.[3][7][8]

Официальная документация подтверждает:
- recurring crypto markets существуют как отдельный fee/rebate-enabled класс;
- RTDS отдаёт real-time crypto prices из **Binance** и **Chainlink**;
- slugs — first-class identifier для market/event discovery.[3][7][8]

### Какие подвиды стратегий уже видны в open source
Сегмент очень фрагментирован, но стратегии хорошо читаются:

#### 5.1. Signal / directional bots
Пример: **aulekator/Polymarket-BTC-15-Minute-Trading-Bot** — позиционируется как production-grade 15m BTC bot с multi-signal architecture, risk-first design, simulation/live modes и monitoring stack.[28]

Пример: **Gabagool2-2/polymarket-trading-bot-python** — строит UP/DOWN signals из:
- active market discovery via slug;
- orderbook capture через CLOB WebSocket;
- rolling midpoint history;
- spot price из Binance/Coinbase;
- сравнения движения midpoint/spot/strike;
- optional live execution.[31]

Пример: **discountry/polymarket-trading-bot** — отдельный flash-crash/contrarian style, который входит после резкого probability drop.[32]

#### 5.2. Pair/arbitrage bots
Пример: **rvenandowsley/Polymarket-crypto-15min-arbitrage-bot** — мониторит книги и ищет случаи, когда **yes_ask + no_ask < 1**, после чего исполняет coordinated orders и умеет merge redeemable positions.[30]

Пример: **crellOS/polymarket-arbitrage-bot-pre-order-15m-markets** — pre-order strategy: заранее ставит лимитные buy orders на обе стороны следующего 15m-окна и пытается зафиксировать guaranteed edge, если обе стороны берутся ниже суммарного fair payout.[29]

#### 5.3. Hybrid bots
Некоторые public repos сочетают:
- recurring market discovery,
- directional signal,
- early exit / stop-loss,
- hedge logic,
- auto-redeem,
- multi-asset support.[29][30][31][32]

### Почему этот сегмент так популярен
1. **Recurring slugs** упрощают automation.
2. **RTDS crypto prices** дают внешний reference feed.[3]
3. **Short horizon** быстро обучает и быстро сжигает — поэтому привлекает разработчиков.
4. **Maker rebates** и fee-enabled crypto markets добавляют microstructure incentives.[7][8]
5. Порог входа в open source ниже, чем в полноценный news-driven geopolitical research agent.

### Но здесь и главный самообман
Большая часть interval bots — это не “AI edge”, а комбинация:
- market discovery,
- low-latency data handling,
- rudimentary signals,
- risk exits,
- order management.

Именно поэтому этот сегмент полезен вам как **песочница execution и replay**, но не как доказательство долгосрочного edge.

### Вывод по сегменту
Если вам нужен технический полигон для отработки исполнения — crypto interval markets идеальны. Если вам нужен устойчивый alpha — одного “бота на BTC 15m” недостаточно.

---

## 6) Maker / reward bots

### Что это
Это отдельный класс ботов, цель которых — не угадать исход лучше рынка, а:
- **котировать ликвидность**,
- зарабатывать на spread,
- получать **Liquidity Rewards** или **Maker Rebates**,
- управлять YES/NO inventory,
- merge/redeem outcome tokens.

### Официальная экономика сегмента
Polymarket официально поддерживает **две разные reward-mechanics**:

1. **Liquidity Rewards** — поощрение за resting limit orders, рассчитанное по формуле качества котировок относительно midpoint и book participation; выплаты идут daily, methodology подробно описана в docs.[6]

2. **Maker Rebates Program** — daily USDC rebates для makers, funded by taker fees в eligible markets.  
На момент марта 2026 docs указывают, что taker fees включены на **all crypto markets, NCAAB и Serie A**, а rebate funding для crypto и sports markets описан отдельно; в таблице указаны rollout dates для 15-Min, 5-Min, 1H/4H/Daily/Weekly crypto и sports cohorts.[7][8]

Дополнительно docs по positions/tokens отдельно указывают **Holding Rewards**: 4.00% annualized on eligible markets, distributed daily based on sampled position value, с оговоркой, что ставка может меняться по усмотрению Polymarket.[10]

### Representative examples
- **Официальная MM docs**: overview, trading, liquidity rewards, maker rebates — это уже полноценная market-making playbook с two-sided quoting, batch orders, GTD quotes, risk controls и operational workflows.[5][6][7]
- **warproxxx/poly-maker** — AMM/MM bot c configurable parameters.[33]
- **terrytrl100/polymarket-automated-mm** — подчёркивает reward-optimized pricing на базе maker reward formula, market selection by profitability/daily rewards, position management и merge logic.[34]
- **lorine93s/polymarket-market-maker-bot** — позиционируется как production-ready bot для Polymarket CLOB с inventory/risk/cancel-replace cycles.[35]

### Почему этот сегмент недооценён
В публичном инфополе много шума про “AI agents”, но maker/reward bots ближе к настоящей trading infrastructure:
- нужны аккуратные quote engines,
- inventory accounting,
- fee-aware order signing,
- market selection,
- adverse selection control,
- risk limits.

### Почему здесь сложнее, чем кажется
- quote quality нужно соотносить с reward formulas;
- crossed/negative spread = гарантированный убыток;
- rebate farming без fill-quality быстро превращается в adverse selection;
- нужен сильный cancel/replace discipline и latency control.[5][6][7][8]

### Вывод по сегменту
Если ваша долгосрочная цель — **устойчивая торговая инфраструктура**, а не только “вдохновляющий агент”, maker/reward layer стоит рассматривать как стратегически более серьёзный вектор, чем generic copy-trading.

---

## 7) Research / semantic agents

### Что это
Это слой агентов, которые:
- анализируют вопрос рынка;
- ищут внешние данные;
- строят аргументы PRO/CON;
- ищут связи между рынками;
- иногда предлагают probability estimate;
- иногда переходят к paper/live execution.

### Official / semi-official infrastructure
Официальный repo **Polymarket/agents** позиционируется как framework/utilities для building AI agents for Polymarket: integration with Polymarket API, RAG, data sourcing from news/web/betting services и CLI for trading/research workflows.[11]

Отдельно Polymarket выпустил **agent-skills** repo, где knowledge split на authentication, order patterns, market data, websocket, bridge, gasless и CTF operations — то есть компания явно признаёт AI-agent integration как отдельную builder surface.[12]

### Representative examples
- **Polymarket/agents** — framework, не готовый alpha-engine.[11]
- **Polymarket/agent-skills** — packaged knowledge layer for agents.[12]
- **Polyseer** — multi-agent research system: planner, research agents, critic, analyst, reporter; использует Bayesian aggregation и real-time research over market/news/paper data.[36]
- **artvandelay/polymarket-agents** — MCP server + autonomous **paper trading** bot для Polymarket market analysis.[37]
- **Semantic 42** — product narrative вокруг autonomous multi-agent trading on Polymarket через x402 / Core Agent 42.[38]
- **Academic support**: paper “Semantic Trading: Agentic AI for Clustering and Relationship Discovery in Prediction Markets” показывает, что агентная pipeline может кластеризовать Polymarket markets, находить correlated/anti-correlated pairs, достигать примерно **60–70% accuracy** на relational predictions и превращать это в trading signals с примерно **20% average returns over week-long horizons** в исследовательской постановке.[39]

### Что здесь реально интересно
Не “бот, который сам нажмёт BUY”, а следующие функции:
1. **market brief generation**;
2. **same-outcome / opposite-outcome relationship discovery**;
3. **cross-market contradiction detection**;
4. **evidence-weighted probability revisions**;
5. **operator-facing memos**.

### Что пока слабое место
- верифицируемый live track record редок;
- легко спутать demo/paper/autonomous analysis с реальным repeatable trading edge;
- LLM-слой может красиво объяснять шум;
- true edge возникает только если агент умеет не только “думать”, но и **работать с latency, fills, fees, market structure**.

### Вывод по сегменту
Research/semantic agents — это не ядро execution, а **верхний интеллектуальный слой**. Для вашего проекта он очень нужен, но только после того, как будет готов deterministic execution + risk/policy framework.

---

## 8) Surveillance tools

### Что это
Surveillance на Polymarket — это инструменты, которые:
- находят whales и аномальные кошельки;
- ранжируют suspicious behaviour;
- связывают адреса/кластеры;
- поднимают alerts по рынкам, где может быть insider-like flow;
- иногда превращают это в copy signal.

### Почему сегмент ускорился
Причин две:

1. **Прозрачность onchain trade flow** — user positions, activity, trades, public profiles и onchain movement делают wallet intelligence естественным направлением.[1][4]

2. **Рост публичного интереса к “инсайдерским” кейсам** — медиа и community обсуждают well-timed trades на геополитических и corporate-event рынках; Reuters отдельно писало, что fear of insider-like trading может подрывать доверие к prediction markets. Параллельно Polymarket официально объявил партнёрство с **Palantir + TWG AI** для sports integrity controls, aimed at preventing, identifying and reporting suspicious activity.[41][42]

### Representative examples
- **PolyGun Insider Wallets** — curated insider category as a copyable/watchable class.[21]
- **Polysights / Insider Finder** — suspicious-wallet monitoring и intelligence workflows.[25][26]
- **Arkham API** — production-grade blockchain intelligence, построенный как **entity-first**, **confidence-scored** system с addresses/entities/labels/tags и explicit focus на wallet tracking/analytics. Это очень важный external enrichment layer для вашего проекта.[40]
- **Palantir/TWG AI sports integrity stack for Polymarket** — institutional surveillance direction со стороны самой platform/partners.[41]

### Что surveillance даёт вам practically
1. **Address enrichment**  
   Кто это может быть? Связанный cluster? Откуда funding?

2. **Behavioral scoring**  
   Новый кошелёк, мало рынков, огромный size, точечные ставки, быстрые exits — это можно формализовать.

3. **Cross-wallet linkage**  
   Funding paths, shared counterparties, synchronized entries.

4. **Operator workflow**  
   Alert → dossier → manual review → watchlist → optional limited copy / hedge response.

### Главный риск
False positives.  
“Похоже на инсайдера” не равно “это инсайдер”. Поэтому surveillance надо строить как **intelligence and policy input**, а не как blind autotrader.

### Вывод по сегменту
Это одна из самых перспективных зон для дифференциации вашего проекта. Generic copy bot легко клонируется. **Surveillance-assisted trading infra** — уже менее тривиальный слой.

---

## 9) Где реально деньги и устойчивость

### 9.1. Retail convenience layer
Telegram execution, quick trading, copy-trading, alerts.  
Representative: PolyGun и подобные инструменты.[13][14][19]

### 9.2. Analytics SaaS
Trader dashboards, wallet tracking, market discovery, alerts.  
Representative: Polymarket Analytics, Polysights, PolyWallet-like category.[23][24][25][26][43]

### 9.3. Builder routing
Builder Program даёт volume attribution, gasless relayer access и weekly USDC rewards для verified builders based on volume.[9]  
Это важная monetization surface для execution apps.

### 9.4. Maker incentives
MMs зарабатывают на spread + daily liquidity rewards / rebates.[5][6][7][8]

### 9.5. AI / semantic layer
Пока чаще продаётся как:
- research edge,
- brand/attention,
- signal layer,
- demo of autonomous finance,
чем как доказанный fully autonomous pnl machine.[11][12][36][37][38][39]

### 9.6. Surveillance as premium intelligence
Strong candidate for subscription or operator-grade platform:
- suspicious wallet alerts,
- cluster analysis,
- insider-like flow monitoring,
- integrated market dossiers.[21][25][26][40][41][42]

---

## 10) White space: где ещё нет сильного продукта

Ниже то, где я вижу наилучшие шансы для вашей системы.

### A. Surveillance → execution bridge
Сегодня рынок заполнен либо:
- tracker’ами без disciplined execution,
- либо copier’ами без нормального intelligence layer.

Ниша:  
**выявили suspicious wallet / cluster → оценили confidence → operator approval → ограниченное исполнение по whitelist-кошелькам и whitelist-рынкам.**

### B. Basket copy trading
Один кошелёк = хрупко.  
Ниша: basket of wallets + scoring + category routing + anti-correlation checks.

### C. Cross-market semantic contradiction engine
Идея из semantic research сегмента почти не productized в execution-grade retail tooling:  
находить contradictory / redundant / same-outcome markets и превращать это в watchlists, hedges и selective trades.[39]

### D. Multi-wallet operator CLI
Большая часть retail tooling идёт в Telegram/mobile UX.  
Ниша для power users: **CLI-first / terminal-first ops layer**:
- watchlists,
- staged orders,
- multi-wallet allocation,
- approvals,
- paper/live toggles,
- audit logs.

### E. Replay / forensic backtesting
У многих open-source ботов слабое место — нет реального replay layer с orderbook-aware evaluation.  
Ниша: полноценно воспроизводить market conditions, fills, slippage, missed entries и operator decisions.

---

## 11) Что это означает для вашего проекта

## Не строить:
- generic copy bot;
- “LLM decides and trades everything”;
- pure insider autotrader;
- only-BTC-15m bot как всю продуктовую ставку.

## Строить:
### Layer 1 — Deterministic execution core
- market discovery;
- token IDs;
- book read;
- create/cancel/replace orders;
- audit trail;
- dry-run/paper/live.

### Layer 2 — Wallet & surveillance intelligence
- wallet registry;
- activity monitor;
- smart-wallet scoring;
- suspicious-cluster detection;
- Arkham enrichment.[40]

### Layer 3 — Watchlists & selected pools
- our positions;
- monitored candidate markets;
- watched wallets;
- insider watchlist;
- high-priority event pools.

### Layer 4 — Strategy engine
- manual strategies;
- copy rules;
- crypto interval rules;
- correlation/arbitrage rules;
- operator prompts to analytics module.

### Layer 5 — AI analyst
- briefs;
- dossiers;
- contradiction maps;
- event memos;
- PRO/CON summaries.

### Layer 6 — Policy gate
- per-wallet limits;
- per-market limits;
- jurisdictional / operational policy;
- human approval requirements for sensitive categories.

---

## 12) Мой жёсткий вывод

Если смотреть на рынок честно, то сегодня:
- **copy bots и wallet trackers** — уже коммерческий базовый слой;
- **crypto interval bots** — лучшая sandbox-ниша для execution engineering;
- **maker/reward bots** — наиболее технически защищённый сегмент;
- **research/semantic agents** — сильный верхний интеллект, но пока редко self-sufficient как live trading core;
- **surveillance tools** — один из самых интересных и недозаполненных слоёв для дифференциации.

### Следствие для вас
Ваш лучший ход — не делать “ещё одного AI Polymarket trader”, а собрать **hybrid stack**:

**Execution core + wallet intelligence + surveillance + operator CLI + modular strategies + AI research layer**

Именно такая комбинация:
- не сводится к commodity copy trading;
- использует onchain transparency как настоящее преимущество;
- позволяет вручную вносить кошельки, рынки и правила;
- естественно масштабируется в Codex/agents/skills/workflow development model.

---

## 13) Practical next step after this memo

Следующий документ, который логично сделать после этого memo:

**“Target architecture & competitive positioning memo”**

Содержимое:
1. какой сегмент берем первым;
2. чем мы отличаемся от PolyGun / wallet trackers / generic interval bots;
3. какая v1 фича действительно даёт edge;
4. что должно идти в Codex repo как `AGENTS.md`, `docs/specs`, `skills`, `automations`.

---

## 14) Source notes / confidence

### Уровни доверия по источникам
- **Высокий:** official Polymarket docs, official/open GitHub repos, Arkham docs, arXiv paper, company press release.[1]-[12][40][41]
- **Средний:** product docs / product websites (PolyGun, Polysights, Polymarket Analytics).[13]-[26]
- **Ниже среднего, использовать как directory signal:** community directories and ecosystem lists (PolyTools, Polymark.et, Awesome-Polymarket-Tools, ecosystem guides).[26][27][43][44]

### Важная оговорка
Часть “landscape” примеров — это:
- маркетинговые страницы продуктов,
- community directories,
- GitHub repos без верифицированного live PnL.

Поэтому их надо читать как **evidence of product existence and category shape**, а не как доказательство устойчивой доходности.

---

## 15) References

[1] Polymarket Docs — API Introduction  
https://docs.polymarket.com/api-reference/introduction

[2] Polymarket Docs — WebSocket Overview  
https://docs.polymarket.com/market-data/websocket/overview

[3] Polymarket Docs — Real-Time Data Socket (RTDS)  
https://docs.polymarket.com/market-data/websocket/rtds

[4] Polymarket Docs — Get trades for a user or markets  
https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets

[5] Polymarket Docs — Market Makers Overview  
https://docs.polymarket.com/market-makers/overview

[6] Polymarket Docs — Liquidity Rewards  
https://docs.polymarket.com/market-makers/liquidity-rewards

[7] Polymarket Docs — Maker Rebates Program  
https://docs.polymarket.com/market-makers/maker-rebates

[8] Polymarket Docs — Trading Fees  
https://docs.polymarket.com/trading/fees

[9] Polymarket Docs — Builder Program  
https://docs.polymarket.com/builders/overview

[10] Polymarket Docs — Positions & Tokens  
https://docs.polymarket.com/concepts/positions-tokens

[11] GitHub — Polymarket/agents  
https://github.com/Polymarket/agents

[12] GitHub — Polymarket/agent-skills  
https://github.com/Polymarket/agent-skills

[13] PolyGun Docs — Welcome / Product Overview  
https://polygun.gitbook.io/polygun-docs

[14] PolyGun Docs — Copy Trading  
https://polygun.gitbook.io/polygun-docs/telegram-bot-user-guide/copy-trading

[15] PolyGun Docs — Copy Trade Sizes  
https://polygun.gitbook.io/polygun-docs/telegram-bot-user-guide/copy-trading/copy-trade-sizes

[16] PolyGun Docs — Max Copy $ Amount per Trade  
https://polygun.gitbook.io/polygun-docs/telegram-bot-user-guide/copy-trading/max-copy-usd-amount-per-trade

[17] PolyGun Docs — Copy Trade Price Range  
https://polygun.gitbook.io/polygun-docs/telegram-bot-user-guide/copy-trading/copy-trade-price-range

[18] PolyGun Docs — Slippage Tolerance  
https://polygun.gitbook.io/polygun-docs/telegram-bot-user-guide/copy-trading/slippage-tolerance

[19] PolyGun Docs — Smart Wallets  
https://polygun.gitbook.io/polygun-docs/smart-wallets/smart-wallets

[20] PolyGun Docs — Crypto Wallets  
https://polygun.gitbook.io/polygun-docs/smart-wallets/crypto-wallets

[21] PolyGun Docs — Insider Wallets  
https://polygun.gitbook.io/polygun-docs/smart-wallets/insider-wallets

[22] QuickNode — Building a Polymarket Copy Trading Bot  
https://www.quicknode.com/guides/defi/polymarket-copy-trading-bot

[23] Polymarket Analytics — Activity  
https://polymarketanalytics.com/activity

[24] Polymarket Analytics — Home / Traders  
https://polymarketanalytics.com/
https://polymarketanalytics.com/traders

[25] Polysights — Home  
https://www.polysights.xyz/

[26] Polymark.et — Polysights product page  
https://polymark.et/product/polysights

[27] Polymark.et — MobyScreener product page  
https://polymark.et/product/mobyscreener

[28] GitHub — aulekator/Polymarket-BTC-15-Minute-Trading-Bot  
https://github.com/aulekator/Polymarket-BTC-15-Minute-Trading-Bot

[29] GitHub — crellOS/polymarket-arbitrage-bot-pre-order-15m-markets  
https://github.com/crellOS/polymarket-arbitrage-bot-pre-order-15m-markets

[30] GitHub — rvenandowsley/Polymarket-crypto-15min-arbitrage-bot  
https://github.com/rvenandowsley/Polymarket-crypto-15min-arbitrage-bot

[31] GitHub — Gabagool2-2/polymarket-trading-bot-python  
https://github.com/Gabagool2-2/polymarket-trading-bot-python

[32] GitHub — discountry/polymarket-trading-bot  
https://github.com/discountry/polymarket-trading-bot

[33] GitHub — warproxxx/poly-maker  
https://github.com/warproxxx/poly-maker

[34] GitHub — terrytrl100/polymarket-automated-mm  
https://github.com/terrytrl100/polymarket-automated-mm

[35] GitHub — lorine93s/polymarket-market-maker-bot  
https://github.com/lorine93s/polymarket-market-maker-bot

[36] GitHub — yorkeccak/Polyseer  
https://github.com/yorkeccak/Polyseer

[37] GitHub — artvandelay/polymarket-agents  
https://github.com/artvandelay/polymarket-agents

[38] Polymark.et — Semantic 42  
https://polymark.et/product/semantic-42

[39] arXiv — Semantic Trading: Agentic AI for Clustering and Relationship Discovery in Prediction Markets  
https://arxiv.org/abs/2512.02436

[40] Arkham API Guide  
https://intel.arkm.com/api/docs

[41] Business Wire — Polymarket Partners With Palantir and TWG AI to Build Next-generation Sports Integrity Platform  
https://www.businesswire.com/news/home/20260310736467/en/Polymarket-Partners-With-Palantir-and-TWG-AI-to-Build-Next-generation-Sports-Integrity-Platform

[42] Reuters — How insider-trading fears harm prediction markets  
https://www.reuters.com/commentary/breakingviews/how-insider-trading-fears-harm-prediction-markets-2026-03-12/

[43] PolyTools — Polymarket Tools directory  
https://polytools.app/

[44] GitHub — harish-garg/Awesome-Polymarket-Tools  
https://github.com/harish-garg/Awesome-Polymarket-Tools