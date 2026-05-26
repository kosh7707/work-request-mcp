from pathlib import Path

import pytest

from wr_mcp import server


def test_info_fresh_session(tmp_path):
    server.wr_register("s1", str(tmp_path))
    info = server.wr_info()
    assert info["lane"] == "s1"
    assert info["root"] == str(Path(tmp_path).resolve())
    assert info["inbox"].endswith("/inbox/s1.log")
    assert info["sent_open"] == 0
    assert info["received_open"] == 0


def test_info_sent_open_count(tmp_path):
    import time
    server.wr_register("s1", str(tmp_path))
    for i in range(3):
        server.wr_send("s2", f"msg {i}")
        time.sleep(0.002)
    info = server.wr_info()
    assert info["sent_open"] == 3
    assert info["received_open"] == 0


def test_info_received_open_count(tmp_path):
    import time
    server.wr_register("s1", str(tmp_path))
    server.wr_send("s2", "x")
    time.sleep(0.002)
    server.wr_send("s2", "y")
    server._reset_for_tests()
    server.wr_register("s2", str(tmp_path))
    info = server.wr_info()
    assert info["sent_open"] == 0
    assert info["received_open"] == 2


def test_info_completed_excluded_from_both(tmp_path):
    server.wr_register("s1", str(tmp_path))
    sent = server.wr_send("s2", "x")
    server._reset_for_tests()
    server.wr_register("s2", str(tmp_path))
    server.wr_complete(sent["wr_id"])
    info_s2 = server.wr_info()
    assert info_s2["received_open"] == 0
    server._reset_for_tests()
    server.wr_register("s1", str(tmp_path))
    info_s1 = server.wr_info()
    assert info_s1["sent_open"] == 0


def test_info_ignores_other_lanes(tmp_path):
    server.wr_register("s1", str(tmp_path))
    server.wr_send("s2", "x")
    server._reset_for_tests()
    server.wr_register("s3", str(tmp_path))
    info = server.wr_info()
    assert info["sent_open"] == 0
    assert info["received_open"] == 0


def test_info_requires_register():
    with pytest.raises(RuntimeError):
        server.wr_info()
