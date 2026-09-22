# План equality — Tier-2, пункт 3a (конечное равенство)

Статус: **утверждён и реализован**. Tier-2 из `docs/folio_extension_plan.md` §6
разделён на **3a конечное равенство** (эта записка) и **3b ограниченные функциональные
термы** (отложено, §5). Фрагмент гейтится **только синтетически** (`evals.l2_synthetic`),
потому что ни одна доступная выборка не содержит равенство в чистом срезе (§2). Новой
процедуры решения нет: переиспользуется существующая ограниченная клаузальная процедура
за `ANKYRA_LOGIC`. Результаты — в §8.

Каноническая версия: `docs/equality_plan.md` (английский); это русское зеркало.

См. также: `docs/folio_extension_plan.md` (§6 Phase 3, `D-FE-4`),
`docs/coverage_ceiling.md` (backlog Tier-1), `docs/l2_plan.md` (расширяемая процедура),
`docs/fragment_routing.md` (контракт named fragment), `docs/folio.md` §4 (инвентарь
конструктов), `docs/quality_findings.md` §G, `docs/implementation_plan.md` §8,
`docs/reasoning_roadmap.md`.

## 1. Цель

Решать конечное ground-равенство `=` / `≠` внутри committed L2-фрагмента: подстановка
(конгруэнтность), рефлексивность, симметрия и unique names — не покидая ограниченную
клаузальную процедуру и не понижая `proven`. Конструкт, который фрагмент решить не
может, остаётся честным `out_of_fragment` / `unsupported`, а не догадкой.

## 2. Находка, задающая размер фрагмента: внешнего гейта нет

План `docs/folio_extension_plan.md` §6 называл равенство «reachable but absent from the
committed sample». Измерение (LLM-free, 2026-09-22) показывает: оно **отсутствует во всей
доступной коллекции**, а функциональные термы отсутствуют везде:

| источник | строк | `=` | функциональный терм |
|---|---|---|---|
| FOLIO v0 `validation` (`evals/data/.cache/folio/validation.jsonl`, committed-источник) | 204 | **0** | **0** |
| FOLIO v0 `train` (нет `conclusion-FOL`) | 1004 | 0 | 0 |
| FOLIO v2 `validation` (`tasksource/folio`, `folio_v2_validation.jsonl`) | 203 | 33 | **0** |
| FOLIO v2 `train` (`tasksource/folio`, `folio_v2_train.jsonl`) | 1001 | 162 | **0** |

Хуже того, в FOLIO v2 равенство переплетено с конструктами вне committed-фрагмента: из
33 equality-строк validation 30 используют `var = var` (multi-variable quantification,
отложенный пункт Tier-1), а после фильтра без XOR/бикондиционала/arity-3/вложенных
кванторов остаётся всего 11 строк — и часть из них всё ещё использует `∀x∀y` или `∃x∃y`
с двумя свидетелями. Итого: **чистого equality-среза для гейта нет**, и **нигде нет
функционального терма** (3b не реализуется; это остаётся ловушкой полуразрешимости из
`docs/l2_plan.md` §8).

Следствие (D-FE-4): равенство входит как **named fragment с синтетическим soundness-гейтом**,
а отсутствие внешнего гейта фиксируется здесь, а не замалчивается.

## 3. Скоуп и не-цели

**В скоупе.**
- Reserved бинарный предикат `eq` (subject/object; отрицание — `Morphism.negated`);
  `=` / `!=` нормализуются в него.
- Ground-равенство: подстановка через каноникализацию, рефлексивность `eq(t,t)`,
  симметрия (через каноникализацию), unique names `neq(a,b)` для различных ground-имён.
- Равенство в ассертированных фактах, головах и телах правил, атомах экзистенциалов и
  целях.
- Объявленный fragment feature `equality`, его refusal-код, синтетический гейт, тесты и
  доки.

