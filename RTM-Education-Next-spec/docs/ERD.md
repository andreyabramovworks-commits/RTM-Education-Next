# Концептуальная ER-диаграмма MVP

> Показывает главные связи; точные колонки и ограничения описаны в `DATA_MODEL.md`. Статья — отдельная сущность, не тип `materials`.

```mermaid
erDiagram
    COURSES ||--o{ COURSE_SECTIONS : contains
    COURSE_SECTIONS ||--o{ COURSE_ITEMS : contains
    COURSES ||--o{ ARTICLES : owns_internal
    ARTICLES ||--o{ ARTICLE_BLOCKS : contains
    MATERIALS ||--o{ ARTICLE_BLOCKS : embedded_by
    MATERIALS ||--o| VIDEO_ASSETS : video
    MATERIALS ||--o| AUDIO_ASSETS : audio
    MATERIALS ||--o| GOOGLE_DOCUMENTS : google
    MATERIALS ||--o| TEST_DEFINITIONS : test
    KNOWLEDGE_FOLDERS ||--o{ KNOWLEDGE_FOLDERS : child
    KNOWLEDGE_FOLDERS ||--o{ KNOWLEDGE_FOLDER_ARTICLES : contains
    ARTICLES ||--o| KNOWLEDGE_FOLDER_ARTICLES : placed_once
    KNOWLEDGE_FOLDERS ||--o{ KNOWLEDGE_ACCESS_GRANTS : allowed_folder
    ARTICLES ||--o{ KNOWLEDGE_ACCESS_GRANTS : allowed_article
    ARTICLES ||--o{ ARTICLE_REVISIONS : publishes
    ARTICLE_REVISIONS ||--o{ GOOGLE_TEXT_SNAPSHOTS : archives
    ARTICLE_REVISIONS ||--o| REVISION_TESTS : assesses
    MATERIALS ||--o{ REVISION_TESTS : test_material
    ARTICLE_REVISIONS ||--o{ ASSIGNMENT_CAMPAIGNS : updates
    COURSES ||--o{ ASSIGNMENT_CAMPAIGNS : learning
    ASSIGNMENT_CAMPAIGNS ||--o{ ASSIGNMENTS : generates
    ASSIGNMENTS ||--o{ TEST_ATTEMPTS : produces
    TEST_ATTEMPTS ||--o{ ATTEMPT_QUESTIONS : snapshots
    TEST_ATTEMPTS ||--o| TEST_COMPLETION_REWARDS : awards_on_pass
```

Редакции есть только у статей Базы знаний. Курс и внутренняя статья живые; начатая попытка теста хранит технический снимок. Историческое содержимое Google Docs сохраняется компактным текстом.

<!-- Requirements traceability: REQ-163, REQ-164, REQ-165 -->
