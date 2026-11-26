import pytest

from app.media import rutube_embed_url


def test_private_rutube_link_keeps_access_key_in_embed():
    assert rutube_embed_url(
        "https://rutube.ru/video/private/aabbccddeeff00112233445566778899/?p=sampleKey123456789"
    ) == "https://rutube.ru/play/embed/aabbccddeeff00112233445566778899/?p=sampleKey123456789"


@pytest.mark.parametrize("url", [
    "https://rutube.ru/video/private/aabbccddeeff00112233445566778899/",
    "https://rutube.ru/video/private/aabbccddeeff00112233445566778899/?p=",
    "https://rutube.ru/video/private/aabbccddeeff00112233445566778899/?p=abcdefgh&next=evil",
    "https://evil.example/video/private/aabbccddeeff00112233445566778899/?p=abcdefgh",
    "https://rutube.ru/video/aabbccddeeff00112233445566778899/?redirect=evil",
])
def test_rejects_invalid_private_links(url):
    with pytest.raises(ValueError):
        rutube_embed_url(url)
