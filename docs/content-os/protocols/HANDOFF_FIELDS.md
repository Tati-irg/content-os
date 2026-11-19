АРХИВ · снимок протокола на 9 ноября 2026. Рабочий вход — docs/content-os/README.md.
Ссылки на прежние рабочие данные и команды сохранены для справки.

# Единая таблица передачи между модулями

Версия: draft v1, 2026-10-08. Основа: 00 (v1.5), 06 draft v1, решения D-01…D-04.

Зачем она нужна. Сейчас каждый модуль ждёт на входе свой набор полей, и наборы не совпадают. Из-за этого 07 и 09 по своим же правилам встают на «данных недостаточно». Эта таблица становится единственным источником правды: на шаге 4 списки «вход» и «выход» в 07, 08, 09 заменяются ссылкой на неё.

Обозначения: **О** обязательно, **У** если применимо (условие написано рядом), **—** не нужно.

---

## 1. Шапка любой передачи

Есть у каждой передачи от модуля к модулю (00, раздел «Handoff State»).

| Поле | Что это |
|---|---|
| FROM / TO | кто передаёт и кому |
| CYCLE ID / CYCLE RUN ID | какой цикл |
| RELEVANT ID | RESEARCH RESULT ID, STRATEGY DECISION ID или CONTENT ASSET ID |
| ASSET VERSION | какая версия материала (для production) |
| STATUS | состояние по словарю 00 (ASSET STATE) |
| DATE | когда |
| SUMMARY | одна-две фразы, что передаётся |
| REQUIRED ACTION | что должен сделать получатель |

---

## 2. Исследование → 06 (01, 02, 03, 04, 05)

Тело отчёта у каждого модуля своё, оно уже описано в протоколах 01–05. Общим должно быть только это:

| Поле | О/У |
|---|---|
| RESEARCH RESULT ID | О |
| MODULE | О |
| RESEARCH PERIOD | О |
| SCOPE / SAMPLE (платформы, сколько материалов, языки) | О |
| DATA SOURCES (+ что было недоступно) | О |
| KEY FINDINGS с тегами [FACT] / [OBSERVATION] / [INTERPRETATION] / [HYPOTHESIS] / [DATA INSUFFICIENT] | О |
| LIMITATIONS | О |
| SIGNALS FOR 06 (финальный блок модуля) | О |
| MODULE STATUS: RECEIVED / PARTIAL / NOT_AVAILABLE / DATA INSUFFICIENT | О |

---

## 3. 06 → производство (главная таблица)

Колонки: **A** обычный asset (пост, Telegram, Threads, Stories), **A-Reel**, **B** карусель через 07, **C** самостоятельная карусель через 09.
Получатель: в A, A-Reel и B это 07, в C это 09.

