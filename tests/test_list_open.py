import os
import time

import pytest

from wr_mcp import server


def test_list_open_empty(tmp_path):
    server.wr_register("s2", str(tmp_path))
    assert server.wr_list_open() == []


def test_list_open_filters_by_to(tmp_path):
    # s1 -> s2 (A)
    server.wr_register("s1", str(tmp_path))
    a = server.wr_send("s2", "from s1")["wr_id"]
    server._reset_for_tests()
    # s3 -> s2 (B)
    server.wr_register("s3", str(tmp_path))
    b = server.wr_send("s2", "from s3")["wr_id"]
    server._reset_for_tests()
    # read as s2
    server.wr_register("s2", str(tmp_path))
    result = server.wr_list_open()
    assert {e["wr_id"] for e in result} == {a, b}


def test_list_open_excludes_completed(tmp_path):
    server.wr_register("s1", str(tmp_path))
    sent = server.wr_send("s2", "x")
    server._reset_for_tests()
    server.wr_register("s2", str(tmp_path))
    server.wr_complete(sent["wr_id"])
    assert server.wr_list_open() == []


def test_list_open_excludes_sent_by_self(tmp_path):
    server.wr_register("s1", str(tmp_path))
    server.wr_send("s2", "x")
    assert server.wr_list_open() == []  # s1 is sender, not recipient


def test_list_open_sorted_by_registered_at(tmp_path):
    server.wr_register("s1", str(tmp_path))
    ids = []
    for i in range(3):
        ids.append(server.wr_send("s2", f"msg {i}")["wr_id"])
        time.sleep(0.002)
    server._reset_for_tests()
    server.wr_register("s2", str(tmp_path))
    result = server.wr_list_open()
    assert [e["wr_id"] for e in result] == ids
    # also assert registered_at strings are monotonic
    rats = [e["registered_at"] for e in result]
    assert rats == sorted(rats)


def test_list_open_entry_shape(tmp_path):
    server.wr_register("s1", str(tmp_path))
    server.wr_send("s2", "x")
    server._reset_for_tests()
    server.wr_register("s2", str(tmp_path))
    result = server.wr_list_open()
    assert len(result) == 1
    e = result[0]
    assert set(e.keys()) == {"wr_id", "from", "registered_at", "path"}
    for v in e.values():
        assert isinstance(v, str)
    assert os.path.isabs(e["path"])


def test_list_open_ignores_non_md_files(tmp_path):
    server.wr_register("s1", str(tmp_path))
    server.wr_send("s2", "x")
    # drop a stray non-md file
    (tmp_path / "messages" / "notes.txt").write_text("noise", encoding="utf-8")
    server._reset_for_tests()
    server.wr_register("s2", str(tmp_path))
    result = server.wr_list_open()
    assert len(result) == 1


def test_list_open_ignores_malformed_md_silently(tmp_path):
    server.wr_register("s1", str(tmp_path))
    server.wr_send("s2", "x")
    # drop a malformed md file (no frontmatter)
    (tmp_path / "messages" / "broken.md").write_text("no frontmatter", encoding="utf-8")
    server._reset_for_tests()
    server.wr_register("s2", str(tmp_path))
    result = server.wr_list_open()
    assert len(result) == 1  # broken.md skipped


def test_list_open_requires_register():
    with pytest.raises(RuntimeError):
        server.wr_list_open()
