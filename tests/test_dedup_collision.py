import hashlib
from pathlib import Path

from wr_mcp import server
from wr_mcp.server import _read_md


def _pair(tmp_path):
    """Register recipient s2 (so its inbox exists), then sender s1."""
    server.wr_register("s2", str(tmp_path))
    server.wr_register("s1", str(tmp_path))


def _md_count(tmp_path):
    return len(list((tmp_path / "messages").glob("*.md")))


def test_send_dedup_identical_returns_existing(tmp_path):
    _pair(tmp_path)
    r1 = server.wr_send("s2", "# Same\n\nbody")
    r2 = server.wr_send("s2", "# Same\n\nbody")
    assert r2["wr_id"] == r1["wr_id"]
    assert r2.get("dedup") is True
    assert _md_count(tmp_path) == 1
    log = (tmp_path / "inbox" / "s2.log").read_text(encoding="utf-8")
    assert log.strip().count("\n") == 0  # exactly one notify line


def test_send_dedup_distinct_body_not_collapsed(tmp_path):
    _pair(tmp_path)
    server.wr_send("s2", "alpha")
    server.wr_send("s2", "beta")
    assert _md_count(tmp_path) == 2


def test_send_dedup_differs_by_related_to(tmp_path):
    _pair(tmp_path)
    server.wr_send("s2", "same body")
    server.wr_send("s2", "same body", related_to="wr-1-s2-s1-x")
    assert _md_count(tmp_path) == 2


def test_send_reopens_after_complete(tmp_path):
    _pair(tmp_path)
    r1 = server.wr_send("s2", "# Same\n\nbody")
    server._reset_for_tests()
    server.wr_register("s2", str(tmp_path))
    server.wr_complete(r1["wr_id"])
    server._reset_for_tests()
    server.wr_register("s1", str(tmp_path))
    r2 = server.wr_send("s2", "# Same\n\nbody")  # prior is completed -> new WR
    assert r2["wr_id"] != r1["wr_id"]
    assert "dedup" not in r2


def test_send_body_sha256_in_frontmatter(tmp_path):
    _pair(tmp_path)
    r = server.wr_send("s2", "hello body")
    fm, _ = _read_md(Path(r["path"]))
    assert fm["body_sha256"] == hashlib.sha256(b"hello body").hexdigest()


def test_send_wr_id_collision_bumps_ms(tmp_path, monkeypatch):
    _pair(tmp_path)
    monkeypatch.setattr(server.time, "time", lambda: 1000.0)  # freeze unix ms
    # distinct bodies so dedup does NOT fire; same slug forces the id collision
    r1 = server.wr_send("s2", "first body", slug="dup")
    r2 = server.wr_send("s2", "second body", slug="dup")
    assert r1["wr_id"] != r2["wr_id"]
    assert _md_count(tmp_path) == 2
