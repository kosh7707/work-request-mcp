import json

import pytest

from wr_mcp import server


def test_unregister_removes_own_claim_and_clears_state(tmp_path):
    server.wr_register("s1", str(tmp_path))
    result = server.wr_unregister()
    assert result["lane"] == "s1"
    assert result["released"] is True
    assert not (tmp_path / "inbox" / "s1.claim").exists()
    assert server._lane is None
    assert server._root is None


def test_unregister_keeps_inbox_log_and_messages(tmp_path):
    # s2 is the recipient; s1 sends one WR, then unregisters
    server.wr_register("s2", str(tmp_path))
    server.wr_register("s1", str(tmp_path))
    server.wr_send("s2", "keep me")
    server.wr_unregister()
    assert (tmp_path / "inbox" / "s2.log").exists()       # inbox log preserved
    assert (tmp_path / "inbox" / "s1.log").exists()       # own log preserved
    assert len(list((tmp_path / "messages").glob("*.md"))) == 1  # message preserved


def test_unregister_does_not_remove_other_pid_claim(tmp_path):
    server.wr_register("s1", str(tmp_path))
    # someone else stole the lane: claim now held by a different pid
    claim = tmp_path / "inbox" / "s1.claim"
    claim.write_text(json.dumps({"pid": 4242, "at": "x"}), encoding="utf-8")
    result = server.wr_unregister()
    assert result["released"] is False
    assert claim.exists()              # not ours -> left intact
    assert server._lane is None        # but we still drop our own session state


def test_unregister_claim_already_absent(tmp_path):
    server.wr_register("s1", str(tmp_path))
    (tmp_path / "inbox" / "s1.claim").unlink()  # claim vanished out from under us
    result = server.wr_unregister()
    assert result["released"] is False
    assert server._lane is None


def test_unregister_corrupt_claim_not_removed(tmp_path):
    server.wr_register("s1", str(tmp_path))
    claim = tmp_path / "inbox" / "s1.claim"
    claim.write_text("{bad json", encoding="utf-8")  # unparseable -> not ours to delete
    result = server.wr_unregister()
    assert result["released"] is False
    assert claim.exists()
    assert server._lane is None


def test_unregister_requires_register():
    with pytest.raises(RuntimeError):
        server.wr_unregister()


def test_unregister_then_reregister(tmp_path):
    server.wr_register("s1", str(tmp_path))
    server.wr_unregister()
    # lane is free again -> clean re-register, no LaneClaimedError
    out = server.wr_register("s1", str(tmp_path))
    assert out["lane"] == "s1"
    assert (tmp_path / "inbox" / "s1.claim").exists()
