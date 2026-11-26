# Сквозная трассировка требований: каждое решение → источник → документ → проверка

**Область аудита:** все доступные решения текущей беседы и ранее сохранённой v0.5, актуализированные поправками 23.11.2026. `APPROVED` — явно принято пользователем; `APPROVED-CONCEPT` — принято направление, не детальная реализация; `OPEN` — требует решения. Никогда не превращать `OPEN` в утверждённое молча.

| ID | Согласование/источник | Требование | Статус | Основной файл | Проверка |
|---|---|---|---|---|---|
| REQ-001 | начальные обсуждения/утверждение модели данных | Одна основная PostgreSQL (PostgreSQL 17 выбран как базовая версия) с логическими схемами identity/content/learning/review/integration/audit; отдельные dev/prod БД. | APPROVED | [ARCHITECTURE.md](ARCHITECTURE.md) | Сверить профильный контракт + QA сценарий |
| REQ-002 | 19.11 скриншот стека | React 19/Vite/TypeScript; FastAPI; SQLAlchemy 2 + Alembic; Docker Compose; Caddy либо существующий reverse proxy; pytest/Vitest/Playwright. Точные фиксированные версии зависимостей проверять перед кодом. | APPROVED | [ARCHITECTURE.md](ARCHITECTURE.md) | Сверить профильный контракт + QA сценарий |
| REQ-003 | 19.11 Tiptap/Excalidraw | Полный отказ от Excalidraw. Собственный редактор на бесплатной MIT/open-source базе Tiptap. Не зависеть от платных расширений. | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | Сверить профильный контракт + QA сценарий |
| REQ-004 | 19.11 исходная архитектура | Новые React-компоненты, не наслаивать старую legacy JavaScript runtime. | APPROVED | [ARCHITECTURE.md](ARCHITECTURE.md) | Сверить профильный контракт + QA сценарий |
| REQ-005 | начальный архитектурный запрос | Авторизация Bitrix24 и серверные сессии. Bitrix24 — источник сведений о сотрудниках/структуре/админах, RTM — локальные роли, назначения и результаты. | APPROVED | [ACCESS_AND_ROLES.md](ACCESS_AND_ROLES.md) | Сверить профильный контракт + QA сценарий |
| REQ-006 | AGENTS.md/19.11 подтверждение | Роли developer > admin > editor > teacher > employee; авто-админ из Bitrix24, developer защищён. | APPROVED | [ACCESS_AND_ROLES.md](ACCESS_AND_ROLES.md) | Сверить профильный контракт + QA сценарий |
| REQ-007 | 19.11 worker принято | Фоновый worker отдельным Python-процессом/контейнером: Bitrix sync, Google Docs, уведомления, напоминания, контроль сроков; PostgreSQL queue для MVP, без Redis. | APPROVED | [ARCHITECTURE.md](ARCHITECTURE.md) | Сверить профильный контракт + QA сценарий |
| REQ-008 | 19.11 правки AGENTS | Код меняют только в локальном репозитории; на production правки исходников запрещены; commit/push/tag только после отдельной явной команды пользователя. | APPROVED | [../AGENTS.md](../AGENTS.md) | Сверить профильный контракт + QA сценарий |
| REQ-009 | 19.11 автодеплой main | Одобренный push в `main` должен запускать изолированный автодеплой Next с Alembic и проверками; старое приложение `/opt/rtm-app` не менять. | APPROVED | [../AGENTS.md](../AGENTS.md) | Сверить профильный контракт + QA сценарий |
| REQ-010 | 19.11 временная dev-БД | На временной dev-БД автоматические бэкапы не нужны; GitHub хранит код, но не фактическую БД; до реальных данных обязательны проверяемые бэкапы БД и файлов. | APPROVED | [../AGENTS.md](../AGENTS.md) | Сверить профильный контракт + QA сценарий |
| REQ-011 | 23.11 отклонено «Материалы» | Отдельного админ-раздела «Материалы» нет. Главный контентный раздел — «Курсы». | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | Сверить профильный контракт + QA сценарий |
| REQ-012 | 25.11.2026 новое решение | Статьи создаются в курсе или БЗ; тесты курса остаются внутри курса. | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | Сверить профильный контракт + QA сценарий |
| REQ-013 | 23.11 независимое копирование | Статью или тест можно скопировать из другого курса; создать **новый самостоятельный объект/UUID**, копию содержимого и настроек; дальнейшие изменения независимы; результаты сотрудников не копировать. | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | Сверить профильный контракт + QA сценарий |
| REQ-014 | 25.11.2026 новое решение | Google Docs в курсе выбирается из БЗ только как блок статьи. | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | Сверить профильный контракт + QA сценарий |
| REQ-015 | 25.11.2026 новое решение | Редакция принадлежит целой статье БЗ, а не Google Docs. | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | Сверить профильный контракт + QA сценарий |
| REQ-016 | 19.11 редакции/даты/ID | Редакция имеет UUID, отдельно номер и дату (UI DD.MM.YYYY); результат и подтверждение указывают точную редакцию. Бизнес-правило «одна дата — одна редакция» сохраняется, технически номер отдельно. | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | Сверить профильный контракт + QA сценарий |
| REQ-017 | 25.11.2026 новая модель | Редакция статьи БЗ создаётся без кампании; только отдельный запуск кампании создаёт назначения. | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | QA-127 |
| REQ-018 | 19.11 удаление admin/developer | Удаление **опубликованной** редакции только admin/developer; хранение результатов не должно нарушаться. | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | Сверить профильный контракт + QA сценарий |
| REQ-019 | 23.11 секции/DnD | Курс состоит из разделов; можно создавать/переименовывать/переставлять разделы; материалы сортируются DnD внутри и между разделами. | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | Сверить профильный контракт + QA сценарий |
| REQ-020 | 25.11.2026 новое решение | Элементы программы курса — статья и тест; медиа и Google Docs вставляются в статью. | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | Сверить профильный контракт + QA сценарий |
| REQ-021 | 25.11.2026 новое решение | Статья с медиа и Google Docs открывается внутри RTM с возвратом в курс. | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | Сверить профильный контракт + QA сценарий |
| REQ-022 | 25.11.2026 новое решение | Внутренняя статья курса Tiptap без пользовательских редакций. | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | Сверить профильный контракт + QA сценарий |
| REQ-023 | 25.11.2026 новая модель | Сохранение статьи, выпуск редакции статьи БЗ и запуск кампании — разные действия; черновик и контекст возврата защищены. | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-127 |
| REQ-024 | 23.11 окончательное согласование | Живой курс с постоянным UUID, без редакций; кампании указывают на курс, исторические действия сохраняются | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | Сверить профильный контракт + QA сценарий |
| REQ-025 | 19.11 независимый прогресс | Прогресс независимо у каждого назначения; автозачёт результатов из других курсов не входит в MVP. | APPROVED | [DATA_MODEL.md](DATA_MODEL.md) | Сверить профильный контракт + QA сценарий |
| REQ-026 | 23.11 таблица курсов | «Курсы» — компактная таблица, а не главная сетка карточек; поиск, фильтры, понятные действия. | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | Сверить профильный контракт + QA сценарий |
| REQ-027 | 25.11.2026 новое решение | Создать статью/тест либо скопировать из курса; медиа вставить в статью. | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | Сверить профильный контракт + QA сценарий |
| REQ-028 | 23.11 конструктор тестов одобрен | Конструктор тестов внутри курса; автоматические и свободные вопросы, баллы, картинки, попытки, таймер, порог, настройки результата и preview. | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | Сверить профильный контракт + QA сценарий |
| REQ-029 | 25.11.2026 новое решение | Видео RUTUBE или серверное видео воспроизводится внутри статьи MVP. | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | Сверить профильный контракт + QA сценарий |
| REQ-030 | 25.11.2026 новое решение | Единая БЗ содержит статьи и папки без раздельных зон видео и документов. | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | Сверить профильный контракт + QA сценарий |
| REQ-031 | 25.11.2026 новое решение | Полноценная База знаний с папками, ACL и статьями входит в MVP. | APPROVED | [MVP_CONTRACT.md](MVP_CONTRACT.md) | Сверить профильный контракт + QA сценарий |
| REQ-032 | 25.11.2026 новое решение | Папки произвольной вложенности; одна статья в одной папке. | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | Сверить профильный контракт + QA сценарий |
| REQ-033 | 25.11.2026 новое решение | Видео RUTUBE/MP4/WebM/MOV и аудио MP3/WAV доступны в MVP. | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | Сверить профильный контракт + QA сценарий |
| REQ-034 | 25.11.2026 новое решение | ACL папки/статьи по отделу, подотделу и сотруднику проверяется backend. | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | Сверить профильный контракт + QA сценарий |
| REQ-035 | 25.11.2026 новое решение | Однократный импорт Google Docs из таблицы; папки затем ведутся в RTM. | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-135 |
| REQ-036 | 23.11 мастер назначений | Курсы назначаются по отделам/подотделам/конкретным людям; выбор ответственных; сроки относительные и конкретной датой; уведомления и задачи Bitrix24 включаются раздельно. | APPROVED | [COURSE_ASSIGNMENTS.md](COURSE_ASSIGNMENTS.md) | Сверить профильный контракт + QA сценарий |
| REQ-037 | 23.11 задачи/уведомления | Название и описание задачи Bitrix24 редактируемые; предпросмотр; выбор дедлайна; запуск фиксирует кампанию/получателей и позволяет worker доставлять уведомления. | APPROVED | [COURSE_ASSIGNMENTS.md](COURSE_ASSIGNMENTS.md) | Сверить профильный контракт + QA сценарий |
| REQ-038 | 19.11 отдельно Управление редакциями | Согласование/публикация редакций — в отдельной вкладке «Управление редакциями», независимо от Центра проверок. | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | Сверить профильный контракт + QA сценарий |
| REQ-039 | 19.11 три вкладки Центра | Центр проверок **ровно 3 вкладки**: «Требует действий», «Проверка отдельных материалов», «Проверка курсов обучений». | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | Сверить профильный контракт + QA сценарий |
| REQ-040 | 19.11 заглушка Требует действий | «Требует действий» — **MVP только плашка**, позже персональная очередь ответственного: проверка, напоминания, выдача попыток, быстрые действия. | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | Сверить профильный контракт + QA сценарий |
| REQ-041 | 25.11.2026 новое решение | Отдельные кампании включают редакции статей БЗ и внутренние статьи/тесты. | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | Сверить профильный контракт + QA сценарий |
| REQ-042 | 19.11 проверка курсов | «Проверка курсов обучений» аналогично: активные кампании, по курсам/сотрудникам, прогресс по элементам, сроки, тесты, карточка в полном экране. | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | Сверить профильный контракт + QA сценарий |
| REQ-043 | 19.11 завершённые позже | Переключатель «Активные/Завершённые кампании» в двух вкладках запланирован, но завершённые — плашка следующей версии. | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | Сверить профильный контракт + QA сценарий |
| REQ-044 | 19.11 тесты в обеих | Старые 4 вкладки и отдельная проверка тестов отменены для Next: тесты проверяются через **материал** либо через **курс**, используя один движок. | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | Сверить профильный контракт + QA сценарий |
| REQ-045 | 19.11 всегда «Все действия» | В каждой карточке есть релевантное рекомендованное действие **и** постоянное меню «Все действия» со всеми разрешёнными операциями; не показывать только одну кнопку. | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | Сверить профильный контракт + QA сценарий |
| REQ-046 | 19.11 перечень действий | Действия: посмотреть ответы и попытки, напомнить, изменить срок, выдать попытки, проверить свободный ответ, освободить с причиной, вручную подтвердить с причиной; все переходы и аудит. | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | Сверить профильный контракт + QA сценарий |
| REQ-047 | 19.11/23.11 возврат free-text | При возврате свободного ответа преподаватель выбирает: исправление лишь указанных свободных ответов **без списания попытки** ИЛИ полное повторное прохождение теста с новой попыткой; обе ветки сохраняют историю. | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | Сверить профильный контракт + QA сценарий |
| REQ-048 | 19.11 попытки и история | Попытки привязаны к назначению; ответы, исправления и решения append-only; X/Y и награда за итоговое Сдан разделены | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | Сверить профильный контракт + QA сценарий |
| REQ-049 | 19.11 review UX | Вопросы/ответы и медиа, бинарная проверка free-text, комментарии, атомарное Взять в работу | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | Сверить профильный контракт + QA сценарий |
| REQ-050 | ранние обсуждения способы ознакомления | Подтверждение ознакомления: кнопка, один вопрос или полный тест; факт связан с редакцией, сотрудником, временем/назначением. | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | Сверить профильный контракт + QA сценарий |
| REQ-051 | 19.11 принять 1–7 | Базовые фильтры и группировки legacy сохраняем, CSV+**реальный** XLSX, фильтры/статистика сервером; корректный процент курса и дедлайны; сохранять состояние интерфейса. | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | Сверить профильный контракт + QA сценарий |
| REQ-052 | 19.11 роли и область прав | Преподаватель работает с любым сотрудником компании в рамках утверждённых действий; сервер проверяет роль | APPROVED-CONCEPT | [ACCESS_AND_ROLES.md](ACCESS_AND_ROLES.md) | Сверить профильный контракт + QA сценарий |
| REQ-053 | 23.11 UI программа курса | Разделы можно создавать и переименовывать | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C02/QA-005 |
| REQ-054 | 23.11 скрин 3 | Материалы перетаскиваются мышью в пределах секции | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C02/QA-006 |
| REQ-055 | 23.11 скрин 3 | Материал переносится из одной секции в другую | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C02/QA-006 |
| REQ-056 | 23.11 статья | Клик по статье открывает полноэкранный Tiptap редактор | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C03/QA-007 |
| REQ-057 | 23.11 тест | Клик по тесту открывает полноэкранный конструктор | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C04/QA-008 |
| REQ-058 | 25.11.2026 новое решение | Google Docs открывается актуальным содержимым внутри статьи RTM. | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C05/QA-009 |
| REQ-059 | 25.11.2026 новое решение | Видео и аудио воспроизводятся внутри статьи RTM. | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C06/QA-009 |
| REQ-060 | 23.11 возврат | Все окна материалов возвращают в курс без потери контекста | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C03-C06/QA-009 |
| REQ-061 | 23.11 статья | Статья имеет название, короткое описание, необязательную обложку | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C03/QA-007 |
| REQ-062 | 25.11.2026 новое решение | Редакции есть у статьи БЗ, внутренняя статья курса без редакций. | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C03/QA-007 |
| REQ-063 | 23.11 Tiptap | Свой Tiptap toolbar: заголовки, форматирование, списки, таблицы, ссылки, изображения, блоки | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C03/QA-015 |
| REQ-064 | 23.11 статья | Autosave, preview и сохранение текущей статьи с историей правок | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C03/QA-010 |
| REQ-065 | 23.11 копия | Поиск статьи в чужом курсе, просмотр и создание новой копии | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C07/QA-013 |
| REQ-066 | 23.11 копия | Копия статьи/теста независима и хранит copied_from provenance | APPROVED | [DATA_MODEL.md](DATA_MODEL.md) | QA-013/QA-014 |
| REQ-067 | 25.11.2026 новое решение | Видео в статье: RUTUBE либо серверный MP4/WebM/MOV. | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C06/QA-004 |
| REQ-068 | 25.11.2026 новое решение | Серверная загрузка видео работает в MVP. | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-056 |
| REQ-069 | 23.11 видеотека | Папка имеет имя и обложку-превью | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-052 |
| REQ-070 | 23.11 видеотека | Вложенные папки и перемещение объектов как в Windows | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-052 |
| REQ-071 | 23.11 видеотека | ACL по отделу и подотделу, отдельному сотруднику | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-052 |
| REQ-072 | 25.11.2026 новое решение | В админке единая БЗ с деревом папок и статьями. | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-002 |
| REQ-073 | 25.11.2026 новое решение | Пользователь видит только разрешённые папки и статьи. | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-052 |
| REQ-074 | 23.11 База знаний | Google Docs новая ссылка добавляется в Базе знаний, не в курсе | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-003 |
| REQ-075 | 25.11.2026 новое решение | База знаний с папками, ACL и статьями работает в MVP. | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-002 |
| REQ-076 | 23.11 курс | Список курсов показывается компактной таблицей | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-001 |
| REQ-077 | 23.11 курс | Описание: название, цель, краткое описание, свободный/последовательный режим | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C01 |
| REQ-078 | 23.11 курс | Программа: секции, порядок, обязательность и живое содержание | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C02 |
| REQ-079 | 23.11 курс | Предпросмотр глазами сотрудника до публикации | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C10 |
| REQ-080 | 23.11 курс | Меню «Все действия» рядом с «Открыть» в строках курса | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-023 |
| REQ-081 | 23.11 курс | Фильтры и положение каталога сохраняются при возврате | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-007 |
| REQ-082 | 23.11 курс | Ошибка сети не должна маскироваться под успешный autosave | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-010 |
| REQ-083 | 23.11 тест | Конструктор имеет single/multi/free и изображения | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-016 |
| REQ-084 | 23.11 тест | Конструктор имеет попытки, таймер, баллы, порог и результат reveal | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-017 |
| REQ-085 | 19.11 review | Автоответы оцениваются сервером, свободные — преподавателем | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | T01/T09 |
| REQ-086 | 19.11 review | Снимок начатой попытки не изменяется после правки теста | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | T01 |
| REQ-087 | 19.11 review | Просмотр всех попыток и ответов без подтверждения не мутирует БД | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | T03 |
| REQ-088 | 19.11 review | Черновик незавершённой проверки сохраняется | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | T11 |
| REQ-089 | 19.11 review | Два одновременных reviewer claim не перетирают друг друга | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | T04 |
| REQ-090 | 19.11 review | При возврате обязателен комментарий | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | T08 |
| REQ-091 | 19.11 review | При возврате у teacher выбор только ответ или полный тест | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | T05/T06 |
| REQ-092 | 19.11 review | Только ответ — новая version в answer_submissions, attempt_no прежний | APPROVED | [DATA_MODEL.md](DATA_MODEL.md) | T05 |
| REQ-093 | 19.11 review | Полный ретейк — новая попытка с сохранением прежней | APPROVED | [DATA_MODEL.md](DATA_MODEL.md) | T06 |
| REQ-094 | 19.11 review | Дополнительные попытки выдаются отдельному назначению, не глобальному тесту | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | T10 |
| REQ-095 | 19.11 review | Основное рекомендованное действие не скрывает меню всех разрешённых | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | T10 |
| REQ-096 | 19.11 review | Освобождение и ручной зачёт сохраняют обязательную причину, audit | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | QA-028 |
| REQ-097 | 19.11 review | Вкладки по материалам/сотрудникам и курсам/сотрудникам | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | RC01 |
| REQ-098 | 19.11 review | Карточка сотрудника — полноценная страница вместо правого drawer | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | RC04 |
| REQ-099 | 19.11 review | Сохраняются фильтры по отделу, статусу, сроку и группировки | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | RC08 |
| REQ-100 | 19.11 review | Многократные активные кампании не сливаются, completed сотрудник остаётся | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | RC06 |
| REQ-101 | 19.11 review | Активные кампании в MVP, завершённые — заглушка future | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | RC06 |
| REQ-102 | 19.11 review | Различать status сотрудника и overdue flag | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | QA-033 |
| REQ-103 | 19.11 review | Курс считает обязательные элементы required only | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | RC05 |
| REQ-104 | 19.11 review | В курсе блокируется последующий шаг при sequential до успеха (required only) | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | C01 |
| REQ-105 | 23.11 кампании | Выбор конкретных людей плюс отделов/вложенных отделов без дублей | APPROVED | [COURSE_ASSIGNMENTS.md](COURSE_ASSIGNMENTS.md) | A01 |
| REQ-106 | 23.11 кампании | Ответственные за проверку выбираются при назначении курса | APPROVED | [COURSE_ASSIGNMENTS.md](COURSE_ASSIGNMENTS.md) | A01 |
| REQ-107 | 23.11 кампании | Срок относительный или абсолютной датой | APPROVED | [COURSE_ASSIGNMENTS.md](COURSE_ASSIGNMENTS.md) | A02 |
| REQ-108 | 23.11 кампании | Уведомление и задача Bitrix настраиваются независимо | APPROVED | [COURSE_ASSIGNMENTS.md](COURSE_ASSIGNMENTS.md) | A03 |
| REQ-109 | 23.11 кампании | Настраиваются название и описание Bitrix задачи с preview | APPROVED | [COURSE_ASSIGNMENTS.md](COURSE_ASSIGNMENTS.md) | A04 |
| REQ-110 | 19.11 worker | Ошибки доставки не откатывают назначения и retry не дублирует | APPROVED | [COURSE_ASSIGNMENTS.md](COURSE_ASSIGNMENTS.md) | A05 |
| REQ-111 | 19.11 кампании | Учёт новых сотрудников в активной кампании идемпотентен | APPROVED | [COURSE_ASSIGNMENTS.md](COURSE_ASSIGNMENTS.md) | A06 |
| REQ-112 | 19.11 Bitrix | Администраторы Bitrix admin автоматически становятся RTM admin | APPROVED | [ACCESS_AND_ROLES.md](ACCESS_AND_ROLES.md) | QA-048 |
| REQ-113 | 19.11 Bitrix | Преподаватель не редактирует учебный контент | APPROVED | [ACCESS_AND_ROLES.md](ACCESS_AND_ROLES.md) | QA-037 |
| REQ-114 | 19.11 Bitrix | Редактор не назначает и не снимает системные роли | APPROVED | [ACCESS_AND_ROLES.md](ACCESS_AND_ROLES.md) | QA-048 |
| REQ-115 | 19.11 Git | Никакого commit/push/tag без отдельного разрешения | APPROVED | [../AGENTS.md](../AGENTS.md) | QA-049 |
| REQ-116 | 19.11 Git | После санкционированного push в main идёт автоматический деплой Next | APPROVED | [../AGENTS.md](../AGENTS.md) | QA-050 |
| REQ-117 | 19.11 Git | Правки кода непосредственно production запрещены | APPROVED | [../AGENTS.md](../AGENTS.md) | QA-049 |
| REQ-118 | 19.11 Git | Теги vX.Y.Z и ключ RTM-YYYYMMDD-NN в выпуске | APPROVED | [../AGENTS.md](../AGENTS.md) | QA-049 |
| REQ-119 | 19.11 Bitrix | Секреты/OAuth только backend, никакого .env в Git | APPROVED | [../AGENTS.md](../AGENTS.md) | QA-049 |
| REQ-120 | 19.11 backups | Dev disposable без бэкапа, реальные результаты — бэкап DB+media | APPROVED | [../AGENTS.md](../AGENTS.md) | QA-051 |
| REQ-121 | раннее согласование | Одна PostgreSQL с 6 logical schemas, не БД на тип материала | APPROVED | [ARCHITECTURE.md](ARCHITECTURE.md) | QA-050 |
| REQ-122 | раннее согласование | Завершённые результаты сохраняются после изменения курса и не пересчитываются | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | QA-046 |
| REQ-123 | 19.11 редакции | Время UTC/дата UI DD.MM.YYYY и отдельный sequence № | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | QA-054 |
| REQ-124 | 19.11 редакции | Опубликованную редакцию удалить могут только admin/developer | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | QA-047 |
| REQ-125 | 19.11 редакции | Первоначальная редакция без кампании не попадает в Центр проверок | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | QA-031 |
| REQ-126 | 19.11 редакции | Подтверждение чтения кнопкой/вопросом/тестом сохраняет человека/время/редакцию | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | QA-046 |
| REQ-127 | 19.11 роли | Иерархия developer > admin > editor > teacher > employee | APPROVED | [ACCESS_AND_ROLES.md](ACCESS_AND_ROLES.md) | QA-048 |
| REQ-128 | 19.11 миграция | Legacy 4 вкладки — историческое, не Next | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | RC01 |
| REQ-129 | 25.11.2026 новое решение | Постоянная синхронизация Google Sheets не нужна; первичный импорт однократный. | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-135 |
| REQ-130 | 25.11.2026 новое решение | Первичный импорт Google Docs из таблицы, затем раскладка статей по папкам. | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-135 |
| REQ-131 | 25.11.2026 новое решение | Исторический снимок Google Docs — извлечённый текст, источник, время и хеш. | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | QA-125 |
| REQ-132 | 19.11 права | Преподаватель действует по любому сотруднику компании | APPROVED | [ACCESS_AND_ROLES.md](ACCESS_AND_ROLES.md) | QA-078 |
| REQ-133 | 23.11 UI | Разделы курса строго одноуровневые; вложенные подразделы запрещены | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-056 |
| REQ-134 | 23.11 публикация | Внутреннюю статью/тест можно назначить отдельно | APPROVED | [COURSE_ASSIGNMENTS.md](COURSE_ASSIGNMENTS.md) | QA-079 |
| REQ-135 | 19.11 legacy | Предшественник — источник сценариев, но не legacy JS runtime реализации | APPROVED | [ARCHITECTURE.md](ARCHITECTURE.md) | QA-038 |
| REQ-136 | 19.11 удобство | Вернуться из редактора к каталогу/курсу с сохранением поисков/скролла | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-007 |
| REQ-137 | 19.11 видео | RUTUBE открытие плеера не объявлять доказанным просмотром без API события | APPROVED-CONCEPT | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-004 |
| REQ-138 | 19.11 server | Next — отдельное окружение от /opt/rtm-app, prod код не менять | APPROVED | [ARCHITECTURE.md](ARCHITECTURE.md) | QA-050 |
| REQ-139 | 23.11 управление редакциями | Управление редакциями остаётся отдельной админ-вкладкой | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | QA-046 |
| REQ-140 | 19.11 подтверждение 1-7 | В каждом ревью доступны сроки, фото, ответственные, история, CSV/XLSX, детали | APPROVED | [REVIEW_CENTER_NEXT.md](REVIEW_CENTER_NEXT.md) | RC03-RC09 |
| REQ-141 | Согласование экрана «Программа курса» от 23.11.2026 | Каталог курсов и полноценный редактор с сохранением контекста | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-056 |
| REQ-142 | Согласование экрана «Программа курса» от 23.11.2026 | Одноуровневые разделы, удаление с двумя подтверждаемыми вариантами | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-057 |
| REQ-143 | Согласование экрана «Программа курса» от 23.11.2026 | Drag & Drop за ручку, пустая/свёрнутая цель, без копии/смены UUID | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-058 |
| REQ-144 | Согласование экрана «Программа курса» от 23.11.2026 | Пять способов добавления и полноценные страницы с возвратом | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-059 |
| REQ-145 | Согласование экрана «Программа курса» от 23.11.2026 | Полноценный редактор статьи Tiptap и безопасное сохранение | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-060 |
| REQ-146 | Согласование экрана «Программа курса» от 23.11.2026 | Конструктор теста, серверная оценка и два режима возврата свободного ответа | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-061 |
| REQ-147 | Согласование экрана «Программа курса» от 23.11.2026 | Видео RUTUBE внутри курса с ошибкой просмотра без ложного подтверждения | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-062 |
| REQ-148 | 25.11.2026 новая модель | Независимое копирование статьи/теста из текущего сохранённого состояния с новым UUID | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-063 |
| REQ-149 | Согласование экрана «Программа курса» от 23.11.2026 | Серверное автосохранение и контроль конфликтов | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-064 |
| REQ-150 | Согласование экрана «Программа курса» от 23.11.2026 | Публикация с блокерами, подтверждаемыми предупреждениями и аудитом | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-065 |
| REQ-151 | Согласование экрана «Программа курса» от 23.11.2026 | Разделение сохранения, публикации и назначения | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-066 |
| REQ-152 | Согласование экрана «Программа курса» от 23.11.2026 | Админка для компьютера, пользовательская часть на мобильных | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-067 |
| REQ-153 | Согласование экрана «Программа курса» от 23.11.2026 | Живой курс без пользовательских редакций меняется и хранит историю | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | QA-068 |
| REQ-154 | 25.11.2026 новое решение | Актуальный Google Docs внутри статьи; исторический снимок при публикации редакции. | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | QA-069 |
| REQ-155 | Согласование экрана «Программа курса» от 23.11.2026 | Преподаватель назначает курс любому сотруднику компании | APPROVED | [ACCESS_AND_ROLES.md](ACCESS_AND_ROLES.md) | QA-070 |
| REQ-156 | Согласование экрана «Программа курса» от 23.11.2026 | Открытые вопросы по живому курсу, тесту и награде перечислены в OPEN_QUESTIONS.md | APPROVED | [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | QA-071 |
| REQ-157 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Курс и внутренние материалы без пользовательских редакций | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | QA-072 |
| REQ-158 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Курс меняется при активной/закрытой кампании | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-073 |
| REQ-159 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Незавершивший видит актуальное; завершивший сохраняет результат | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | QA-074 |
| REQ-160 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Начатая попытка использует снимок; следующая актуальный тест | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | QA-075 |
| REQ-161 | 25.11.2026 новое решение | Статьи БЗ имеют редакции; Google Docs встраивается в статьи. | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-127 |
| REQ-162 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Преподаватель действует по любому сотруднику с аудитом | APPROVED | [ACCESS_AND_ROLES.md](ACCESS_AND_ROLES.md) | QA-077 |
| REQ-163 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Кампания статьи/теста отдельна без взаимозачёта | APPROVED | [COURSE_ASSIGNMENTS.md](COURSE_ASSIGNMENTS.md) | QA-078 |
| REQ-164 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Кампания указывает на живой курс без редакции | APPROVED | [COURSE_ASSIGNMENTS.md](COURSE_ASSIGNMENTS.md) | QA-079 |
| REQ-165 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Состояния кампании и напоминания согласованы | APPROVED | [COURSE_ASSIGNMENTS.md](COURSE_ASSIGNMENTS.md) | QA-080 |
| REQ-166 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Порог теста X/Y без баллов за вопросы | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | QA-081 |
| REQ-167 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Свободные ответы бинарно Принято/Не принято | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | QA-082 |
| REQ-168 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Награда баллами только после всего сданного теста | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | QA-083 |
| REQ-169 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Частичный и полный возврат сохраняют историю попыток | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | QA-084 |
| REQ-170 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Копирование текущего материала включая доступный черновик | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-085 |
| REQ-171 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Копия целого курса без кампаний и результатов | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-086 |
| REQ-172 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Видео подтверждается событиями, кнопкой или проверкой | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-087 |
| REQ-173 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Историческое пользовательское меню заменено REQ-195; шесть админ-разделов сохранены | SUPERSEDED | [UI_NAVIGATION.md](UI_NAVIGATION.md) | QA-088 |
| REQ-174 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Открытые граничные вопросы живого курса | APPROVED | [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | QA-089 |
| REQ-175 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Снимки истории и отделение награды от X/Y | APPROVED | [DATA_MODEL.md](DATA_MODEL.md) | QA-090 |
| REQ-176 | Окончательное согласование пунктов 1–12 и уточнение баллов, 23.11.2026 | Схема без course_revision_id | APPROVED | [DATA_MODEL.md](DATA_MODEL.md) | QA-091 |
| REQ-177 | Ответ пользователя 26.11.2026 | Настраиваемые баллы за тест начисляются один раз на назначение–тест после итогового «Сдан» | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | QA-137 |
| REQ-178 | Ответ пользователя 26.11.2026 и безопасная настройка срока | Несколько исправлений свободного ответа в одной попытке до принятия; отдельный настраиваемый срок возврата (по умолчанию 7 суток), исходный таймер не перезапускается | APPROVED | [TEST_REVIEW_WORKFLOWS.md](TEST_REVIEW_WORKFLOWS.md) | QA-138 |
| REQ-179 | Консолидация спецификации 23.11.2026 | Расход начатой, но не отправленной попытки требует решения | OPEN | [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | OPEN-034 |
| REQ-180 | Консолидация спецификации 23.11.2026 | Граничные формулы прогресса требуют решения | OPEN | [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | OPEN-035 |
| REQ-181 | Консолидация спецификации 23.11.2026 | Исторические агрегаты закрытой кампании требуют решения | OPEN | [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | OPEN-036 |
| REQ-182 | Консолидация спецификации 23.11.2026 | Точный переход теста только со свободными ответами требует решения | OPEN | [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | OPEN-037 |
| REQ-183 | Консолидация спецификации 23.11.2026 | Автоматический зачёт RUTUBE зависит от доступных событий целевого плеера | OPEN | [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | OPEN-039 |
| REQ-184 | Консолидация спецификации 23.11.2026 | Название и точный переход первой активации курса требуют решения | OPEN | [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | OPEN-040 |
| REQ-185 | 25.11.2026 новое решение | Формат исходной таблицы и сопоставление Google file ID для импорта открыты. | OPEN | [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | OPEN-042 |
| REQ-186 | Консолидация спецификации 23.11.2026 | Production-путь, домен, volumes и deploy-service требуют решения | OPEN | [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | OPEN-018 |
| REQ-187 | Консолидация спецификации 23.11.2026 | Google OAuth и права экспорта приватных документов требуют проверки | OPEN | [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | OPEN-019 |
| REQ-188 | 25.11.2026 новое решение | ACL папки наследуется вниз, отдельная статья открывает путь без соседей. | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-125 |
| REQ-189 | 25.11.2026 новое решение | Статья курса не наследует ACL папок БЗ. | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-125 |
| REQ-190 | Консолидация спецификации 23.11.2026 | Массовые исключительные действия преподавателя требуют отдельного согласования | OPEN | [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | OPEN-020 |
| REQ-191 | Консолидация комплекта 23.11.2026 | Новый чат обязан начать с baseline, решений, трассировки, профильных контрактов, OPEN и QA | APPROVED | [CURRENT_MVP_BASELINE.md](CURRENT_MVP_BASELINE.md) | QA-122 |
| REQ-192 | Консолидация комплекта 23.11.2026 | Валидатор выявляет рассинхронизацию OPEN/REQ/QA и известные отменённые правила в активных документах | APPROVED | [../scripts/validate_spec.py](../scripts/validate_spec.py) | QA-123 |
| REQ-193 | Консолидация комплекта 23.11.2026 | Визуальная система готовится отдельным потоком и передаётся разработке как проверяемый пакет | APPROVED | [VISUAL_DESIGN_WORKSTREAM.md](VISUAL_DESIGN_WORKSTREAM.md) | QA-124 |
| REQ-194 | Ответы пользователя 1–13, 25.11.2026 | Полная папочная БЗ, ACL, статьи и медиа реализуются в MVP | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-125 |
| REQ-195 | Ответы пользователя 2, 25.11.2026 | Меню пользователя: Обучение → Курсы/Обновления; База знаний; Профиль | APPROVED | [UI_NAVIGATION.md](UI_NAVIGATION.md) | QA-126 |
| REQ-196 | Ответы пользователя 3–5, 25.11.2026 | Редакция целой статьи БЗ; текущий Google Docs внутри статьи и компактный исторический текстовый снимок | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | QA-127 |
| REQ-197 | Ответ пользователя 6, 25.11.2026 | Статья Tiptap смешивает текст, таблицы, несколько Google Docs, видео и аудио в произвольном порядке | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-128 |
| REQ-198 | Ответ пользователя 7, 25.11.2026 | Полный тест создаётся из мастера редакции, привязан к ней, копируется в следующую редакцию независимо | APPROVED | [CONTENT_REVISIONS.md](CONTENT_REVISIONS.md) | QA-129 |
| REQ-199 | Ответ пользователя 8, 25.11.2026 | Внутренняя статья курса отделена от статьи БЗ, без пользовательских редакций | APPROVED | [DATA_MODEL.md](DATA_MODEL.md) | QA-130 |
| REQ-200 | Ответ пользователя 9, 25.11.2026 | Google Docs в программе курса только внутри статьи, отдельной строки нет | APPROVED | [COURSES_EDITOR_UI.md](COURSES_EDITOR_UI.md) | QA-131 |
| REQ-201 | Ответ пользователя 10, 25.11.2026 | Материалы: video/audio/test/google_document; статьи отдельно с блоками и связями | APPROVED | [DATA_MODEL.md](DATA_MODEL.md) | QA-132 |
| REQ-202 | Ответ пользователя 11, 25.11.2026 | RUTUBE и серверное видео MP4/WebM/MOV; аудио MP3/WAV; плееры внутри статьи | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-133 |
| REQ-203 | Ответы пользователя 12–13, 25.11.2026 | Одна папка на статью, ACL folder/article; наследование папки, путь к статье без соседей | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-134 |
| REQ-204 | Ответ пользователя 1, 25.11.2026 | Google Docs из таблицы импортируются однократно, затем раскладываются в БЗ | APPROVED | [KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md](KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md) | QA-135 |
| REQ-205 | Уточнение пользователя 25.11.2026 о стартовом виде и разработчике | После входа пользовательская часть; кнопка админки только teacher+; проверенный Bitrix24 ID 36 — защищённый developer, остальные повышенные роли через админку, Bitrix24-admin автоматически admin | APPROVED | [ACCESS_AND_ROLES.md](ACCESS_AND_ROLES.md) | QA-136 |

## Контроль спорных/отменённых решений


- `OLD-001` и `OLD-002`: нет общей mutable библиотеки тестов; статьи БЗ и внутренние статьи курса различаются, копии независимы.
- `OLD-003`: нет отдельной админ-Видеотеки; видео встроено в статью Базы знаний или курса.
- `OLD-004`: новый Google Docs регистрируется в БЗ и встраивается в статью; отдельного элемента программы курса нет.
- `OLD-005`: старый review центр 4 вкладки; Next строго 3, первая заглушка.
- `OLD-006`: на production source редактировать нельзя.

## Как вносить следующее изменение

1. Указать дату/сообщение пользователя и дословный смысл решения.
2. Обновить ADR в `DECISIONS.md` (`SUPERSEDED` для отменённого, новый `APPROVED` для замены).
3. Обновить **существующий** профильный `.md`, модель БД и MVP-границы, если они затронуты.
4. Дописать следующий последовательный REQ, указав профильный документ и критерий приёмки либо точный OPEN-ID.
5. Закрыть/открыть соответствующий `OPEN`; обновить `CHANGELOG.md`.
6. Выполнить `scripts/validate_spec.py` и сообщить результат, что осталось OPEN.

**Ограничение:** машинная проверка целостности и 140 трассировок — не автоматическое доказательство отсутствия *любых* смысловых пропусков. Человек обязан сверить этот список с исходными сообщениями перед внедрением.



