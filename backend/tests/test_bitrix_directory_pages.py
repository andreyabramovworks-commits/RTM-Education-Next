import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from app import bitrix


def test_directory_page_identifies_expired_token_in_success_or_error_response(monkeypatch):
    expired = json.dumps({"error": "expired_token"}).encode()
    monkeypatch.setattr(bitrix, "urlopen", lambda _request, timeout: BytesIO(expired))
    with pytest.raises(bitrix.BitrixExpiredToken):
        bitrix.directory_page("user.get", "stale", 0)

    def error(_request, timeout):
        raise HTTPError("https://rtm-group.bitrix24.ru/rest/user.get.json", 401,
                        "expired", {}, BytesIO(expired))
    monkeypatch.setattr(bitrix, "urlopen", error)
    with pytest.raises(bitrix.BitrixExpiredToken):
        bitrix.directory_page("user.get", "stale", 0)
