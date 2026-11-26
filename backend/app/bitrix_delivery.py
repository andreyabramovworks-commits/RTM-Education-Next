"""Server-only Bitrix24 delivery and OAuth token refresh."""
import fcntl
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.bitrix import PORTAL

AUTH_FILE = Path(os.environ.get("BITRIX_AUTH_FILE", "/data/bitrix-auth.json"))
CLIENT_ID = os.environ.get("BITRIX_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("BITRIX_CLIENT_SECRET", "")


class DeliveryError(Exception):
    def __init__(self, code: str, retryable: bool = False, uncertain: bool = False):
        super().__init__(code)
        self.retryable = retryable
        self.uncertain = uncertain


def configured() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET and AUTH_FILE.is_file())


def saved_auth() -> dict:
    try:
        value = json.loads(AUTH_FILE.read_text())
    except (OSError, ValueError) as exc:
        raise DeliveryError("BITRIX_INSTALL_UNAVAILABLE") from exc
    if not value.get("access_token") or not value.get("refresh_token"):
        raise DeliveryError("BITRIX_TOKENS_UNAVAILABLE")
    return value


def refresh_auth(stale_access_token: str) -> dict:
    lock_path = AUTH_FILE.with_suffix(".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        auth = saved_auth()
        if auth["access_token"] != stale_access_token:
            return auth
        params = urlencode({"grant_type": "refresh_token", "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET, "refresh_token": auth["refresh_token"]})
        try:
            with urlopen(f"https://oauth.bitrix24.tech/oauth/token/?{params}", timeout=12) as response:
                renewed = json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise DeliveryError("TOKEN_REFRESH_UNAVAILABLE", retryable=True) from exc
        if not renewed.get("access_token") or not renewed.get("refresh_token"):
            raise DeliveryError("TOKEN_REFRESH_REJECTED")
        auth.update({"access_token": renewed["access_token"], "refresh_token": renewed["refresh_token"]})
        if isinstance(renewed.get("scope"), str):
            auth["scope"] = renewed["scope"]
        temporary = AUTH_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(auth))
        os.chmod(temporary, 0o600)
        temporary.replace(AUTH_FILE)
        return auth


def rest_call(method: str, fields: dict, retry_safe: bool) -> object:
    auth = saved_auth()
    for attempt in range(2):
        request = Request(f"https://{PORTAL}/rest/{method}.json",
            data=json.dumps({**fields, "auth": auth["access_token"]}).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=12) as response:
                payload = json.load(response)
        except HTTPError as exc:
            try:
                error = json.load(exc)
            except (ValueError, OSError):
                error = {}
            code = str(error.get("error") or f"HTTP_{exc.code}")[:100]
            if exc.code == 401 and code == "expired_token" and attempt == 0:
                auth = refresh_auth(auth["access_token"])
                continue
            if exc.code == 429 or code == "QUERY_LIMIT_EXCEEDED":
                raise DeliveryError(code, retryable=True) from exc
            if exc.code >= 500:
                raise DeliveryError(code, retryable=retry_safe, uncertain=not retry_safe) from exc
            raise DeliveryError(code) from exc
        except (URLError, TimeoutError) as exc:
            raise DeliveryError("NETWORK_RESULT_UNKNOWN", retryable=retry_safe, uncertain=not retry_safe) from exc
        if "error" in payload:
            code = str(payload["error"])[:100]
            if code == "expired_token" and attempt == 0:
                auth = refresh_auth(auth["access_token"])
                continue
            raise DeliveryError(code, retryable=code == "QUERY_LIMIT_EXCEEDED")
        return payload.get("result")
    raise DeliveryError("TOKEN_REFRESH_LOOP")


def deliver(kind: str, payload: dict, idempotency_key: str, campaign_title: str) -> str:
    bitrix_id = int(payload["bitrix_id"])
    if kind == "bitrix_notification":
        result = rest_call("im.notify.personal.add", {"USER_ID": bitrix_id,
            "MESSAGE": payload.get("message") or f"Назначено обучение: {campaign_title}. Откройте RTM Обучение Next в Битрикс24.",
            "TAG": idempotency_key}, retry_safe=True)
        if not result:
            raise DeliveryError("NOTIFICATION_NOT_CREATED")
        return str(result)
    if kind == "bitrix_task":
        fields = {"TITLE": payload["title"], "DESCRIPTION": payload.get("description", ""),
                  "RESPONSIBLE_ID": bitrix_id}
        if payload.get("due_at"):
            fields["DEADLINE"] = payload["due_at"]
        result = rest_call("tasks.task.add", {"fields": fields}, retry_safe=False)
        task = result.get("task") if isinstance(result, dict) else None
        if not isinstance(task, dict) or not task.get("id"):
            raise DeliveryError("TASK_RESULT_UNKNOWN", uncertain=True)
        return str(task["id"])
    raise DeliveryError("UNSUPPORTED_OUTBOX_JOB")