**Вне скоупа (без изменений).**
- **Функциональные термы** (`f(x,y)`) — нет данных; отдельный отложенный фрагмент (3b).
- Полная first-order унификация и не-ground равенство; решается только ground-равенство
  над конечным именованным доменом.
- Равенство на Horn-пути: при выключенном `ANKYRA_LOGIC` структура отклоняется по имени.
- Extraction / эмиссия `=` / `!=` из Phase 0 (live-путь не гейтится); gold-парсер FOLIO v2;
  новые live-прогоны LLM (`docs/reasoning_roadmap.md` §4).
- Никаких NL-эвристик и per-id тюнинга (`docs/task.md` §3.8).

## 4. Проектные решения

- **EQ-D1 — Представление.** Один reserved id `eq`; `=` / `==` / `!=` отображаются в него,
  отрицание — существующий флаг `Morphism.negated` (отдельного `neq` нет). *Коллизия:*
  `engine/builtins.py` уже отображает `eq` / `neq` в числовой builtin сравнения. На
  клаузальном/equality-пути `eq` идёт в equality-препроцессор (`engine/clause.py`), а не в
  builtin-фильтр; числовой builtin остаётся Horn-path-only (`ANKYRA_BUILTINS`).
- **EQ-D2 — Семантика: конечный именованный домен (объявленная).** Equality-фрагмент
  читает тот же конечный ground-домен, который уже предполагает L2-grounding: терм
  обозначает своё имя, поэтому **различные ground-имена различны, если ассертированное
  ground-равенство их не слило**. Это *объявленная* семантика фрагмента (как объявленный
  CWA у L1, `docs/l1_plan.md` D-L1-4), не выводится из формулировки, и по умолчанию
  выключена вместе с `ANKYRA_LOGIC`. Soundness-контроль `eq-control-diseq-07` фиксирует
  границу: правило с disequality-условием не срабатывает для исключённого индивида.
- **EQ-D3 — Понижение.** `engine/clause.py`, на клаусификации: ассертированное **unit**
  ground-равенство строит union-find; каждый терм каноникализуется к представителю
  (подстановка бесплатно); затем добавляются unit-аксиомы рефлексивности и unique names в
  обеих ориентациях над индивидуальным доменом. Ассертированные **условные** или
  **дизъюнктивные** равенства не задают разбиение (это не ассерции); они остаются
  прверу и, где неразрешимы, остаются честными. `resolution.py` не меняется: каждая
  аксиома — обычный шаг резолюции.
- **EQ-D4 — Фрагмент / capability.** Новый `FragmentFeature "equality"` в
  `engine/inference.py`, решается существующей capability `clausal` — **нового флага
  нет** (паттерн T1/T3/T5/T4/T2). При выключенной clausal-capability и наличии `eq`
  отказ — `out_of_fragment:equality`; equality также входит в clausal-fragment-набор,
  поэтому `defeasible × equality` отклоняется (D-FR-4).
- **EQ-D5 — Каноникализация запроса.** Запрос (target/goals/conditions) и пул свидетелей
  каноникализуются тем же разбиением, что и теория (`verify.l2_outcomes`), чтобы цель над
  слитым именем совпала с каноническим множеством клауз.
- **EQ-D6 — Функции и внешний гейт.** 3b не реализуется (нет данных); Tier-2 гейтится
  только синтетически (§2).

## 5. Изменения движка

- **`engine/clause.py`.** `equality_partition` (ассертированные unit ground-равенства +
  Skolem-атомы экзистенциалов), `canonicalize_theory` / `canonicalize_query`, карта
  `Clausification.canon`, `has_equality` / `query_equality_terms` и `_add_equality_axioms`
  (рефлексивность + unique names); `clausify` получает `equality_terms=` и исключает `eq`
  из builtin-отказа.
- **`engine/inference.py`.** `FragmentFeature "equality"`, `_has_equality`, членство в
  `_CLAUSAL_FRAGMENT` и отказ `out_of_fragment:equality` на Horn-пути.
