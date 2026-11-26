# Предшественник — что проверено в исходном коде (справочник, НЕ контракт Next)

Проверенный исходный репозиторий: `andreyabramovworks-commits/RTM-education-Bitrix`. Использовались `frontend/src/AdminApp.jsx`, `frontend/public/legacy/acknowledgements.js`, `frontend/public/legacy/learning.js`, `backend/app/v51.py`, `backend/app/models.py`, `AGENTS.md`, README/deploy документы. Код **не меняли**. Данные получены из репозитория ранее в этой беседе; автоматическую актуальность с сегодняшним состоянием main не гарантируем.

## Подтверждённые legacy-механизмы

- `acknowledgements.js`: исторически четыре вкладки «Требует действий», «Проверка тестов», «Проверка редакций», «История действий»; user их **отменил** для Next в пользу трёх вкладок и одной общей проверки тестов.
- Старые фильтры `Все/Мои проверки/Просрочено/Не приступали >3 дней`; поиск по сотруднику/документу; группировки по сотруднику/документу/редакции/статусу/подразделению. «Проверка редакций» — «По документам» и «По сотрудникам», подсчёт сотрудников/назначений/подтверждений/просроченных, экспорт, карточка в боковой панели. User хочет сохранить удачную механику фильтров/агрегатов, но заменить drawer на полноценный экран.
- Legacy review free-text: принять/вернуть с комментарием, «Взять в работу», проверка по вопросу, history попыток. Новый механизм должен быть один, atomic и append-only.
- `backend/app/v51.py`: редакции `GET/POST /documents/{document_id}/editions`, delete, кампании launch/edit/close, assignments answer/start/review/manual-complete/exempt/remind, `/center`, Google OAuth/revisions/render. Legacy автоматически добавляет новичков, считает overdue, формирует Bitrix tasks/notifications и хранит события.
- Legacy модели: `knowledge_editions`, `acknowledgement_campaigns`, `acknowledgement_assignments`, `acknowledgement_events`, `app_users`, `bitrix_departments`, `knowledge_document_renders`; тестовые попытки и другие entity/JSON структуры.
- В старом интерфейсе админ-раздел «Материалы и курсы» с наследуемыми скриптами. В Next **не переносить** legacy JS, не создавать самостоятельный «Материалы» и не использовать прежнюю ссылочную reuse-модель статей/тестов.

## Как использовать

Функциональная миграция — переносить **проверенные сценарии**, не старую реализацию и не старые маршруты один-в-один. Старый `/api/v51/center?scope=all` не гарантирует персонально ограниченный scope; серверная авторизация Next обязательна. Кнопка старого «XLSX» фактически могла создавать TSV/`xls`: в Next только настоящий XLSX. Разные источники legacy state могли порождать дубли/гонки; в Next один backend query/immutable key.

**Не переводить старый текст «четыре вкладки» в новое решение.** Единственные нормативные вкладки — `REVIEW_CENTER_NEXT.md`. Для сравнения старого и нового используйте `DECISIONS.md`, особенно SUPERSEDED.
