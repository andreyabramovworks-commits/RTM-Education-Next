from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from app.db import SessionLocal
from app.auth import router as auth_router
from app.courses import router as courses_router
from app.employees import router as employees_router
from app.knowledge import router as knowledge_router
from app.course_program import router as course_program_router
from app.campaigns import router as campaigns_router
from app.learning import router as learning_router
from app.tests_authoring import router as tests_authoring_router
from app.tests_learning import router as tests_learning_router
from app.reviews import router as reviews_router
from app.media import router as media_router
from app.settings import router as settings_router
from app.google_reader import router as google_reader_router
from app.profile import router as profile_router
from app.review_center import router as review_center_router

app = FastAPI(title="RTM Education Next")
app.include_router(auth_router)
app.include_router(courses_router)
app.include_router(employees_router)
app.include_router(knowledge_router)
app.include_router(course_program_router)
app.include_router(campaigns_router)
app.include_router(learning_router)
app.include_router(tests_authoring_router)
app.include_router(tests_learning_router)
app.include_router(reviews_router)
app.include_router(media_router)
app.include_router(settings_router)
app.include_router(google_reader_router)
app.include_router(profile_router)
app.include_router(review_center_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    if SessionLocal is None:
        raise HTTPException(503, "Database is unavailable")
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(503, "Database is unavailable") from exc
    return {"status": "ready"}
