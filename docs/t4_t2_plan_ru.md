# План T4 + T2 — неплоская ground-цель и экзистенциальная посылка с вложенной ∨

Статус: **утверждён и реализован**. Это последние два пункта бэклога понижения
Tier-1 (`docs/coverage_ceiling.md` §6–§7). **T4** решает неплоскую **ground**-формулу
цели `φ` (`Cute ∧ Still → Turtle ∧ Skittish`, `A ∨ B → C ∨ D`) и закрывает открытое
решение **T-D2**. **T2** решает экзистенциальную посылку, тело которой содержит
вложенную дизъюнкцию (`∃x (A(x) ∧ (B(x) ∨ C(x) ∨ …))`). Согласно `D-FE-3` оба
**переиспользуют существующую ограниченную клаузальную процедуру** (`ANKYRA_LOGIC`):
работа — в IR/lowering, а не в новой семантике. Результаты — в §15.

Канонический язык: английский; русское зеркало: `docs/t4_t2_plan_ru.md`, канонический
оригинал — `docs/t4_t2_plan.md`.

Связанное: `docs/coverage_ceiling.md` (упорядоченный бэклог и T-D2), `docs/t1_plan.md`,
`docs/t3_plan.md`, `docs/t5_plan.md` (шаблон на пункт, которому это следует),
`docs/l2_plan.md` (процедура, которую оба расширяют), `docs/folio_gold_fed.md`
(измерение, за которым это следует), `docs/fragment_routing.md` (контракт
именованного фрагмента), `docs/reasoning_roadmap.md`, `docs/implementation_plan.md`
(§8 пункт 26).

## 1. Цель

Закрыть последние два пробела охвата FOLIO L2 тир a, чтобы закоммиченный срез решался
весь, кроме одной битой аннотации. Измеренный базис (2026-09-22, после T1/T3/T5,
`uv run python -m evals.analyze_folio --subset l2`):

| источник вердикта | верно |
|---|---|
| text-fed | 25/45 |
| gold-fed open | 35/45 |
| gold `out_of_fragment` | 6/45 |
| covered (метод) | 35/39 |
| covered (текст) | 22/39 |

Оставшиеся 6 строк `out_of_fragment`:

| id | метка | первый блокер | пункт |
|---|---|---|---|
| folio-validation-0006 | True | посылка `∃x (GetMonkeypox(x) ∧ (Fever(x) ∨ …))` | **T2** |
| folio-validation-0007 | Uncertain | idem | **T2** |
| folio-validation-0008 | Uncertain | idem | **T2** |
| folio-validation-0073 | True | цель `GrowthCompanies’Stocks(kO) ∨ PriceVolatile(kO) → ¬Companies’Stocks(kO) ∨ ¬PriceVolatile(kO)` | **T4** |
| folio-validation-0020 | False | цель `Cute(rock) ∧ Still(rock) → Turtle(rock) ∧ Skittish(rock)` (посылка уже исправлена T5) | **T4** |
| folio-validation-0109 | False | лишняя `)` — битая | — (данные) |

Прототип (LLM-free, §9): T4 решает `0073`→`supported`/`yes` и `0020`→`refuted`/`no`;
T2 решает `0006`→`yes`, `0007`→`unknown`, `0008`→`unknown`. Вместе ожидается охват
**44/45**, gold-fed **40/45**, `out_of_fragment` **1/45** (только `0109`), covered
gold-fed **40/44**, **0 ложных заземлённых доказательств**.

## 2. Текущие блокеры

### T4

- **Парсер.** `_conclusion` (`evals/folio_fol.py:353–380`) отвергает любую неплоскую,
  неквантифицированную цель сразу:
  `raise FolParseError("compound conclusion is not a flat conjunction/disjunction")`
  (`evals/folio_fol.py:380`). `0073`/`0020` попадают туда после NNF.
