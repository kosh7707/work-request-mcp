import json
import os

import pytest

from wr_mcp import server


def test_register_writes_claim(tmp_path):
    server.wr_register("s1", str(tmp_path))
    claim = tmp_path / "inbox" / "s1.claim"
    assert claim.is_file()
    data = json.loads(claim.read_text(encoding="utf-8"))
    assert data["pid"] == os.getpid()
    assert "at" in data


def test_register_same_pid_reregister_ok(tmp_path):
    # same process re-registering its own lane must not raise (pid == me)
    server.wr_register("s1", str(tmp_path))
    server.wr_register("s1", str(tmp_path))
    assert server._lane == "s1"


def _plant_claim(tmp_path, lane, pid):
    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / f"{lane}.claim").write_text(
        json.dumps({"pid": pid, "at": "2026-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    (inbox / f"{lane}.log").touch()


def test_register_rejects_live_other_pid(tmp_path, monkeypatch):
    _plant_claim(tmp_path, "s1", 4242)
    monkeypatch.setattr(server, "_pid_alive", lambda pid: True)
    with pytest.raises(server.LaneClaimedError, match="already held by pid 4242"):
        server.wr_register("s1", str(tmp_path))


def test_register_steals_dead_pid(tmp_path, monkeypatch):
    _plant_claim(tmp_path, "s1", 4242)
    monkeypatch.setattr(server, "_pid_alive", lambda pid: False)
    server.wr_register("s1", str(tmp_path))  # dead claim -> auto steal
    data = json.loads((tmp_path / "inbox" / "s1.claim").read_text(encoding="utf-8"))
    assert data["pid"] == os.getpid()


def test_register_force_steals_live(tmp_path, monkeypatch):
    _plant_claim(tmp_path, "s1", 4242)
    monkeypatch.setattr(server, "_pid_alive", lambda pid: True)
    server.wr_register("s1", str(tmp_path), force=True)
    data = json.loads((tmp_path / "inbox" / "s1.claim").read_text(encoding="utf-8"))
    assert data["pid"] == os.getpid()


def test_register_corrupt_claim_is_stealable(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "s1.claim").write_text("not json", encoding="utf-8")
    (inbox / "s1.log").touch()
    server.wr_register("s1", str(tmp_path))  # unparseable -> no holder -> ok
    assert server._lane == "s1"


def test_register_claim_atomic_no_partial(tmp_path, monkeypatch):
    import wr_mcp.server as srv

    def boom(*a, **k):
        raise RuntimeError("simulated replace failure")

    monkeypatch.setattr(srv.os, "replace", boom)
    with pytest.raises(RuntimeError, match="simulated"):
        server.wr_register("s1", str(tmp_path))
    # failed claim write leaves no partial claim and no stray temp file
    assert list((tmp_path / "inbox").glob("*.claim")) == []
    assert list((tmp_path / "inbox").glob(".tmp-*")) == []


def test_pid_alive_self():
    assert server._pid_alive(os.getpid()) is True


def test_pid_alive_dead(monkeypatch):
    def _no_proc(pid, sig):
        raise ProcessLookupError

    monkeypatch.setattr(server.os, "kill", _no_proc)
    assert server._pid_alive(1234) is False
