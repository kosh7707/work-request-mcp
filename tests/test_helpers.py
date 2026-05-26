import re
import time

import pytest

from wr_mcp.server import _now_iso, _read_md, _slugify, _write_md


def test_slugify_basic():
    assert _slugify("Hello World") == "hello-world"


def test_slugify_strips_heading_hash_and_punctuation():
    assert _slugify("# Fix the bug!!!") == "fix-the-bug"


def test_slugify_empty_returns_untitled():
    assert _slugify("") == "untitled"


def test_slugify_whitespace_returns_untitled():
    assert _slugify("   ") == "untitled"


def test_slugify_max_50_chars():
    result = _slugify("a" * 200)
    assert len(result) <= 50
    assert set(result) == {"a"}


def test_slugify_collapses_non_alnum():
    assert _slugify("foo___bar...baz") == "foo-bar-baz"


def test_slugify_strips_leading_trailing_dashes():
    assert _slugify("--leading and trailing--") == "leading-and-trailing"


def test_slugify_non_ascii_collapses():
    assert _slugify("Café 123") == "caf-123"


def test_now_iso_format():
    s = _now_iso()
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(\+00:00|Z)$", s)


def test_now_iso_monotonic():
    t1 = _now_iso()
    time.sleep(0.002)
    t2 = _now_iso()
    assert t2 >= t1


def test_now_iso_utc_marker():
    s = _now_iso()
    assert s.endswith("+00:00") or s.endswith("Z")


def test_read_write_md_round_trip(tmp_path):
    path = tmp_path / "x.md"
    fm = {
        "wr_id": "wr-1-s1-s2-x",
        "from": "s1",
        "to": "s2",
        "status": "open",
        "registered_at": "2026-01-01T00:00:00+00:00",
    }
    body = "Hello\n\nWorld\n"
    _write_md(path, fm, body)
    fm_out, body_out = _read_md(path)
    assert fm_out == fm
    assert body_out == body


def test_write_md_starts_with_frontmatter_delimiter(tmp_path):
    path = tmp_path / "x.md"
    _write_md(path, {"k": "v"}, "body")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    # second delimiter
    assert text.count("\n---\n") >= 1


def test_write_md_omits_none_fields(tmp_path):
    path = tmp_path / "x.md"
    fm = {"wr_id": "x", "completed_at": None, "related_to": None}
    _write_md(path, fm, "body")
    fm_out, _ = _read_md(path)
    # convention: None values omitted on write
    assert "completed_at" not in fm_out
    assert "related_to" not in fm_out
    assert fm_out["wr_id"] == "x"


def test_read_md_no_frontmatter_raises(tmp_path):
    path = tmp_path / "x.md"
    path.write_text("no frontmatter here\n", encoding="utf-8")
    with pytest.raises(ValueError):
        _read_md(path)