- **IR.** `Query.goals` + `goal_mode` (`single | all | any | forall`,
  `core/models.py:23–27`) не имеют формы для общей булевой комбинации ground-литералов.
  `all` — каждый конъюнкт независимо, `any` — плоская дизъюнкция; ни то, ни другое не
  есть `(A∧B) → (C∧D)`.
- **Доказыватель уже достаточно общий.** `refute_support`
  (`engine/resolution.py:121`) принимает *список* предположенных клауз, поэтому
  `T ⊨ φ` решается как невыполнимость `T ∪ {¬φ}` помещением CNF `¬φ` в set of support.
  Новой процедуры решения не нужно.

### T2

- **Парсер.** `_existential_premise` (`evals/folio_fol.py:317–327`) требует, чтобы тело
  было конъюнкцией литералов:
  `raise FolParseError("existential premise is not a conjunction of literals")`. Тело
  `GetMonkeypox(x) ∧ (Fever(x) ∨ …)` — не конъюнкция литералов, поэтому `0006/0007/0008`
  отвергаются.
- **IR.** `Existential` (`core/models.py:185–196`) несёт только `atoms` (конъюнкцию
  литералов). Поля для дизъюнктивной части тела нет.
- **Клаузификация.** `_add_existentials` (`engine/clause.py:270–287`) порождает по
  одной unit-клаузе на атом над Skolem-константой; дизъюнктивную клаузу он испустить
  не может.

## 3. Объём и не-цели

**В объёме.**
- **T4:** **ground** булева формула цели над литералами (без квантора и свободной
  переменной): импликации между соединениями без `∀`, комбинации по Де Моргану,
  конъюнкции клауз. Решается существующей ограниченной резолюцией через CNF `φ` и `¬φ`.
- **T2:** экзистенциальная посылка `∃x φ(x)`, тело которой — **CNF над литералами от
  `x`** (конъюнкция unit- и многолитеральных клауз), например `∃x (A(x) ∧ (B(x)∨C(x)))`.
  Skolemize в `A(sk) ∧ (B(sk) ∨ C(sk))`.
- Имена признаков, синтетические гейты и routing-контроли; парсер gold-fed.

**Вне объёма (без изменений, по-прежнему `out_of_fragment`).**
- Формула цели с **квантором или свободной переменной** (`∀`/`∃` внутри составной цели);
  такие остаются формами T1/T3 либо отвергаются.
- Вложенные кванторы в теле экзистенциала, функциональные термы, DNF-тела за пределами
  CNF (любое пропозициональное тело нормализуется в CNF; квантор внутри отвергается).
- **Живая формулировка извлечения** для составного вопроса или посылки с вложенной
  дизъюнкцией — трек извлечения (G1–G4), а не method-гейты T4/T2.
- Без нового флага и новой настройки `.env`: capability — существующий `clausal`
  (`ANKYRA_LOGIC`, по умолчанию off); `clause_goal` и `existential_disjunction` —
  производные `FragmentFeature`, а не процедуры.
- Без NL-эвристик и подгонки под id (`docs/task.md` §3.8;
  `docs/coverage_ceiling.md` §8).

## 4. T4 — конструкт и решение

### 4.1 Прочтение

`φ` — пропозициональная формула над **ground**-литералами (каждый атом — именованный
факт). Классически `T ⊨ φ` тогда и только тогда, когда `T ∧ ¬φ` невыполнимо; `T ⊨ ¬φ`
тогда и только тогда, когда `T ∧ φ` невыполнимо. На закоммиченном конечно-доменном
клаузальном фрагменте это ровно два ограниченных резолюционных опровержения.

### 4.2 Процедура решения (переиспользование ограниченной резолюции)

