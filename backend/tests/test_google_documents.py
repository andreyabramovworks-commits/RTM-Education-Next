import pytest

from app import google_documents


def test_extracts_current_document_across_tabs_and_tables():
    document = {"tabs": [{"documentTab": {"body": {"content": [
        {"paragraph": {"paragraphStyle": {"namedStyleType": "HEADING_1"},
                       "elements": [{"textRun": {"content": "Правила\n"}}]}},
        {"table": {"tableRows": [{"tableCells": [
            {"content": [{"paragraph": {"elements": [{"textRun": {"content": "А"}}]}}]},
            {"content": [{"paragraph": {"elements": [{"textRun": {"content": "Б"}}]}}]},
        ]}]}}
    ]}}, "childTabs": [{"documentTab": {"body": {"content": [
        {"paragraph": {"elements": [{"textRun": {"content": "Вложенная вкладка"}}]}}
    ]}}}]}]}
    blocks = google_documents.document_blocks(document)
    assert [block["type"] for block in blocks] == ["paragraph", "table", "paragraph"]
    assert blocks[0] == {"type": "paragraph", "style": "HEADING_1", "text": "Правила"}
    assert google_documents.block_text(blocks[1]) == "А\tБ"
    assert blocks[2]["text"] == "Вложенная вкладка"


def test_revision_snapshot_keeps_source_and_fails_closed(monkeypatch):
    monkeypatch.setattr(google_documents, "read_document", lambda file_id: {
        "file_id": file_id, "revision_id": "rev-1", "text": "Текст документа", "fetched_at": "2026-11-26T00:00:00Z",
        "sha256": "digest", "title": "Источник", "blocks": []})
    source = {"type": "doc", "content": [{"type": "google_document", "attrs": {"fileId": "source12345"}}]}
    result = google_documents.snapshot_google_nodes(source)
    assert result["content"][0]["attrs"]["snapshot"]["revision_id"] == "rev-1"
    assert "snapshot" not in source["content"][0]["attrs"]
    monkeypatch.setattr(google_documents, "read_spreadsheet", lambda _file_id: (_ for _ in ()).throw(
        google_documents.GoogleReadError("GOOGLE_SHEET_TOO_LARGE")))
    with pytest.raises(google_documents.GoogleReadError, match="GOOGLE_SHEET_TOO_LARGE"):
        google_documents.snapshot_google_nodes({"type": "doc", "content": [
            {"type": "google_spreadsheet", "attrs": {"fileId": "source12345"}}]})


def test_reads_all_sheet_tabs_without_truncating(monkeypatch):
    calls = []

    def fake_request(_file_id, url):
        calls.append(url)
        if "fields=" in url:
            return {"properties": {"title": "Операции"}, "sheets": [
                {"properties": {"title": "Лист 1", "gridProperties": {"rowCount": 2, "columnCount": 2}}},
                {"properties": {"title": "Данные", "gridProperties": {"rowCount": 1, "columnCount": 1}}},
            ]}
        return {"values": [["А", "Б"]] if len(calls) == 2 else [["В"]]}

    monkeypatch.setattr(google_documents, "request_google_json", fake_request)
    data = google_documents.read_spreadsheet("sheet12345")
    assert [block["title"] for block in data["blocks"]] == ["Лист 1", "Данные"]
    assert "А\tБ" in data["text"] and "В" in data["text"]
    assert len(calls) == 3
