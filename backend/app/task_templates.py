"""Render the task text shown to a teacher and sent to Bitrix24."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

APP_URL = "https://rtmgroupdocs.fvds.ru/education-next/app"
TOKENS = {"course", "name", "due_date", "link"}
TOKEN_PATTERN = re.compile(r"\{([^{}]+)\}")


def validate_template(value: str) -> None:
    unknown = set(TOKEN_PATTERN.findall(value)) - TOKENS
    if unknown:
        raise HTTPException(422, f"Unknown task placeholders: {', '.join(sorted(unknown))}")


def render_task(value: str, course: str, name: str, due_at: datetime | None) -> str:
    validate_template(value)
    fields = {"course": course, "name": name,
              "due_date": due_at.astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M МСК") if due_at else "—",
              "link": APP_URL}
    return TOKEN_PATTERN.sub(lambda match: fields[match.group(1)], value)
