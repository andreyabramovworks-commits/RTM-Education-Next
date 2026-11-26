from sqlalchemy import delete, func, select

from app.catalog_import import SOURCE_SHEET, SOURCE_TAB, apply_catalog, plan_catalog
from app.db import SessionLocal
from app.models import Article, Employee, FolderArticle, KnowledgeFolder, KnowledgeGrant


def test_catalog_plan_preserves_folder_levels_and_is_stable():
    source = {"source_spreadsheet_id": SOURCE_SHEET, "sheet_id": SOURCE_TAB, "rows": [
        {"row": 2, "title": "Компания", "bold": True, "color": "217,217,217"},
        {"row": 3, "title": "Правила", "bold": True, "color": "201,218,248"},
        {"row": 4, "title": "Инструкция", "bold": True},
        {"row": 5, "title": "Документ", "description": "Описание", "google_url":
            "https://docs.google.com/document/d/abc_123/edit?tab=t.0", "comment": "Не показывать ученикам"},
        {"row": 6, "title": "Таблица", "primary_url":
            "https://docs.google.com/spreadsheets/d/sheet123/edit"},
        {"row": 7, "title": "НЕАКТУАЛЬНЫЕ", "bold": True, "color": "244,204,204"},
        {"row": 8, "title": "Старый документ", "google_url":
            "https://docs.google.com/document/d/old123/edit"},
        {"row": 9, "title": "Новый раздел", "bold": True, "color": "201,218,248"},
        {"row": 10, "title": "Повтор ссылки", "google_url":
            "https://docs.google.com/document/d/abc_123/edit"},
    ]}
    plan = plan_catalog(source)
    assert len(plan.folders) == 4
    assert [entry.parent_id for entry in plan.folders] == [None, plan.folders[0].id,
        plan.folders[1].id, plan.folders[0].id]
    assert len(plan.articles) == 3
    assert [entry.folder_id for entry in plan.articles] == [plan.folders[2].id,
        plan.folders[2].id, plan.folders[3].id]
    assert plan.articles[0].description == "Описание"
    assert plan.articles[0].google_file_id == plan.articles[2].google_file_id
    assert plan.articles[0].id != plan.articles[2].id
    assert plan.articles[0].id == plan_catalog(source).articles[0].id
    assert [item["reason"] for item in plan.skipped] == ["obsolete_section", "obsolete_section"]


def test_catalog_apply_is_idempotent_and_grants_no_access():
    assert SessionLocal is not None
    source = {"source_spreadsheet_id": SOURCE_SHEET, "sheet_id": SOURCE_TAB, "rows": [
        {"row": 999001, "title": "Тестовая папка", "bold": True, "color": "217,217,217"},
        {"row": 999002, "title": "Тестовый документ", "description": "Описание",
         "google_url": "https://docs.google.com/document/d/testDocId/edit"},
    ]}
    plan = plan_catalog(source)
    with SessionLocal() as db:
        actor = Employee(bitrix_id=36, first_name="Test", last_name="Developer")
        db.add(actor)
        db.commit()
        actor_id = actor.id
    try:
        with SessionLocal() as db:
            actor = db.get(Employee, actor_id)
            assert apply_catalog(db, plan, actor) == {"folders_created": 1, "articles_created": 1, "skipped": 0}
            article = db.get(Article, plan.articles[0].id)
            assert article.body["content"][0]["attrs"]["fileId"] == "testDocId"
            assert db.scalar(select(func.count()).select_from(KnowledgeGrant).where(
                KnowledgeGrant.target_id.in_([plan.articles[0].id, plan.folders[0].id]))) == 0
            article.title = "Edited in RTM"
            db.commit()
            assert apply_catalog(db, plan, actor) == {"folders_created": 0, "articles_created": 0, "skipped": 0}
            assert db.get(Article, article.id).title == "Edited in RTM"
    finally:
        with SessionLocal() as db:
            db.execute(delete(FolderArticle).where(FolderArticle.article_id == plan.articles[0].id))
            db.execute(delete(Article).where(Article.id == plan.articles[0].id))
            db.execute(delete(KnowledgeFolder).where(KnowledgeFolder.id == plan.folders[0].id))
            db.execute(delete(Employee).where(Employee.id == actor_id))
            db.commit()
