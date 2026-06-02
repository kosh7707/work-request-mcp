import pytest

from wr_mcp import server


def test_lanes_lists_known_with_online_status(tmp_path):
    server.wr_register("s2", str(tmp_path))
    server.wr_register("s1", str(tmp_path))
    res = server.wr_lanes()
    lanes = {entry["lane"]: entry for entry in res["lanes"]}
    assert set(lanes) == {"s1", "s2"}
    assert lanes["s1"]["is_self"] is True
    assert lanes["s2"]["is_self"] is False
    assert lanes["s1"]["online"] and lanes["s2"]["online"]
    assert set(res["online"]) == {"s1", "s2"}
    assert lanes["s2"]["since"]  # registration timestamp carried through


def test_lanes_known_but_offline_after_claim_gone(tmp_path):
    # s2 registered (inbox log persists) then its claim removed = cleanly offline.
    server.wr_register("s2", str(tmp_path))
    server.wr_register("s1", str(tmp_path))
    (tmp_path / "inbox" / "s2.claim").unlink()
    res = server.wr_lanes()
    lanes = {entry["lane"]: entry for entry in res["lanes"]}
    assert "s2" in lanes                 # still KNOWN — log persists
    assert lanes["s2"]["online"] is False
    assert "s2" not in res["online"]


def test_lanes_dead_pid_is_offline(tmp_path, monkeypatch):
    server.wr_register("s2", str(tmp_path))
    server.wr_register("s1", str(tmp_path))
    monkeypatch.setattr(server, "_pid_alive", lambda pid: False)
    lanes = {entry["lane"]: entry for entry in server.wr_lanes()["lanes"]}
    assert lanes["s1"]["online"] is False
    assert lanes["s2"]["online"] is False


def test_lanes_requires_register():
    with pytest.raises(RuntimeError):
        server.wr_lanes()
