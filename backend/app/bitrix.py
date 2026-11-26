import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PORTAL = "rtm-group.bitrix24.ru"


class BitrixExpiredToken(Exception):
    pass


def directory_page(method: str, token: str, start: int) -> dict:
    if method not in {"user.get", "department.get"}:
        raise ValueError("Unsupported Bitrix directory method")
    request = Request(
        f"https://{PORTAL}/rest/{method}.json",
        data=urlencode({"auth": token, "start": start}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.load(response)
    except HTTPError as exc:
        try:
            payload = json.load(exc)
        except (ValueError, OSError):
            raise exc
        if isinstance(payload, dict) and payload.get("error") == "expired_token":
            raise BitrixExpiredToken from exc
        raise exc
    if not isinstance(payload, dict):
        raise ValueError("Bitrix directory response is invalid")
    if payload.get("error") == "expired_token":
        raise BitrixExpiredToken
    return payload


def call(method: str, token: str) -> dict:
    if method not in {"app.info", "profile", "user.current"}:
        raise ValueError("Unsupported Bitrix method")
    request = Request(
        f"https://{PORTAL}/rest/{method}.json",
        data=urlencode({"auth": token}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urlopen(request, timeout=8) as response:
        payload = json.load(response)
    if not isinstance(payload.get("result"), dict):
        raise ValueError("Bitrix response has no result")
    return payload["result"]


def token_scopes(token: str) -> list[str]:
    """Read the permissions granted to this exact Bitrix application token."""
    request = Request(
        f"https://{PORTAL}/rest/scope.json",
        data=urlencode({"auth": token}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urlopen(request, timeout=8) as response:
        payload = json.load(response)
    result = payload.get("result")
    if not isinstance(result, list) or not all(isinstance(scope, str) for scope in result):
        raise ValueError("Bitrix scope response is unavailable")
    return result


def list_users(token: str) -> list[dict]:
    """Read the employee directory with Bitrix24's documented 50-row pagination."""
    users: list[dict] = []
    start = 0
    while True:
        payload = directory_page("user.get", token, start)
        page = payload.get("result")
        if not isinstance(page, list):
            raise ValueError("Bitrix employee directory is unavailable")
        users.extend(row for row in page if isinstance(row, dict))
        next_start = payload.get("next")
        if next_start is None:
            return users
        if not isinstance(next_start, int) or next_start <= start or next_start > 100000:
            raise ValueError("Invalid Bitrix pagination")
        start = next_start


def list_departments(token: str) -> list[dict]:
    departments: list[dict] = []
    start = 0
    while True:
        payload = directory_page("department.get", token, start)
        page = payload.get("result")
        if not isinstance(page, list):
            raise ValueError("Bitrix department structure is unavailable")
        departments.extend(row for row in page if isinstance(row, dict))
        next_start = payload.get("next")
        if next_start is None:
            return departments
        if not isinstance(next_start, int) or next_start <= start or next_start > 100000:
            raise ValueError("Invalid Bitrix department pagination")
        start = next_start
