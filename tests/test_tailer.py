import subprocess
import sys
import time
from pathlib import Path

from wr_mcp.tailer import _read_new


def test_read_new_missing_file(tmp_path):
    p = tmp_path / "missing"
    text, pos = _read_new(p, 42)
    assert text == ""
    assert pos == 42


def test_read_new_empty_file(tmp_path):
    p = tmp_path / "log"
    p.write_text("", encoding="utf-8")
    text, pos = _read_new(p, 0)
    assert text == ""
    assert pos == 0


def test_read_new_full_read(tmp_path):
    p = tmp_path / "log"
    content = "hello\nworld\n"
    p.write_text(content, encoding="utf-8")
    text, pos = _read_new(p, 0)
    assert text == content
    assert pos == len(content.encode("utf-8"))


def test_read_new_from_position(tmp_path):
    p = tmp_path / "log"
    p.write_text("hello\nworld\n", encoding="utf-8")
    start = len("hello\n".encode("utf-8"))
    text, pos = _read_new(p, start)
    assert text == "world\n"
    assert pos == len("hello\nworld\n".encode("utf-8"))


def test_read_new_no_growth(tmp_path):
    p = tmp_path / "log"
    p.write_text("hello\n", encoding="utf-8")
    size = p.stat().st_size
    text, pos = _read_new(p, size)
    assert text == ""
    assert pos == size


def test_read_new_truncation_resets(tmp_path):
    p = tmp_path / "log"
    p.write_text("longer content here\n", encoding="utf-8")
    old_size = p.stat().st_size
    p.write_text("short\n", encoding="utf-8")
    text, pos = _read_new(p, old_size)
    assert text == "short\n"
    assert pos == len("short\n".encode("utf-8"))


def test_tailer_subprocess_streams_appended_lines(tmp_path):
    """End-to-end: spawn `python -m wr_mcp.tailer`, append lines, see them on stdout."""
    log = tmp_path / "inbox.log"
    log.write_text("", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "wr_mcp.tailer", str(log)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        # let tailer establish initial position
        time.sleep(0.6)
        with open(log, "a", encoding="utf-8") as f:
            f.write("first\n")
        # poll stdout up to 5s for the line
        deadline = time.time() + 5.0
        collected = ""
        while time.time() < deadline:
            line = proc.stdout.readline()
            if line:
                collected += line
                if "first\n" in collected:
                    break
            else:
                # readline may return empty briefly; small sleep
                time.sleep(0.1)
        assert "first" in collected, f"got: {collected!r}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_tailer_subprocess_usage_error_exits_nonzero():
    proc = subprocess.run(
        [sys.executable, "-m", "wr_mcp.tailer"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert proc.returncode != 0
    assert "usage" in proc.stderr.lower()
