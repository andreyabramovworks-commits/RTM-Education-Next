# RTM-Education-Next — живая спецификация

**Состояние:** модель MVP обновлена 25.11.2026: статьи Базы знаний, папки, ACL, редакции и медиа входят в MVP. Открытые технические решения перечислены в `docs/OPEN_QUESTIONS.md`.

## Начать работу

1. Прочитать `AGENTS.md`.
2. Прочитать [текущую модель MVP](docs/CURRENT_MVP_BASELINE.md). Это краткая нормативная точка входа.
3. Проверить решение в [DECISIONS.md](docs/DECISIONS.md) и требование в [REQUIREMENTS_TRACEABILITY.md](docs/REQUIREMENTS_TRACEABILITY.md).
4. Читать профильный контракт нужной области.
5. Перед реализацией затронутой функции проверить [OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) и её сценарии в [QUALITY_AND_TEST_MATRIX.md](docs/QUALITY_AND_TEST_MATRIX.md).

## Карта документов

| Задача | Документы |
|---|---|
| Архитектура, стек, безопасность | `ARCHITECTURE.md`, `DATA_MODEL.md`, `ERD.md`, `ACCESS_AND_ROLES.md` |
| Курсы, статьи, тесты, DnD | `COURSES_EDITOR_UI.md`, `CONTENT_REVISIONS.md` |
| Статьи Базы знаний, папки, ACL, Google Docs, видео, аудио | `KNOWLEDGE_BASE_AND_VIDEO_LIBRARY.md`, `CONTENT_REVISIONS.md` |
| Кампании, сроки, Bitrix24 | `COURSE_ASSIGNMENTS.md` |
| Проверки и попытки | `REVIEW_CENTER_NEXT.md`, `TEST_REVIEW_WORKFLOWS.md` |
| Навигация и границы MVP | `UI_NAVIGATION.md`, `MVP_CONTRACT.md` |
| Приёмка | `QUALITY_AND_TEST_MATRIX.md`, `REQUIREMENTS_TRACEABILITY.md` |
| Визуальное проектирование в отдельном чате | `VISUAL_DESIGN_WORKSTREAM.md` |

## Правило приоритета

`APPROVED` и `APPROVED-CONCEPT` нормативны. `SUPERSEDED` хранит историю и не реализуется. `OPEN` не разрешается молча. При обнаружении расхождения с `CURRENT_MVP_BASELINE.md` сначала исправляется комплект документации, затем продолжается реализация.

## Проверка

После каждого изменения документации запускать `python scripts/validate_spec.py`.

Проверка контролирует файлы, последовательность и ссылки REQ, связь OPEN-вопросов, QA, нормативные решения и запрещённые устаревшие формулировки в активных контрактах.

`references/AGENTS.original.md` — неизменяемый оригинал, загруженный пользователем. Рабочие документы изменяются по месту без создания наборов `final`, `new` и `v2`.
