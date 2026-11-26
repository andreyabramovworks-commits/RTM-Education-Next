"""One-time local Google authorization; never commit either JSON file."""

import json
import os
from pathlib import Path

import requests
from google_auth_oauthlib.flow import InstalledAppFlow


ROOT = Path(__file__).resolve().parent.parent
CLIENT_FILE = ROOT / "private" / "google-oauth-client.json"
TOKEN_FILE = ROOT / "private" / "google-credentials.json"
EXPECTED_EMAIL = "aiapprtm@gmail.com"
SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/documents.readonly",
          "https://www.googleapis.com/auth/spreadsheets.readonly"]


def main() -> None:
    if not CLIENT_FILE.is_file():
        raise SystemExit(f"Сначала сохраните OAuth JSON сюда: {CLIENT_FILE}")
    payload = json.loads(CLIENT_FILE.read_text(encoding="utf-8"))
    if "installed" not in payload:
        raise SystemExit("Нужен OAuth client типа Desktop app.")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
    credentials = flow.run_local_server(host="127.0.0.1", port=0, open_browser=False,
                                        authorization_prompt_message="Откройте эту ссылку в Chrome с aiapprtm@gmail.com: {url}",
                                        success_message="Доступ передан локальному помощнику. Вернитесь в Codex.",
                                        access_type="offline", prompt="consent select_account")
    response = requests.get("https://www.googleapis.com/oauth2/v3/userinfo",
                            headers={"Authorization": f"Bearer {credentials.token}"}, timeout=15)
    response.raise_for_status()
    email = response.json().get("email", "").lower()
    if email != EXPECTED_EMAIL:
        raise SystemExit(f"Выбран {email}, нужен {EXPECTED_EMAIL}. Файл доступа не сохранён.")
    if not credentials.refresh_token:
        raise SystemExit("Google не вернул refresh token. Файл доступа не сохранён.")
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        payload = json.loads(credentials.to_json())
        payload["type"] = "authorized_user"
        output.write(json.dumps(payload))
    print(f"Готово: серверный доступ для {email} сохранён в закрытом файле.")


if __name__ == "__main__":
    main()