- **`engine/verify.py`.** `l2_outcomes` передаёт equality-термы запроса в `clausify`,
  каноникализует запрос и пул свидетелей, а также Gamma-условие в `_unused_l2`.
- **`engine/resolution.py` / `engine/explain.py`.** Без изменений (equality-аксиомы —
  обычные рёбра резолюции).

## 6. Синтетический гейт (`evals.l2_synthetic`, механизм `equality`)

| кейс | теория / цель | ожидание |
|---|---|---|
| `eq-subst-01` | `is_a(rex,cat)`, `eq(rex,tom)`, `is_a(?x,cat)→is_a(?x,animal)`; цель `is_a(tom,animal)` | `supported`, `yes` (подстановка) |
| `eq-reflexive-02` | `is_a(rex,cat)`; цель `eq(rex,rex)` | `supported`, `yes` |
| `eq-unique-names-03` | `is_a(rex,cat)`, `is_a(tom,cat)`; цель `eq(rex,tom)` с отрицанием | `supported`, `yes` |
| `eq-distinct-refuted-04` | то же; цель `eq(rex,tom)` | `refuted`, `no` |
| `eq-symmetry-05` | `eq(rex,tom)`; цель `eq(tom,rex)` | `supported`, `yes` |
| `eq-body-disequality-06` | тело правила `?x != rex`; цель `is_a(tom,special)` | `supported`, `yes` |
| `eq-control-diseq-07` | то же; цель `is_a(rex,special)` | `unsupported` (**soundness-контроль**) |
| `eq-control-flag-off-08` | структура с `eq`, `logic="off"` | `out_of_fragment:equality` |
| `eq-control-budget-09` | подстановочный кейс, `budget=1` | `insufficient`, **никогда** не доказательство |

`evals.build_routing_synthetic` добавляет `equality-18` (feature, clausal) и
`refuse-equality-19` (отказ при выключенном L2).

## 7. Тесты и проверка

- `tests/test_engine_equality.py` — разбиение, каноникализация, инъекция аксиом,
  подстановка, рефлексивность, unique names, симметрия, disequality в теле + контроль,
  routing-отказ.
- `tests/test_evals_l2_synthetic.py` / `tests/test_evals_routing_synthetic.py` — обновление
  гейта и покрытия.
- `uv run pytest`, `uv run python -m evals.l2_synthetic`,
  `uv run python -m evals.routing_synthetic`,
  `uv run python -m evals.analyze_folio --subset l2` (без изменений: равенства в FOLIO v0 нет).

## 8. Результаты

Реализовано 2026-09-22 (решения EQ-D1…EQ-D6). LLM-free проверка:

| гейт | до | после |
|---|---|---|
| `evals.l2_synthetic` | 56/56 | **65/65** (9 кейсов `equality`) |
| `evals.routing_synthetic` | 17/17 | **19/19** (feature + отказ) |
| `uv run pytest` | 480 passed | **505 passed**, 26 skipped |
| FOLIO L2 tier a gold-fed | 42/45 | 42/45 (без изменений; `out_of_fragment` 1, covered 42/44) |

Ни одно число FOLIO не двигается, потому что в FOLIO v0 равенства нет. Фрагмент доказан
синтетическим гейтом, чьи контроли держатся: правило с disequality не срабатывает для
исключённого индивида, исчерпанный бюджет — не доказательство, а равенство при выключенном
L2 отклоняется по имени.

## 9. Ограничения

- Конструкт входит только как named fragment (`docs/fragment_routing.md`); вне конечного
  ground-домена остаётся честный `out_of_fragment` / `unsupported`.
- Unique-names читается **объявленно** (EQ-D2), не выводится из формулировки; числовой
  `eq` builtin не переиспользуется на клаузальном пути (EQ-D1).
- Никакого понижения семантики: disequality не «заминается», исключённый индивид не
  срабатывает правилом через подстановку.
- Никакого per-id тюнинга; гейт структурный и LLM-free.
- Никаких новых live-прогонов LLM без отдельного явного решения
  (`docs/reasoning_roadmap.md` §4).
