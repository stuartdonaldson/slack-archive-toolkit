import json

from slackbackup import files_logic


def test_load_index_returns_empty_list_when_missing(tmp_path):
    assert files_logic.load_index(tmp_path / "nope.json") == []


def test_summarize_counts_by_workspace_mimetype_and_context_type(tmp_path):
    index_json = tmp_path / "index.json"
    index_json.write_text(json.dumps([
        {"id": "F1", "workspace": "f3a", "mimetype": "application/pdf",
         "message_context": {"type": "message_attachment"}},
        {"id": "F2", "workspace": "f3a", "mimetype": "application/vnd.slack-docs",
         "message_context": {"type": "channel_canvas"}},
        {"id": "F3", "workspace": "f3b", "mimetype": "application/pdf",
         "message_context": {"type": "search_result"}},
    ]))

    summary = files_logic.summarize(index_json)
    assert summary["total"] == 3
    assert summary["by_workspace"] == {"f3a": 2, "f3b": 1}
    assert summary["by_mimetype"] == {"application/pdf": 2, "application/vnd.slack-docs": 1}
    assert summary["by_context_type"] == {
        "message_attachment": 1, "channel_canvas": 1, "search_result": 1
    }


def test_summarize_empty_index(tmp_path):
    summary = files_logic.summarize(tmp_path / "nope.json")
    assert summary == {"total": 0, "by_workspace": {}, "by_mimetype": {}, "by_context_type": {}}
