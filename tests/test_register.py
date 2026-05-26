from pathlib import Path

from wr_mcp import server


def test_register_creates_dirs(tmp_path):
    server.wr_register("s1", str(tmp_path))
    assert (tmp_path / "messages").is_dir()
    assert (tmp_path / "inbox").is_dir()
    log = tmp_path / "inbox" / "s1.log"
    assert log.is_file()
    assert log.stat().st_size == 0


def test_register_sets_globals(tmp_path):
    server.wr_register("s1", str(tmp_path))
    assert server._lane == "s1"
    assert server._root == Path(tmp_path).resolve()


def test_register_return_value(tmp_path):
    result = server.wr_register("s1", str(tmp_path))
    assert result["lane"] == "s1"
    assert result["root"] == str(Path(tmp_path).resolve())
    assert result["inbox"].endswith("/inbox/s1.log")


def test_register_idempotent_does_not_truncate(tmp_path):
    server.wr_register("s1", str(tmp_path))
    log = tmp_path / "inbox" / "s1.log"
    log.write_text("existing\n", encoding="utf-8")
    server.wr_register("s1", str(tmp_path))
    assert log.read_text(encoding="utf-8") == "existing\n"


def test_register_switches_lane(tmp_path):
    server.wr_register("s1", str(tmp_path))
    server.wr_register("s2", str(tmp_path))
    assert server._lane == "s2"
    assert (tmp_path / "inbox" / "s2.log").is_file()
    assert (tmp_path / "inbox" / "s1.log").is_file()
