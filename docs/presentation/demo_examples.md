# Демонстрационные примеры для семинара

Все команды выполняются из корня репозитория Ankyra. Перед первым запуском:

```bash
uv sync
```

`--lang ru` задаёт язык пояснения и заключения. Текст задачи можно подавать
на русском; предикаты в Prolog-выводе остаются каноническими английскими
идентификаторами. Команды ниже читают текст из stdin, поэтому их можно
копировать целиком.

| № | Стадия | Коллекция | Что показывает | Ожидаемый итог |
|---|---|---|---|---|
| 1 | L0 | ProofWriter | дедукция, хорновские правила | `yes / proven` |
| 2 | L1 | ProntoQA | явное отрицание, цепочка классов | `no / proven` |
| 3 | L2 | ProntoQA-OOD | дизъюнкция и доказательство от противного | `yes / proven` |
| 4 | L2 | FOLIO | дизъюнкция и разбор случаев | `no / proven` |
| 5 | L2 | FOLIO (negation) | отрицание в реальном тексте | `yes / proven` |
| 6 | L3 | AR-LSAT | конечная CSP, отдельный решатель | `вариант E / determined` |
| 7 | L4 | GSM8K | точная арифметика, отдельный решатель | `57500 / determined` |
| 8 | — | Ankyra | гипотеза и `proven_under(H)` | `binding / proven_under` |
| 9 | — | Ankyra | честный отказ вне фрагмента | `out_of_fragment:compound_goal` |

---

## 1. L0 / ProofWriter: дедукция

Источник: ProofWriter (AI2), простой хорновский пример.

```bash
uv run python -m ankyra.cli.solve --lang ru <<'EOF'
Анна милая. Все милые люди холодны. Холодна ли Анна?
EOF
```

Ожидаемо: `Answer: Yes`, сила `proven`.

---

## 2. L1 / ProntoQA: отрицание

Источник: ProntoQA, цепочка классов с явным отрицанием.

```bash
uv run python -m ankyra.cli.solve --lang ru --world-assumption open <<'EOF'
Каждая крапивница — бабочка. Каждая бабочка — чешуекрылое. Чешуекрылые — насекомые. Насекомые — членистоногие. Членистоногие не имеют костей. Салли — крапивница. Имеет ли Салли кости?
EOF
```

Ожидаемо: `Answer: No`, сила `proven`.

---

## 3. L2 / ProntoQA-OOD: дизъюнкция и доказательство от противного

Источник: ProntoQA-OOD, пример `1hop_OOD_ProofByContra...`.
Нужен клаузальный решатель L2:

```bash
ANKYRA_LOGIC=ground uv run python -m ankyra.cli.solve --lang ru <<'EOF'
Всё, что является нумпусом или вомпусом, является бримпусом. Всё, что является вумпусом или юмпусом, является бримпусом. Всё, что является вумпусом или юмпусом, является импусом. Рен — не лемпус. Рен — не бримпус.
Докажите: Рен — не юмпус и не вумпус.
EOF
```

Ожидаемо: `Answer: Yes`, сила `proven`.

---

## 4. L2 / FOLIO: дизъюнкция и разбор случаев

Источник: FOLIO validation-0010. Нужен клаузальный решатель L2:

```bash
ANKYRA_LOGIC=ground uv run python -m ankyra.cli.solve --lang ru <<'EOF'
Есть шесть видов диких индеек: восточная, Осцеола, Гулда, Мерриама, Рио-Гранде и глазчатая. Том — не восточная дикая индейка. Том — не индейка Осцеола. Том также не индейка Гулда, не индейка Мерриама и не индейка Рио-Гранде. Том — дикая индейка.
Верно ли, что Том — восточная дикая индейка?
EOF
```

Ожидаемо: `Answer: No`, сила `proven`.

---

## 5. L2 / FOLIO: срез с отрицанием

Источник: FOLIO validation-0135 (negation-срез). Нужен клаузальный решатель L2:

```bash
ANKYRA_LOGIC=ground uv run python -m ankyra.cli.solve --lang ru <<'EOF'
Плунжеры всасывают. Пылесосы всасывают. Вампиры всасывают. Космос — это вакуум. Щётка для пыли — бытовой прибор, который не всасывает.
Верно ли, что Космос всасывает?
EOF
```

Ожидаемо: `Answer: Yes`, сила `proven`.

---

## 6. L3 / AR-LSAT: конечная CSP

Источник: AR-LSAT, игра `201110_2-G_1_1` (парковка).
Нужен CSP-решатель и отдельный трек:

