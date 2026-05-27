"""Cross-platform `tail -F` replacement for WR inbox logs.

Polls a file for new content and streams it to stdout, line-by-line. Used by
the `/wr-init` skill via Monitor so the recipient session can detect inbound
WRs without depending on shell coreutils (which Windows native cmd lacks).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

POLL_INTERVAL = 0.5


def _read_new(path: Path, pos: int) -> tuple[str, int]:
    """Return (new_text, new_pos) for content past `pos` in `path`.

    Missing files are treated as empty (returns same pos). On truncation
    (file shrank below `pos`), position is reset to 0 and the new content
    is returned from the start.
    """
    path = Path(path)
    if not path.exists():
        return "", pos
    size = path.stat().st_size
    if size < pos:
        pos = 0
    if size == pos:
        return "", pos
    with open(path, "r", encoding="utf-8") as f:
        f.seek(pos)
        text = f.read()
        return text, f.tell()


def _run_tail(path: Path, poll_interval: float = POLL_INTERVAL) -> None:
    """Stream new content from `path` to stdout indefinitely."""
    path = Path(path)
    pos = path.stat().st_size if path.exists() else 0
    while True:
        text, pos = _read_new(path, pos)
        if text:
            sys.stdout.write(text)
            sys.stdout.flush()
        time.sleep(poll_interval)


def main() -> None:
    if len(sys.argv) != 2:
        sys.stderr.write("usage: python -m wr_mcp.tailer <path>\n")
        sys.exit(2)
    _run_tail(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
