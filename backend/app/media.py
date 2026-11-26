import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_employee
from app.db import get_db
from app.knowledge import visible_article_ids
from app.models import (Article, ArticleRevision, Assignment, AssignmentCampaign, Employee,
                        FolderArticle, KnowledgeFolder, MediaAsset, AttemptQuestion, TestAttempt)
from app.permissions import ROLE_RANK, require_role

router = APIRouter(tags=["media"])
MEDIA_ROOT = Path("/media")
MAX_VIDEO_BYTES = 500 * 1024 * 1024
MAX_AUDIO_BYTES = 100 * 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
TYPES = {".mp4": ("video", "video/mp4"), ".webm": ("video", "video/webm"),
         ".mov": ("video", "video/quicktime"), ".mp3": ("audio", "audio/mpeg"),
         ".wav": ("audio", "audio/wav"), ".png": ("image", "image/png"),
         ".jpg": ("image", "image/jpeg"), ".jpeg": ("image", "image/jpeg"),
         ".webp": ("image", "image/webp")}


class RutubeVideo(BaseModel):
    url: str
    title: str = "Видео RUTUBE"


def valid_signature(extension: str, header: bytes) -> bool:
    if extension == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in (".jpg", ".jpeg"):
        return header.startswith(b"\xff\xd8\xff")
    if extension == ".webp":
        return header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    if extension in (".mp4", ".mov"):
        return len(header) >= 12 and header[4:8] == b"ftyp" and (extension != ".mov" or b"qt  " in header[:32])
    if extension == ".webm":
        return header.startswith(b"\x1a\x45\xdf\xa3")
    if extension == ".wav":
        return header.startswith(b"RIFF") and header[8:12] == b"WAVE"
    if extension == ".mp3":
        return header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xff and header[1] & 0xe0 == 0xe0)
    return False


def media_in_body(value: object, asset_id: str) -> bool:
    if isinstance(value, dict):
        attrs = value.get("attrs")
        return (value.get("type") == "mediaEmbed" and isinstance(attrs, dict) and attrs.get("assetId") == asset_id) or any(
            media_in_body(item, asset_id) for item in value.values())
    if isinstance(value, list):
        return any(media_in_body(item, asset_id) for item in value)
    return False


def can_read_asset(db: Session, employee: Employee, asset: MediaAsset) -> bool:
    if ROLE_RANK.get(employee.effective_role, 0) >= ROLE_RANK["editor"]:
        return True
    if asset.kind == "image":
        attempt_ids = db.scalars(select(TestAttempt.id).join(Assignment,
            TestAttempt.assignment_id == Assignment.id).where(Assignment.employee_id == employee.id)).all()
        if attempt_ids:
            questions = db.scalars(select(AttemptQuestion).where(AttemptQuestion.attempt_id.in_(attempt_ids))).all()
            if any(question.image_asset_id == asset.id or any(
                option.get("image_asset_id") == str(asset.id) for option in question.options_snapshot)
                   for question in questions):
                return True
        return False
    folders = db.scalars(select(KnowledgeFolder)).all()
    placements = db.scalars(select(FolderArticle)).all()
    visible = visible_article_ids(db, employee, folders, placements)
    active_course_ids = set(db.scalars(select(AssignmentCampaign.target_id).join(Assignment,
        Assignment.campaign_id == AssignmentCampaign.id).where(Assignment.employee_id == employee.id,
        AssignmentCampaign.status == "active", AssignmentCampaign.target_type == "course",
        Assignment.status.notin_(["cancelled", "exempted"]))).all())
    assigned_article_ids = set(db.scalars(select(AssignmentCampaign.target_id).join(Assignment,
        Assignment.campaign_id == AssignmentCampaign.id).where(Assignment.employee_id == employee.id,
        AssignmentCampaign.status == "active", AssignmentCampaign.target_type == "course_article",
        Assignment.status.notin_(["cancelled", "exempted"]))).all())
    articles = db.scalars(select(Article)).all()
    for article in articles:
        if article.id in visible or article.id in assigned_article_ids or article.owner_course_id in active_course_ids:
            if media_in_body(article.body, str(asset.id)):
                return True
    assigned_revision_ids = set(db.scalars(select(AssignmentCampaign.target_id).join(Assignment,
        Assignment.campaign_id == AssignmentCampaign.id).where(Assignment.employee_id == employee.id,
        AssignmentCampaign.status == "active", AssignmentCampaign.target_type == "article_revision",
        Assignment.status.notin_(["cancelled", "exempted"]))).all())
    if assigned_revision_ids:
        revisions = db.scalars(select(ArticleRevision).where(ArticleRevision.id.in_(assigned_revision_ids))).all()
        if any(media_in_body(revision.body_snapshot, str(asset.id)) for revision in revisions):
            return True
    return False