| Поле | A | A-Reel | B | C | Комментарий |
|---|---|---|---|---|---|
| STRATEGY DECISION ID | О | О | О | О | |
| CONTENT ASSET ID | О | О | О | О | |
| CONTENT FAMILY ID | У | У | У | У | если из одного решения выходит несколько assets |
| CYCLE ID / CYCLE RUN ID | О | О | О | О | |
| SLOT ID (дата, канал) | О | О | О | О | слоты назначает 06 |
| PLATFORM | О | О | О | О | |
| FORMAT | О | О | О | О | |
| RUBRIC: Мужчины / Женщины / Отношения / Секс / Наука / Кейсы / Полезность | О | О | О | О | 00 раздел 57 |
| GENDER MODE: для мужчин / для женщин / общий | О | О | О | О | мужчинам действия, женщинам можно эмоции, общий нейтрально (00 раздел 14) |
| PLATFORM SET: Telegram, VK, Threads, сторис-подводка | О | О | О | О | комплект к каждой теме дня, свой SLOT ID у каждого (00 раздел 58) |
| PRODUCTION ROUTE | О | О | О | О | |
| PUBLICATION MODE: STANDARD / TEST | О | О | О | О | TEST только после «тест» на GATE 1 |
| TEST HYPOTHESIS + METRIC + REVIEW DATE | У | У | У | У | если TEST |
| TOPIC | О | О | О | О | |
| CORE PROBLEM | О | О | О | О | |
| AUDIENCE LANGUAGE | О | О | О | О | дословно из 02, если есть; иначе DATA INSUFFICIENT |
| WHO IS CONTENT ABOUT | О | О | О | О | |
| WHO IS IT FOR | О | О | О | О | |
| WHO IS EXPECTED TO ACT | О | О | О | О | |
| RELATIONAL POSITION | О | О | О | О | |
| STRATEGIC ANGLE | О | О | О | О | |
| PRIMARY FUNCTION | О | О | О | О | |
| CORE MESSAGE | О | О | О | О | одна фраза |
| SECONDARY MESSAGES | У | У | У | У | |
| HOOK DIRECTION | О | О | О | О | направление, не готовый hook |
| DEPTH | О | — | О | О | у Reel вместо неё TARGET DURATION |
| VIRAL DNA (механизм из 04) | У | У | У | У | если выбран механизм |
| SCIENCE REQUIREMENT + RESEARCH RESULT ID из 05 | У | У | У | У | если есть научная опора |
| REQUIRED SOURCE MATERIAL | У | У | У | У | ссылки на материалы 01–05 |
| CLIENT POTENTIAL | О | О | О | О | |
| CTA FUNCTION | О | О | О | О | |
| VISUAL DIRECTION | О | О | О | О | |
| FACT-CHECK REQUIREMENT | О | О | О | О | при сомнении REQUIRED |
| SEPARATE VISUAL PRODUCTION REQUIREMENT | О | О | — | — | для каруселей визуал входит в 09 |
| RISKS | О | О | О | О | |
| **Только Reel** | | | | | |
| REEL FORMAT: A / B / C / D | — | О | — | — | cinematic, talking head, science, practice |
| TARGET DURATION | — | О | — | — | |
| AVATAR / REAL-FACE REQUIREMENT | — | О | — | — | |
| MANUAL STEPS (запись, обложка) | — | О | — | — | ручные шаги Татьяны |
| **Только карусель** | | | | | |
| SLIDE COUNT | — | — | О | О | число или диапазон внутри DEPTH |
| INFORMATION UNIT TARGET | — | — | О | О | |
| STRUCTURE MAP (функция каждого слайда) | — | — | О | О | функции задаёт 06, текст пишет 07 или 09 |
| REQUIRED CLAIMS | — | — | О | О | |
| REQUIRED EXPLANATIONS | — | — | О | О | |
| REQUIRED EXAMPLES / APPLICATIONS | — | — | У | У | |
| EVIDENCE REQUIREMENT | — | — | О | О | |
| LIMITATIONS / NUANCE | — | — | О | О | |
| TEMPLATE ID: T01 / T02 / T03 | — | — | О | О | без файла шаблона BLOCKED |
| ACCENT: wine / indigo / terracotta | — | — | У | У | не указан: 09 выбирает сам по теме; один акцент на карусель |
| VISUAL RULES | — | — | О | О | |
| PHOTO / VISUAL REQUIREMENT | — | — | О | О | из ACTIVE фотобанка или «без фото» |
| WHAT 09 MUST PRESERVE | — | — | О | О | |
| WHAT 09 MUST NOT ADD | — | — | О | О | |

Правило пустой клетки: если обязательное поле заполнить нельзя, пишется **DATA INSUFFICIENT + причина**. Пустое поле означает, что handoff не принят.

---

## 4. 07 → 08 и 09 → 08 (на фактчек)

| Поле | О/У |
|---|---|
| CONTENT ASSET ID + ASSET VERSION (или PLATFORM VERSION) | О |
| ORIGINATING MODULE (07 или 09) | О |
| PRODUCTION ROUTE | О |
| ПОЛНЫЙ ТЕКСТ ВЕРСИИ (текст, voice-over, caption, on-screen text, текст слайдов) | О |
| CLAIMS LIST: каждое проверяемое утверждение отдельно, с тегом | О |
| SOURCES: RESEARCH RESULT ID из 05 и другие источники | У |
| CHANGED CLAIMS (что изменилось с прошлой проверки) | У, при повторной проверке |
| HNE QC RESULT | О для текстовых assets |

