# Концептуальная модель данных MVP

**Статус:** утверждённые сущности и связи на 25.11.2026; точные SQL-типы, индексы и миграции уточняются при реализации. PostgreSQL 17, схемы identity/content/learning/review/integration/audit; все структурные изменения через Alembic.

## Контент

| Сущность | Основные поля и связи | Инвариант |
|---|---|---|
| `courses` | UUID, название, описание, статус, автор, аудит | Живое содержание, без пользовательских редакций |
| `course_sections`, `course_items` | course FK, section FK, position, article/test FK | Одноуровневые секции, перенос без изменения ID |
| `articles` | UUID, `owner_course_id` nullable, название, текущее Tiptap JSON, аудит, `copied_from_article_id` | Статья курса принадлежит курсу; статья БЗ имеет размещение в одной папке; статьи не входят в `materials` |
| `article_blocks` | article/revision FK, position, тип, текст/таблица или material FK | Несколько разнотипных блоков в произвольном порядке; тест не бывает блоком тела |
| `materials` | UUID, тип `video`/`audio`/`test`/`google_document`, owner, provenance, аудит | Типизированный материал, без статьи |
| `video_assets` | material FK, `rutube_url` или server asset FK, формат, длительность, обработка | RUTUBE или загруженный MP4/WebM/MOV |
| `audio_assets` | material FK, server asset FK, MIME, формат, длительность | MP3/WAV на сервере |
| `google_documents` | material FK, Google file ID, ссылка, права, sync metadata | Один внешний источник; актуальное содержимое при обычном открытии |
| `test_definitions`, `test_questions`, `test_options` | material FK, настройки X/Y, reward_points, correction_days, вопросы и варианты | Общая тестовая модель для курса и редакции статьи |
| `media_assets` | UUID, storage key, MIME, byte size, checksum, статус | Байты вне PostgreSQL; доступ через backend |

Google Docs в курсе выбирается из зарегистрированных материалов Базы знаний и вставляется блоком внутренней статьи. Отдельного `course_item → google_document` нет. Копирование внутренней статьи/теста в другой курс создаёт независимый UUID и не копирует результаты.

## База знаний и редакции

| Сущность | Основные поля и связи | Инвариант |
|---|---|---|
| `knowledge_folders` | UUID, parent FK nullable, название, описание nullable, обложка asset FK nullable | Дерево произвольной глубины без циклов |
| `knowledge_folder_articles` | folder FK, article FK UNIQUE | Ровно одна папка у опубликованной статьи БЗ |
| `knowledge_access_grants` | target type folder/article, target ID, subject type department/subdepartment/employee, subject ID, аудит | Только разрешения; папка наследуется вниз, прямой доступ статьи открывает лишь путь |
| `article_revisions` | UUID, article FK, номер, дата, описание, Tiptap snapshot, опубликовано | Редакция целой статьи БЗ, независима от кампании |
| `google_text_snapshots` | revision FK, material FK, извлечённый текст, Google revision ID nullable, captured_at, SHA256 | Компактный исторический снимок для чтения и поиска |
| `revision_tests` | article_revision FK, test material FK UNIQUE | Полный тест только после статьи; копия в следующую редакцию — новый UUID |

Импорт Google Docs из исходной таблицы однократный и идемпотентный по Google file ID. После импорта статьи и папки организуются в RTM. Исторический снимок Google Docs не подменяет актуальное содержимое при обычном открытии статьи.

## Назначения и прохождение

`assignment_campaigns` хранит тип цели `course`/`course_article`/`course_test`/`article_revision`, ID цели, настройки сроков, Bitrix-уведомления/задачи и ответственных. `assignments` содержит сотрудника, статус, сроки, просрочку отдельно. Редакция статьи фиксируется по UUID; курс остаётся живым. `acknowledgements` фиксирует точную редакцию, сотрудника, время сервера и режим подтверждения. `test_attempts`, `attempt_questions`, `answer_submissions`, `answer_reviews`, `attempt_allowances` сохраняют снимок попытки, версии свободных ответов и аудит. У попытки есть `correction_deadline_at` для отдельного окна исправления; таймер полной попытки остаётся историческим. `test_completion_rewards` содержит assignment/test/attempt FK, points и awarded_at, уникальная пара assignment–test начисляет награду только после окончательного `passed`; X/Y не является системой баллов. `outbox_jobs` доставляет Bitrix-уведомления и задачи идемпотентно.

ACL проверяется в SQL/backend при перечислении, поиске, прямом открытии и получении медиа. Получивший доступ только к статье видит цепочку папок без соседних статей. Структурные назначения отделам применяются к текущему составу сотрудников; история назначений не переписывается.

<!-- Requirements traceability: REQ-025, REQ-066, REQ-092, REQ-093, REQ-153, REQ-154, REQ-163, REQ-164, REQ-165, REQ-175, REQ-176 -->
<!-- Requirements traceability: REQ-199, REQ-201 -->
