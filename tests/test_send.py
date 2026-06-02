import os
import re
import time
from pathlib import Path

import pytest

from wr_mcp import server
from wr_mcp.server import _read_md


def _register_pair(tmp_path):
    # Recipient s2 must have an inbox before s1 can send to it.
    server.wr_register("s2", str(tmp_path))
    server.wr_register("s1", str(tmp_path))


def test_send_writes_md_file(tmp_path):
    _register_pair(tmp_path)
    result = server.wr_send("s2", "# Help me\n\nplease")
    assert "wr_id" in result and "path" in result
    p = Path(result["path"])
    assert p.is_file()
    assert p.parent == (tmp_path / "messages").resolve()
    assert p.name == f"{result['wr_id']}.md"


def test_send_wr_id_format(tmp_path):
    _register_pair(tmp_path)
    result = server.wr_send("s2", "# Help me\n\nplease")
    wr_id = result["wr_id"]
    m = re.match(r"^wr-(\d+)-s1-s2-help-me$", wr_id)
    assert m, wr_id
    unix_ms_in_id = int(m.group(1))
    assert abs(unix_ms_in_id - int(time.time() * 1000)) < 5000


def test_send_slug_explicit(tmp_path):
    _register_pair(tmp_path)
    result = server.wr_send("s2", "anything", slug="my custom slug")
    assert result["wr_id"].endswith("-my-custom-slug")


def test_send_slug_derived_strips_heading_hash(tmp_path):
    _register_pair(tmp_path)
    result = server.wr_send("s2", "# Fix\n\nbody")
    assert result["wr_id"].endswith("-fix")


def test_send_slug_derived_skips_empty_lines(tmp_path):
    _register_pair(tmp_path)
    result = server.wr_send("s2", "\n\n  \n# Real title\nbody")
    assert result["wr_id"].endswith("-real-title")


def test_send_slug_fallback_untitled(tmp_path):
    _register_pair(tmp_path)
    result = server.wr_send("s2", "")
    assert result["wr_id"].endswith("-untitled")


def test_send_atomicity_no_partial_file(tmp_path, monkeypatch):
    """Monkeypatch os.replace to raise. Assert no .md file in messages/."""
    _register_pair(tmp_path)
    import wr_mcp.server as srv

    def boom(*args, **kwargs):
        raise RuntimeError("simulated mid-write failure")

    monkeypatch.setattr(srv.os, "replace", boom)
    with pytest.raises(RuntimeError, match="simulated"):
        server.wr_send("s2", "# Title\n\nbody")
    assert list((tmp_path / "messages").glob("*.md")) == []


def test_send_appends_inbox_notify_exact_line(tmp_path):
    _register_pair(tmp_path)
    result = server.wr_send("s2", "# Title\n\nbody")
    s2_log = tmp_path / "inbox" / "s2.log"
    assert s2_log.is_file()
    content = s2_log.read_text(encoding="utf-8")
    assert content.endswith("\n")
    lines = content.strip().split("\n")
    assert len(lines) == 1
    expected = f"notify wr_id={result['wr_id']} from=s1 path={result['path']}"
    assert lines[0] == expected
    # path must be absolute
    assert os.path.isabs(result["path"])


def test_send_appends_not_overwrites(tmp_path):
    _register_pair(tmp_path)
    r1 = server.wr_send("s2", "first message")
    time.sleep(0.002)
    r2 = server.wr_send("s2", "second message")
    s2_log = tmp_path / "inbox" / "s2.log"
    lines = s2_log.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert r1["wr_id"] in lines[0]
    assert r2["wr_id"] in lines[1]


def test_send_frontmatter_content(tmp_path):
    _register_pair(tmp_path)
    result = server.wr_send("s2", "# Title\n\nbody text")
    fm, _ = _read_md(Path(result["path"]))
    assert fm["wr_id"] == result["wr_id"]
    assert fm["from"] == "s1"
    assert fm["to"] == "s2"
    assert fm["status"] == "open"
    assert "registered_at" in fm
    assert "completed_at" not in fm
    assert "related_to" not in fm


def test_send_with_related_to(tmp_path):
    _register_pair(tmp_path)
    result = server.wr_send("s2", "follow-up", related_to="wr-1-s2-s1-x")
    fm, _ = _read_md(Path(result["path"]))
    assert fm["related_to"] == "wr-1-s2-s1-x"


def test_send_body_preserved(tmp_path):
    _register_pair(tmp_path)
    body = "# Title\n\nLine 1\n\nLine 2\n"
    result = server.wr_send("s2", body)
    _, body_out = _read_md(Path(result["path"]))
    assert body_out == body


def test_send_requires_register():
    with pytest.raises(RuntimeError):
        server.wr_send("s2", "x")


def test_send_to_unregistered_lane_errors(tmp_path):
    server.wr_register("s1", str(tmp_path))
    with pytest.raises(ValueError, match="never registered"):
        server.wr_send("s99", "x")
    # no orphan md written for the failed send
    assert list((tmp_path / "messages").glob("*.md")) == []


def test_send_online_recipient_flagged_no_warning(tmp_path):
    _register_pair(tmp_path)
    result = server.wr_send("s2", "x")
    assert result["recipient_online"] is True
    assert "warning" not in result


def test_send_offline_recipient_warns_but_delivers(tmp_path):
    # s2 KNOWN (inbox log) but offline (claim removed) -> deliver + warn, never block.
    _register_pair(tmp_path)
    (tmp_path / "inbox" / "s2.claim").unlink()
    result = server.wr_send("s2", "queued for later")
    assert result["recipient_online"] is False
    assert "warning" in result and "offline" in result["warning"]
    # delivered anyway: md written + notify line appended (mailbox semantics)
    assert Path(result["path"]).is_file()
    assert (tmp_path / "inbox" / "s2.log").read_text(encoding="utf-8").strip()


def test_send_fsyncs_inbox_line(tmp_path, monkeypatch):
    _register_pair(tmp_path)
    calls = []
    real_fsync = server.os.fsync
    monkeypatch.setattr(server.os, "fsync", lambda fd: calls.append(fd) or real_fsync(fd))
    server.wr_send("s2", "x")
    assert calls  # notify line durably flushed