Храним **CNF `φ`** как `Query.goal_clauses: list[list[Morphism]]` (каждый внутренний
список — дизъюнкция литералов-Morphism'ов). Пусть `A(φ) = { frozenset(literal_of(l)) |
l ∈ C }` для каждой клаузы `C`.

- **supported** — `refute_support(clausification, CNF(¬φ))` выводит пустую клаузу, где
  `CNF(¬φ)` — декартово произведение отрицаний литералов `goal_clauses`
  (`¬(C₁ ∧ … ∧ Cₘ) = ∨ᵢ ¬Cᵢ`, поэтому каждый выбор одного литерала из клаузы даёт
  клаузу `{¬l₁, …, ¬lₘ}`).
- **refuted** — `refute_support(clausification, A(φ))` выводит пустую клаузу.
- **contradiction** — следуют оба.
- иначе **unknown**; исчерпанный бюджет шагов — **budget** (`insufficient`, никогда не
  доказательство).

### 4.3 Почему это состоятельно и обще

- **Состоятельно.** Оба направления предполагают формулу и выводят пустую клаузу;
  записываются только реальные резолюционные рёбра. `T ∧ ¬φ` невыполнимо — это
  определение `T ⊨ φ`, а доказыватель состоятелен (только реальная пустая клауза —
  `entailed`).
- **Обще.** У любой пропозициональной формулы есть CNF, а отрицание через декартово
  произведение точное, поэтому те же два опровержения решают любую ground-формулу во
  фрагменте.
- **Наивная альтернатива несостоятельна и отвергнута.** Рекурсивное структурное решение,
  читающее `T ⊨ φ₁ ∨ φ₂` как `T ⊨ φ₁ или T ⊨ φ₂`, неверно (`T = {p ∨ q}` влечёт
  `p ∨ q`, хотя ни один дизъюнкт). Проверка через невыполнимость — правильная.
- **Ограниченность.** Каждое направление — один ограниченный резолюционный поиск;
  исчерпание — `insufficient`.

## 5. Решения по устройству T4

- **T4-D1 — Представление (закрывает T-D2).** (a) `Query.goal_clauses:
  list[list[Morphism]]` с CNF ground-цели, `goal_mode="cnf"` и
  `Query.target = goal_clauses[0][0]` для эха/ответа; парсер понижает gold-формулу в
  CNF. (b) Рекурсивная модель `GoalFormula` с NNF/CNF в движке: точнее рендерит, но
  новая рекурсивная модель и более широкое изменение `Query`/движка. (c) Новые значения
  `goal_mode`: формы не выражают. **DECIDED (a)**; (b) зафиксировано как альтернатива.
- **T4-D2 — Решение.** (a) Два вызова `refute_support` (§4.2): `CNF(¬φ)` для поддержки,
  `A(φ)` для опровержения. (b) Рекурсивное структурное следование — **несостоятельно**
  для `∨`. **DECIDED (a)**; (b) отвергнуто.
- **T4-D3 — Именование фрагмента.** (a) Добавить производный `FragmentFeature`
  `clause_goal` (`goal_mode == "cnf"`), отображаемый в клаузальный фрагмент: аудируемое
  имя и место для routing-контроля, без нового capability/флага. (b) Переиспользовать
  `compound_goal`. **DECIDED (a)** (зеркалит T1-D3/T3-D3/T5-D3).
- **T4-D4 — Объём.** (a) Только **ground**-формулы: без квантора и свободной переменной
  в цели. Квантифицированное тело внутри составной цели остаётся `out_of_fragment`.
  (b) Обобщить до квантифицированных подформул — отложено (это смешение goal-*формулы*
  T1/T3 с T4, не требуется). **DECIDED (a).**

## 6. T2 — конструкт и решение

### 6.1 Прочтение

`∃x (A(x) ∧ (B(x) ∨ C(x)))` Skolemize в `A(sk) ∧ (B(sk) ∨ C(sk))` — unit-клауза и
бинарная клауза над одной свежей константой. В общем случае тело `φ(x)` — CNF над
литералами от `x`, и каждая клауза становится ground-клаузой над `sk`.

### 6.2 Процедура решения

`_add_existentials` порождает для i-го экзистенциала свежую `sk{i}` и ground-клаузы
`φ(sk{i})`: по одной unit-клаузе на атом и по одной клаузе на дизъюнктивную группу.
Дальше любая цель над Skolem-константой решается существующей ограниченной резолюцией;
новой процедуры нет.

### 6.3 Почему это состоятельно и обще

- **Состоятельно.** Skolemization сохраняет выполнимость: свежая константа нигде больше
  не встречается, поэтому испущенные ground-клаузы — это ровно (Skolemized) экзистенциал.
- **Обще.** CNF-тело покрывает любую пропозициональную комбинацию литералов от `x`;
  `∃x ((A∧B) ∨ C)` нормализуется в `∃x ((A∨C) ∧ (B∨C))` до Skolemization.
- **Ограниченность.** Одна свежая константа на экзистенциал; набор клауз конечен, а
  бюджет шагов ограничивает поиск.

## 7. Решения по устройству T2

- **T2-D1 — Представление.** (a) Добавить `Existential.disjunctions:
  list[list[Morphism]]` (каждый внутренний список — дизъюнкция литералов от переменной);
  `atoms` остаются unit-клаузами, поэтому `atoms` + `disjunctions` — CNF тела. Обратно
  совместимо (по умолчанию пусто) и зеркалит именование `Rule.consequence`/`alternatives`.
  (b) Заменить `atoms` единым `clauses: list[list[Morphism]]` — чище по имени, но широкий
  churn по билдеру, парсеру, symbolic-проверкам и тестам без лишней выразительности.
  **DECIDED (a)**; (b) зафиксировано как альтернатива.
- **T2-D2 — Решение.** Skolemize CNF: одна unit на атом, одна ground-клауза на
  дизъюнктивную группу (§6.2). **DECIDED.**
- **T2-D3 — Именование фрагмента.** (a) Добавить производный `existential_disjunction`
  `FragmentFeature` (экзистенциал с дизъюнктивной частью), отображаемый в клаузальный
  фрагмент, без нового capability/флага. (b) Переиспользовать `existential`.
  **DECIDED (a)** (зеркалит шаблон T1/T3/T5).
- **T2-D4 — Объём тела.** (a) Одна переменная; тело — CNF литералов от неё (NNF затем
  CNF); вложенные кванторы и функциональные термы остаются `out_of_fragment`.
  (b) Обобщить до вложенных кванторов — отложено. **DECIDED (a).**

## 8. Изменения движка

- **`core/models.py`.** `GoalMode` получает `"cnf"` (`core/models.py:23–27`); `Query`
  получает `goal_clauses: list[list[Morphism]]` (`core/models.py:242–262`); `Existential`
  получает `disjunctions: list[list[Morphism]]` (`core/models.py:185–196`), с
  документированием `atoms` + `disjunctions` как CNF тела.
- **`engine/clause.py`.**
  - `_add_existentials` (`engine/clause.py:270–287`): испускать unit-клаузу на атом и
    ground-клаузу на дизъюнктивную группу над `sk{i}` (тавтологию пропускать).
  - `_class_names` (`engine/clause.py:127`): также сканировать `existential.disjunctions`
    (их `is_a`-объекты — имена классов для домена индивидов T5).
- **`engine/verify.py`.**
  - Хелперы `_cnf_assumed(goal_clauses)` и `_cnf_assumed_negated(goal_clauses)`
    (units / декартово произведение отрицаний литералов).
  - `_cnf_outcome(clausification, clauses, budget)` → `(outcome, target_result,
    complement_result, {})` по §4.2.
  - `_goals_of` (`engine/verify.py:269–274`) по-прежнему возвращает единичный якорь
    (`Query.target`) при `goal_mode == "cnf"`, чтобы выбралась клаузальная диспетчеризация;
    ветка `cnf` в `l2_outcomes` читает `goal_clauses` напрямую.
  - `l2_outcomes` (`engine/verify.py:570–597`): при `goal_mode == "cnf" and
    query.goal_clauses` запускать `_cnf_outcome` и вернуть один исход; остальное не
    меняется.
  - `_l2_status` (`engine/verify.py:469–497`): `"cnf"` отображает единичный исход как
    `"forall"` (`supported→supported`, `refuted→refuted`, `contradiction`,
    `budget→insufficient`, `unknown→unsupported`).
  - `_verify_l2` (`engine/verify.py:532–567`): включить `"cnf"` в проверку неиспользованных
    посылок (её положительное доказательство — доказательство `refute_support`).
- **`engine/inference.py`.** Добавить `"clause_goal"` и `"existential_disjunction"` в
  `FragmentFeature` (`engine/inference.py:28`); `_has_clause_goal(query)` и
  `_has_existential_disjunction(theory)`; добавить оба в `_fragment`
  (`engine/inference.py:116`). Маршрутизация не меняется: `compound_goal`/`existential`
  уже выбирают `clausal`.
- **`engine/explain.py`.** `_goal_label` (`engine/explain.py:405`): рендерить cnf-цель
  как `(l₁ OR l₂) AND (l₃)`; `_l2_explanation` уже использует `target.proof` /
  `complement.proof`.
- **`build/enrich.py`.** `_rewrite_existential` (`build/enrich.py:75–78`) также
  переписывать `disjunctions`; `_valid_existential` (`81–84`) принимать чисто
  дизъюнктивное тело.
- **`build/symbolic.py` / `build/unroll.py` / `build/extract.py`.** Включить
  `existential.disjunctions` там, где сканируется/рендерится `existential.atoms`
  (`symbolic.py:217–218`; `unroll._unroll_existentials:272–288`; `extract.py:397–401`).
  Извлечение формы с вложенной дизъюнкцией в Phase 0 — **G-трек**; `unroll` просто
  прокидывает поле, когда `ProblemStructure` его несёт.

## 9. Парсер gold-fed (`evals/folio_fol.py`)

- **T4.** В `_conclusion` (`evals/folio_fol.py:353–380`), после NNF, когда ни одна форма
  выше не подошла и формула **ground** (нет узла `∀`/`∃`, нет свободного терма
  `_VARIABLES`), посчитать её CNF (`_cnf`) и вернуть `goal_clauses` с `goal_mode="cnf"`,
  `target = clauses[0][0]`. `_conclusion` возвращает 4-кортеж
  `(target, goals, goal_mode, goal_clauses)`; `to_theory_query`
  (`evals/folio_fol.py:403–434`) передаёт `goal_clauses` в `Query` и включает атомы клауз
  в `_object_names`. Заменить текущий плоский отказ на строке 380.
- **T2.** В `_existential_premise` (`evals/folio_fol.py:317–327`) сделать NNF, затем CNF
  тела; разложить на `atoms` (unit-клаузы) и `disjunctions` (многолитеральные клаузы);
  возбуждать `FolParseError` при кванторе в клаузе, пустой клаузе или терме, отличном от
  переменной экзистенциала. `_object_names` должен включать атомы дизъюнкций.

## 10. Синтетические гейты

### `evals.l2_synthetic`

Добавить механизм `clause_goal` (T4) и `existential_disjunction` (T2), с обязательными
контролями. `_query` получает `goal_clauses=()`, а `_theory` уже принимает словари
экзистенциалов (теперь с `disjunctions`).

| кейс | теория / цель | ожидание |
|---|---|---|
| `clause-goal-01` | `A`, `B`, `A∧B→C`, `A∧B→D`; цель `(A∧B)→(C∧D)` | `supported`, `yes` |
| `clause-goal-02` | только `A`, `B`; цель `(A∨B)→C` | `insufficient` (**soundness-контроль**: несостоятельное чтение «плоская `∨` из следований» дало бы yes) |
| `clause-goal-03` | `A`, `B`, `¬C`; цель `(A∨B)→C` | `refuted`, `no` |
| `clause-goal-04` | `clause-goal-01` с `LOGIC_BUDGET=1` | `insufficient`, никогда не proven |
| `clause-goal-05` | `clause-goal-01` при `logic="off"` | `out_of_fragment:compound_goal` |
| `exist-or-01` | `∃x(p(x) ∧ (q(x)∨r(x)))`, `p→¬r`; цель `q(sk0)` | `supported`, `yes` |
| `exist-or-02` | `∃x(p(x) ∧ (q(x)∨r(x)))`; цель `q(sk0)` | `unsupported`/`insufficient`, `unknown` |
| `exist-or-03` | `∃x(p(x) ∧ (q(x)∨r(x)))`, `p→q`; цель `¬q(sk0)` | `refuted`, `no` |
| `exist-or-04` | `exist-or-01` с `LOGIC_BUDGET=1` | `insufficient`, никогда не proven |
| `exist-or-05` | `exist-or-01` при `logic="off"` | `out_of_fragment:existential` |
| `exist-or-06` | `exist-or-01` с атомом над другой свободной переменной | `out_of_fragment` (истинный вложенный квантор отвергается парсером; `tests/test_evals_folio_fol.py`) |

Плюс кейсы `routing_synthetic`, проверяющие, что `clause_goal` и
`existential_disjunction` маршрутизируются в `clausal` при включённом `ANKYRA_LOGIC`.

## 11. Тесты и верификация

Прототип (LLM-free, не закоммичен): T4 решает `0073`→`supported` и `0020`→`refuted`;
T2 решает `0006`→`yes`, `0007`→`unknown`, `0008`→`unknown`; все шесть совпадают с
метками. Ожидаемый суммарный гейт:

| метрика | базис | ожидание |
|---|---|---|
| gold-fed open (верно) | 35/45 | **40/45** |
| gold `out_of_fragment` | 6/45 | **1/45** (только `0109`) |
| охват (метод) | 39/45 | **44/45** |
| covered gold-fed | 35/39 | **40/44** |
| grounded false proofs | 0 | **0** |

- `tests/test_engine_logic_l2.py`: поддержка/опровержение cnf-цели/бюджетный контроль;
  поддержка экзистенциала с вложенной дизъюнкцией и его негативный контроль;
  существующие кейсы остаются зелёными.
- `tests/test_engine_resolution.py`: `refute_support` с многоклаузальным предположением
  (`CNF(¬φ)`), и `_add_existentials`, испускающий дизъюнктивную Skolem-клаузу.
- `tests/test_evals_folio_fol.py`: заменить
  `test_conditional_compound_conclusion_is_out_of_fragment` на тест разбора
  `B(a)∧C(a)→D(a)∧E(a)` → `goal_mode="cnf"`; добавить тест разбора экзистенциала с
  вложенной дизъюнкцией; обновить
  `test_gold_l2_shared_witness_with_a_nested_premise_is_fragment` (`0008` теперь покрыта)
  на `not result["fragment"]` и ответ `Uncertain`.
- `tests/test_engine_inference.py` / `tests/test_evals_routing_synthetic.py`: два признака
  и их routing-контроли.
- `uv run pytest` (offline) — полный регресс.
- `uv run python -m evals.l2_synthetic` — новый итог, **0 mismatches**.
- `uv run python -m evals.routing_synthetic` — зелёный.
- `uv run python -m evals.analyze_folio --subset l2` — LLM-free gold-fed повторный замер:
  охват вверх (до 44/45), `out_of_fragment` вниз (до 1/45), **0 grounded false proofs**.
  Записать до/после в `docs/folio_gold_fed.md`.

## 12. Риски

- **Звуковость T4 — это направление `∨`.** Реализация, решающая `φ₁ ∨ φ₂` по
  следованию дизъюнкта (или неверно отрицающая CNF), допускает ложное `yes`.
  Синтетический контроль `clause-goal-02` — специальный негативный тест; gold-fed
  повторный замер требует **0 grounded false proofs**.
- **Раздувание CNF и стоимость.** Размер декартова произведения экспоненциален по числу
  клауз; закоммиченные цели крошечны, а бюджет шагов ограничивает поиск (исчерпание —
  `insufficient`).
- **Свежесть Skolem в T2.** Одна свежая константа на экзистенциал, отсутствующая в
  теории; коллизия была бы несостоятельна. Гарантировать уникальность, как в T1/T3/T5.
- **Утечка вложенных кванторов.** `∃x(p(x) ∧ ∃y q(x,y))` должен отказать, а не быть
  молча уплощён. Синтетический контроль `exist-or-06` это охраняет.
- **Точность объяснения.** Cnf-цель рендерит свою клаузальную форму; каждый шаг
  по-прежнему должен отображаться в реальное резолюционное ребро.
- Никакого полного живого прогона FOLIO без отдельного бюджетного решения
  (`docs/reasoning_roadmap.md` §4).

## 13. Порядок работ (вехи)

1. Движок T4: `Query.goal_clauses`/`goal_mode="cnf"`, `_cnf_outcome`, проводка `verify`;
   юнит-тесты. (Ничего живого не гейтит.)
2. Движок T2: `Existential.disjunctions`, `_add_existentials`, `_class_names`, сканы
   билдера/symbolic; юнит-тесты.
3. Синтетические кейсы `clause_goal` + `existential_disjunction` (сначала
   soundness-контроли); `evals.l2_synthetic` зелёный.
4. Признаки `clause_goal` + `existential_disjunction` и routing-синтетические кейсы.
5. Gold-парсер + тесты парсера; LLM-free gold-fed повторный замер; зафиксировать дельту.
6. Документы: `coverage_ceiling.md` (T4/T2 done + числа), `folio_gold_fed.md`,
   `l2_plan.md`, `reasoning_roadmap.md`, `implementation_plan.md` пункт 26;
   зеркало `docs/t4_t2_plan_ru.md`.

Каждая веха ложится отдельно ревьюируемой; soundness-гейты (шаг 3) предшествуют
gold-fed повторному замеру (шаг 5).

## 14. Ограничители

- Оба конструкта входят как **именованные фрагменты** (`docs/fragment_routing.md`); за
  пределами закоммиченной формы остаётся честный `out_of_fragment`.
- **Никогда не понижать семантику, чтобы пройти строку** (`docs/coverage_ceiling.md`
  §8): не решать дизъюнкцию по дизъюнкту, не выбрасывать вложенную дизъюнкцию.
- Без подгонки под id; LLM-free gold-fed граница — бесплатный гейт после пункта: охват
  вверх, **0 grounded false proofs**.

## 15. Результаты

Реализовано (решения T4-D1a…D4a и T2-D1a…D4a). LLM-free проверка, 2026-09-22:

| гейт | до | после |
|---|---|---|
| `evals.l2_synthetic` | 41/41 | **52/52** (`clause_goal` + `existential_disjunction`) |
| `evals.routing_synthetic` | 15/15 | **17/17** (два новых признака) |
| `uv run pytest` | 464 passed | **476 passed**, 26 skipped |

FOLIO L2 тир a, gold-fed (`uv run python -m evals.analyze_folio --subset l2`):

| метрика | до | после |
|---|---|---|
| gold-fed open (верно) | 35/45 | **40/45** |
| gold `out_of_fragment` | 6/45 | **1/45** |
| охват (метод) | 39/45 | **44/45** |
| covered gold-fed | 35/39 | **40/44** |
| grounded false proofs | 0 | **0** |

T4 решил `0073` (`supported`/`True`) и `0020` (`refuted`/`False`); T2 решил `0006`
(`yes`/`True`), `0007` (`unknown`/`Uncertain`) и `0008` (`unknown`/`Uncertain`).
Единственная оставшаяся строка `out_of_fragment` — битая аннотация `0109`.
Soundness-контроли `clause-goal-02` (дизъюнкция не решается по дизъюнкту) и
`exist-or-02`/`exist-or-06` держатся, а gold-fed повторный замер даёт 0 grounded false
proofs.
