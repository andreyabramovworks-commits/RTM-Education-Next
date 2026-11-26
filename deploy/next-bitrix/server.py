import hmac
import html
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse, urlencode
from urllib.request import Request, urlopen

PORTAL = "rtm-group.bitrix24.ru"
CLIENT_ID = os.environ.get("BITRIX_CLIENT_ID", "")
AUTH_FILE = Path("/data/bitrix-auth.json")


def rest(method, token):
    body = urlencode({"auth": token}).encode()
    request = Request(f"https://{PORTAL}/rest/{method}.json", data=body)
    with urlopen(request, timeout=8) as response:
        return json.load(response).get("result")


def fields(raw):
    parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def reply(self, code, body=b"", content_type="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors https://rtm-group.bitrix24.ru")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self.reply(200, b"ok")
        elif path in ("/app", "/install"):
            self.reply(200, b"RTM Education Next endpoint. Bitrix24 uses POST to open this page.")
        else:
            self.reply(404)

    def do_HEAD(self):
        if urlparse(self.path).path in ("/health", "/app", "/install"):
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/install", "/app"):
            return self.reply(404)
        if not CLIENT_ID:
            return self.reply(503, b"Bitrix client ID is not configured")
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 32768:
                return self.reply(400)
            data = fields(self.rfile.read(size))
            if path == "/install":
                if data.get("event") != "ONAPPINSTALL":
                    return self.reply(403)
                auth = {key[5:-1]: value for key, value in data.items()
                        if key.startswith("auth[") and key.endswith("]")}
                required = ("access_token", "refresh_token", "member_id", "application_token")
                if not all(auth.get(key) for key in required):
                    return self.reply(403)
                info = rest("app.info", auth["access_token"])
                if not isinstance(info, dict) or info.get("CODE") != CLIENT_ID:
                    return self.reply(403)
                AUTH_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                temporary = AUTH_FILE.with_suffix(".tmp")
                temporary.write_text(json.dumps(auth))
                os.chmod(temporary, 0o600)
                temporary.replace(AUTH_FILE)
                return self.reply(200, b"Installed")
            if not AUTH_FILE.is_file():
                return self.reply(503, b"Application is not installed")
            saved = json.loads(AUTH_FILE.read_text())
            domain = parse_qs(urlparse(self.path).query).get("DOMAIN", [""])[-1]
            if domain != PORTAL or not hmac.compare_digest(data.get("APPLICATION_TOKEN", ""), saved["application_token"]):
                return self.reply(403)
            if data.get("member_id") != saved["member_id"] or not data.get("AUTH_ID"):
                return self.reply(403)
            user = rest("user.current", data["AUTH_ID"])
            if not isinstance(user, dict) or not user.get("ID"):
                return self.reply(403)
            name = html.escape(" ".join(str(user.get(part, "")) for part in ("NAME", "LAST_NAME")).strip())
            page = f"<!doctype html><html lang='ru'><meta charset='utf-8'><title>RTM Обучение Next</title><body><h1>RTM Обучение Next</h1><p>Вход подтверждён: {name}</p><p>Учебные функции подключаются.</p></body></html>"
            return self.reply(200, page.encode(), "text/html; charset=utf-8")
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return self.reply(502, b"Bitrix verification failed")


HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