```bash
ANKYRA_CSP=true uv run python -m ankyra.cli.solve --lang ru --track csp <<'EOF'
Администратор должен распределить парковочные места между шестью новыми сотрудниками: Робертсон, Соуза, Тогова, Вон, Сюй и Янг. Каждому из шести сотрудников нужно выделить одно из мест: #1, #2, #3, #4, #5 или #6. Два сотрудника не могут получить одно и то же место. Правила: Янг должен получить место с большим номером, чем Тогова. Сюй должен получить место с большим номером, чем Соуза. Робертсон должен получить место с большим номером, чем Янг. Робертсон должен получить место #1, #2, #3 или #4.
Какой из вариантов может быть распределением парковочных мест?
A. #1: Янг; #2: Соуза; #3: Вон; #4: Робертсон; #5: Тогова; #6: Сюй
B. #1: Вон; #2: Тогова; #3: Янг; #4: Соуза; #5: Робертсон; #6: Сюй
C. #1: Тогова; #2: Янг; #3: Сюй; #4: Робертсон; #5: Соуза; #6: Вон
D. #1: Тогова; #2: Робертсон; #3: Янг; #4: Соуза; #5: Вон; #6: Сюй
E. #1: Соуза; #2: Тогова; #3: Янг; #4: Робертсон; #5: Сюй; #6: Вон
EOF
```

Ожидаемо: вариант **E**, статус `determined`.

Если извлечение из русского текста окажется нестабильным, используйте
английский оригинал:

```bash
ANKYRA_CSP=true uv run python -m ankyra.cli.solve --lang ru --track csp <<'EOF'
An administrator must assign parking spaces to six new employees: Robertson, Souza, Togowa, Vaughn, Xu, and Young. Each of the six employees must be assigned one of the following parking spaces: #1, #2, #3, #4, #5, or #6. No two employees can be assigned the same parking space. The following rules govern the assignment of parking spaces: Young must be assigned a higher-numbered parking space than Togowa. Xu must be assigned a higher-numbered parking space than Souza. Robertson must be assigned a higher-numbered parking space than Young. Robertson must be assigned parking space #1, #2, #3, or #4.
Which one of the following could be the assignment of parking spaces to the new employees?
A. #1: Young; #2: Souza; #3: Vaughn; #4: Robertson; #5: Togowa; #6: Xu
B. #1: Vaughn; #2: Togowa; #3: Young; #4: Souza; #5: Robertson; #6: Xu
C. #1: Togowa; #2: Young; #3: Xu; #4: Robertson; #5: Souza; #6: Vaughn
D. #1: Togowa; #2: Robertson; #3: Young; #4: Souza; #5: Vaughn; #6: Xu
E. #1: Souza; #2: Togowa; #3: Young; #4: Robertson; #5: Xu; #6: Vaughn
EOF
```

---

## 7. L4 / GSM8K: точная арифметика

Источник: GSM8K test-0017. Нужен числовой решатель и отдельный трек:

```bash
ANKYRA_ARITH=true uv run python -m ankyra.cli.solve --lang ru --track numeric <<'EOF'
Джилл получает $20 в час за преподавание и $30 в час за тренерскую работу. Она работает 50 недель в году, 35 часов в неделю преподавателем и 15 часов в неделю тренером. Какова её годовая зарплата?
EOF
```

Ожидаемо: `57500`, статус `determined`.

Английский оригинал:

```bash
ANKYRA_ARITH=true uv run python -m ankyra.cli.solve --lang ru --track numeric <<'EOF'
Jill gets paid $20 per hour to teach and $30 to be a cheerleading coach. If she works 50 weeks a year, 35 hours a week as a teacher and 15 hours a week as a coach, what's her annual salary?
EOF
```

---

## 8. Ankyra: гипотеза и `proven_under(H)`

Здесь в тексте нет правил классов; модель предлагает их как гипотезы,
и ответ честно помечается `proven_under(H1, …)`. Гипотезы должны быть
разрешены (по умолчанию разрешены):

```bash
ANKYRA_ALLOW_HYPOTHESES=true uv run python -m ankyra.cli.solve --lang ru <<'EOF'
Транспортное средство X имеет двигатель, четыре колеса, 150 лошадиных сил и четыре двери. Что это за транспортное средство?
EOF
```

Ожидаемо: ответ-привязка (`binding`) с силой `proven_under(H1, …)`.
В живом логе будет видно, какую гипотезу предложила модель и как её
классифицировал решатель.

---

## 9. Ankyra: честный отказ вне фрагмента

Составной вопрос (конъюнкция целей) без включённого L2 — это
`out_of_fragment:compound_goal`, а не догадка:

```bash
ANKYRA_LOGIC=off uv run python -m ankyra.cli.solve --lang ru <<'EOF'
Идёт дождь. Если идёт дождь, земля мокрая. Мокрая ли земля и идёт ли дождь?
EOF
```

Ожидаемо: `Out of fragment: out_of_fragment:compound_goal`.

---

## Замечания для ведущего

- Для L2 обязателен `ANKYRA_LOGIC=ground`; иначе структура с дизъюнкцией
  будет отклонена как `out_of_fragment:non_horn`.
- Для L3 обязателен `ANKYRA_CSP=true` и `--track csp`.
- Для L4 обязателен `ANKYRA_ARITH=true` и `--track numeric`.
- Для L1 используется открытый мир (`--world-assumption open`), как в
  eval-адаптере ProntoQA.
- Если в `.env` стоит `ANKYRA_ALLOW_HYPOTHESES=false`, пример 8 покажет
  отказ; для демонстрации гипотез выставьте `true`.
- Для L3/L4 надёжнее английские оригиналы: извлечение сложной структуры
  из русского текста может быть менее стабильным, но пояснение и заключение
  всё равно будут на русском благодаря `--lang ru`.
