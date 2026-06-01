import os

import pytest

from wr_mcp import server


def test_read_returns_shape(tmp_path):
    server.wr_register("s2", str(tmp_path))
    server.wr_register("s1", str(tmp_path))
    sent = server.wr_send("s2", "# Title\n\nhello")
    result = server.wr_read(sent["wr_id"])
    assert set(result.keys()) == {"frontmatter", "body", "path"}
    assert result["frontmatter"]["wr_id"] == sent["wr_id"]
    assert result["body"] == "# Title\n\nhello"
    assert result["path"].endswith(f"{sent['wr_id']}.md")
    assert os.path.isabs(result["path"])


def test_read_unknown_wr_id_raises(tmp_path):
    server.wr_register("s2", str(tmp_path))
    server.wr_register("s1", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        server.wr_read("wr-0-x-y-z")


def test_read_sender_can_read_own_wr(tmp_path):
    """No recipient check — sender can read what they sent."""
    server.wr_register("s2", str(tmp_path))
    server.wr_register("s1", str(tmp_path))
    sent = server.wr_send("s2", "mine")
    result = server.wr_read(sent["wr_id"])
    assert result["frontmatter"]["from"] == "s1"


def test_read_preserves_related_to(tmp_path):
    server.wr_register("s2", str(tmp_path))
    server.wr_register("s1", str(tmp_path))
    sent = server.wr_send("s2", "follow-up", related_to="wr-1-s2-s1-x")
    result = server.wr_read(sent["wr_id"])
    assert result["frontmatter"]["related_to"] == "wr-1-s2-s1-x"


def test_read_requires_register():
    with pytest.raises(RuntimeError):
        server.wr_read("wr-0-x-y-z")