@router.post("/admin/media/upload", status_code=201)
async def upload_media(kind: str = Form(), file: UploadFile = File(), db: Session = Depends(get_db),
                       actor: Employee = Depends(require_role("editor"))):
    original = Path(file.filename or "").name[:240]
    extension = Path(original).suffix.lower()
    if extension not in TYPES or TYPES[extension][0] != kind:
        raise HTTPException(422, "Unsupported media format")
    first = await file.read(32)
    if not valid_signature(extension, first):
        raise HTTPException(422, "File content does not match its format")
    limit = MAX_VIDEO_BYTES if kind == "video" else MAX_AUDIO_BYTES if kind == "audio" else MAX_IMAGE_BYTES
    asset_id = uuid.uuid4()
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    path = MEDIA_ROOT / str(asset_id)
    total = 0
    try:
        with path.open("xb") as output:
            chunk = first
            while chunk:
                total += len(chunk)
                if total > limit:
                    raise HTTPException(413, "Media file is too large")
                output.write(chunk)
                chunk = await file.read(1024 * 1024)
        asset = MediaAsset(id=asset_id, kind=kind, source_type="upload", original_filename=original,
            mime_type=TYPES[extension][1], byte_length=total, storage_path=str(path),
            created_by=actor.id, created_at=datetime.now(timezone.utc))
        db.add(asset)
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {"id": str(asset.id), "kind": asset.kind, "title": asset.original_filename,
            "source_type": asset.source_type}


@router.post("/admin/media/rutube", status_code=201)
def register_rutube(payload: RutubeVideo, db: Session = Depends(get_db),
                    actor: Employee = Depends(require_role("editor"))):
    parsed = urlparse(payload.url)
    if parsed.scheme != "https" or parsed.hostname not in ("rutube.ru", "www.rutube.ru") or parsed.query or parsed.fragment:
        raise HTTPException(422, "Use a RUTUBE video URL")
    match = re.fullmatch(r"/(?:video|play/embed)/([A-Za-z0-9]+)/?", parsed.path)
    if not match:
        raise HTTPException(422, "Unsupported RUTUBE video URL")
    asset = MediaAsset(kind="video", source_type="rutube", original_filename=payload.title[:240].strip() or "Видео RUTUBE",
        rutube_url=f"https://rutube.ru/play/embed/{match.group(1)}/", created_by=actor.id)
    db.add(asset)
    db.commit()
    return {"id": str(asset.id), "kind": asset.kind, "title": asset.original_filename,
            "source_type": asset.source_type}


@router.get("/media/{asset_id}/info")
def media_info(asset_id: uuid.UUID, db: Session = Depends(get_db), employee: Employee = Depends(current_employee)):
    asset = db.get(MediaAsset, asset_id)
    if asset is None or not can_read_asset(db, employee, asset):
        raise HTTPException(404)
    return {"id": str(asset.id), "kind": asset.kind, "source_type": asset.source_type,
            "title": asset.original_filename, "mime_type": asset.mime_type,
            "embed_url": asset.rutube_url if asset.source_type == "rutube" else None,
            "file_url": f"/education-next/api/media/{asset.id}" if asset.source_type == "upload" else None}


@router.get("/media/{asset_id}")
def stream_media(asset_id: uuid.UUID, db: Session = Depends(get_db), employee: Employee = Depends(current_employee)):
    asset = db.get(MediaAsset, asset_id)
    if asset is None or asset.source_type != "upload" or not can_read_asset(db, employee, asset):
        raise HTTPException(404)
    path = MEDIA_ROOT / str(asset.id)
    if not path.is_file():
        raise HTTPException(503, "Media file is unavailable")
    return FileResponse(path, media_type=asset.mime_type, headers={"Cache-Control": "private, no-store"})