## 5. 08 → обратно

Кому возвращается: Route A и Route B до сборки идут в 07, Route C и Route B после сборки (если 09 менял утверждение) идут в 09.

| Поле | О/У |
|---|---|
| FACT CHECK ID | О |
| CHECKED VERSION (ASSET VERSION / PLATFORM VERSION) | О |
| RETURN TO (07 или 09) | О |
| VERDICT: PASS / PASS WITH MINOR EDITS / REQUIRES FACTUAL REVISION / REQUIRES SOURCE VERIFICATION / DO NOT PUBLISH YET / DATA INSUFFICIENT | О |
| CLAIM TABLE: claim / type / source / evidence / scope / causality / verdict | О |
| CORRECTED WORDING | У |
| CLAIMS TO REMOVE | У |
| REQUIRED SOURCE ATTRIBUTION | У |
| REMAINING UNCERTAINTY | О |

---

## 6. 07 → 09 (только Route B, после 07 FINAL EDIT)

07 передаёт **всё из колонки B раздела 3 без изменений** плюс:

| Поле | О/У |
|---|---|
| ASSET VERSION (проверенная) | О |
| FACT CHECK ID + VERDICT | У, если fact-check был |
| HNE QC RESULT | О |
| ТЕКСТ ПО СЛАЙДАМ: для каждого слайда из STRUCTURE MAP: SLIDE ID, PURPOSE, CORE COPY, SUPPORTING COPY, INFORMATION UNIT(S), EVIDENCE FLAG, SOURCE / FACT CHECK LINK | О |
| ACTUAL INFORMATION UNITS (сколько вышло) | О |
| CAPTION к посту | О |

09 после этого меняет только визуал, порядок и вёрстку. Любое новое или изменённое утверждение отправляет asset обратно в 08 (D-02).

---

## 7. → GATE 2 (Татьяне на финальное одобрение)

Asset попадает сюда только в состоянии AWAITING_HUMAN_APPROVAL.

| Что видит Татьяна | О/У |
|---|---|
| сам материал: текст, слайды, сценарий, caption | О |
| канал и дата (SLOT) | О |
| ЗАЧЕМ: primary function одной фразой | О |
| ПРОВЕРКИ: fact-check, HNE QC, Voice DNA, Carousel QC (для каруселей) | О |
| ЧТО ПОД ВОПРОСОМ: оставшаяся неопределённость | У |
| ТВОИ РУЧНЫЕ ШАГИ: запись, обложка | У |

Ответ: «ок» / «нет» / «доработать: …». Как и на GATE 1, одним сообщением на весь пакет.

## 8. Публикация (GATE 3) и обратно в 01

| Поле | О/У |
|---|---|
| CONTENT ASSET ID + PUBLISHED VERSION | О |
| SLOT ID | О |
| PUBLISHED AT (дата и время) | О |
| URL / POST ID | О |
| PUBLISHED BY (вручную / автоматически) | О |
| METRIC REVIEW DATE | О для TEST, У для остальных |

Без этой записи asset не считается опубликованным (00, GATE 3).

---

## Что это меняет на шаге 4

- **07:** вход заменить на колонки A, A-Reel, B раздела 3; добавить выход в 08 (раздел 4) и в 09 (раздел 6); убрать статус PUBLISH-READY.
- **08:** вход из раздела 4 от 07 **и** от 09; возврат по правилу раздела 5; выдавать FACT CHECK ID.
- **09:** вход из колонки C (Route C) или раздела 6 (Route B); выход в 08 при новом утверждении; отдача на GATE 2 по разделу 7.
- **01–05:** добавить общую шапку раздела 2 в финальный отчёт.
