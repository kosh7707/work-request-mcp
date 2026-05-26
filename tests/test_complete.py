from pathlib import Path

import pytest

from wr_mcp import server
from wr_mcp.server import NotRecipientError, _read_md


def test_complete_happy_path(tmp_path):
    server.wr_register("s1", str(tmp_path))
    sent = server.wr_send("s2", "# Title\n\nbody")
    server._reset_for_tests()
    server.wr_register("s2", str(tmp_path))
    result = server.wr_complete(sent["wr_id"])
    assert result == {"wr_id": sent["wr_id"], "status": "completed"}
    fm, _ = _read_md(Path(sent["path"]))
    assert fm["status"] == "completed"
    assert "completed_at" in fm
    assert "completed_note" not in fm


def test_complete_with_note(tmp_path):
    server.wr_register("s1", str(tmp_path))
    sent = server.wr_send("s2", "# Title\n\nbody")
    server._reset_for_tests()
    server.wr_register("s2", str(tmp_path))
    server.wr_complete(sent["wr_id"], note="done, see PR #42")
    fm, _ = _read_md(Path(sent["path"]))
    assert fm["completed_note"] == "done, see PR #42"


def test_complete_rejects_non_recipient(tmp_path):
    server.wr_register("s1", str(tmp_path))
    sent = server.wr_send("s2", "# Title\n\nbody")
    # still registered as s1 (sender) — try to complete as sender
    with pytest.raises(NotRecipientError) as ei:
        server.wr_complete(sent["wr_id"])
    assert isinstance(ei.value, PermissionError)
    fm, _ = _read_md(Path(sent["path"]))
    assert fm["status"] == "open"


def test_complete_unknown_wr_id_raises(tmp_path):
    server.wr_register("s1", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        server.wr_complete("wr-0-x-y-z")


def test_complete_idempotent_re_complete_resets_timestamp(tmp_path):
    server.wr_register("s1", str(tmp_path))
    sent = server.wr_send("s2", "# Title\n\nbody")
    server._reset_for_tests()
    server.wr_register("s2", str(tmp_path))
    server.wr_complete(sent["wr_id"], note="first pass")
    fm1, _ = _read_md(Path(sent["path"]))
    # second complete allowed; updates completed_at and note
    import time
    time.sleep(0.002)
    server.wr_complete(sent["wr_id"], note="second pass")
    fm2, _ = _read_md(Path(sent["path"]))
    assert fm2["status"] == "completed"
    assert fm2["completed_note"] == "second pass"
    assert fm2["completed_at"] >= fm1["completed_at"]


def test_complete_requires_register():
    with pytest.raises(RuntimeError):
        server.wr_complete("wr-0-x-y-z")
