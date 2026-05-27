"""wr-mcp server: MCP tools for inter-session WR messaging."""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("wr-mcp")


class NotRecipientError(PermissionError):
    """Raised when a non-recipient tries to complete a WR."""


_SLUG_RE = re.compile(r"[^a-z0-9]+")
_MAX_SLUG_LEN = 50

_lane: str | None = None
_root: Path | None = None


def _reset_for_tests() -> None:
    global _lane, _root
    _lane = None
    _root = None


def _slugify(text: str) -> str:
    s = text.lower().lstrip("#").strip()
    s = _SLUG_RE.sub("-", s).strip("-")
    s = s[:_MAX_SLUG_LEN]
    return s or "untitled"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_md(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    """Atomically write a markdown file with YAML frontmatter.

    None-valued frontmatter keys are omitted on write.
    """
    fm = {k: v for k, v in frontmatter.items() if v is not None}
    front = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
    text = f"---\n{front}---\n{body}"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _read_md(path: Path) -> tuple[dict[str, Any], str]:
    """Read a markdown file with YAML frontmatter. Returns (frontmatter, body)."""
    text = Path(path).read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"no frontmatter in {path}")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError(f"unterminated frontmatter in {path}")
    fm = yaml.safe_load(text[4:end + 1]) or {}
    body = text[end + len("\n---\n"):]
    return fm, body


def _require_session() -> tuple[str, Path]:
    if _lane is None or _root is None:
        raise RuntimeError("wr_register must be called first")
    return _lane, _root


def _derive_slug_from_body(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            return _slugify(stripped.lstrip("#").strip())
    return "untitled"


@mcp.tool()
def wr_register(lane: str, root: str) -> dict[str, str]:
    """Register this session as a WR lane.

    Creates `<root>/messages/` and `<root>/inbox/` directories, touches the
    inbox log file for the given lane (without truncating it), and stores
    `lane` and `root` in module-level state for use by other tools.

    Returns a `monitor_cmd` field that the calling skill should pass verbatim
    to the Claude Code `Monitor` tool. The command spawns a cross-platform
    tail process (Python-based) so the SKILL does not depend on shell
    coreutils — works on Linux, macOS, and Windows alike.
    """
    global _lane, _root
    root_path = Path(root).expanduser().resolve()
    (root_path / "messages").mkdir(parents=True, exist_ok=True)
    (root_path / "inbox").mkdir(parents=True, exist_ok=True)
    inbox_log = root_path / "inbox" / f"{lane}.log"
    inbox_log.touch(exist_ok=True)
    _lane = lane
    _root = root_path
    monitor_cmd = f'"{sys.executable}" -m wr_mcp.tailer "{inbox_log}"'
    return {
        "lane": lane,
        "root": str(root_path),
        "inbox": str(inbox_log),
        "monitor_cmd": monitor_cmd,
    }


@mcp.tool()
def wr_send(
    to: str,
    body: str,
    slug: str | None = None,
    related_to: str | None = None,
) -> dict[str, str]:
    """Send a WR to another lane.

    Writes a markdown file under `<root>/messages/` with YAML frontmatter,
    then appends a notify line to `<root>/inbox/<to>.log` so the recipient
    can detect the new WR via a tail -F Monitor.
    """
    lane, root = _require_session()
    unix_ms = int(time.time() * 1000)
    if slug is None:
        chosen_slug = _derive_slug_from_body(body)
    else:
        chosen_slug = _slugify(slug)
    wr_id = f"wr-{unix_ms}-{lane}-{to}-{chosen_slug}"
    md_path = (root / "messages" / f"{wr_id}.md").resolve()
    fm: dict[str, Any] = {
        "wr_id": wr_id,
        "from": lane,
        "to": to,
        "status": "open",
        "registered_at": _now_iso(),
    }
    if related_to is not None:
        fm["related_to"] = related_to
    _write_md(md_path, fm, body)

    inbox_log = root / "inbox" / f"{to}.log"
    inbox_log.parent.mkdir(parents=True, exist_ok=True)
    line = f"notify wr_id={wr_id} from={lane} path={md_path}\n"
    with open(inbox_log, "a", encoding="utf-8") as f:
        f.write(line)

    return {"wr_id": wr_id, "path": str(md_path)}


@mcp.tool()
def wr_read(wr_id: str) -> dict[str, Any]:
    """Read a WR by id. Returns its frontmatter, body, and absolute path."""
    _, root = _require_session()
    path = (root / "messages" / f"{wr_id}.md").resolve()
    if not path.is_file():
        raise FileNotFoundError(wr_id)
    fm, body = _read_md(path)
    return {"frontmatter": fm, "body": body, "path": str(path)}


@mcp.tool()
def wr_complete(wr_id: str, note: str | None = None) -> dict[str, str]:
    """Mark a WR as completed. Only the recipient lane may call this."""
    lane, root = _require_session()
    path = (root / "messages" / f"{wr_id}.md").resolve()
    if not path.is_file():
        raise FileNotFoundError(wr_id)
    fm, body = _read_md(path)
    if fm.get("to") != lane:
        raise NotRecipientError(
            f"only recipient {fm.get('to')!r} may complete this WR; "
            f"current lane is {lane!r}"
        )
    fm["status"] = "completed"
    fm["completed_at"] = _now_iso()
    if note is not None:
        fm["completed_note"] = note
    _write_md(path, fm, body)
    return {"wr_id": wr_id, "status": "completed"}


def _iter_message_frontmatters(root: Path):
    """Yield (path, frontmatter) for each well-formed *.md under root/messages/."""
    msg_dir = root / "messages"
    for p in sorted(msg_dir.glob("*.md")):
        try:
            fm, _ = _read_md(p)
        except (ValueError, OSError):
            continue
        yield p, fm


@mcp.tool()
def wr_list_open() -> list[dict[str, str]]:
    """List open WRs addressed to the current lane, sorted by registered_at."""
    lane, root = _require_session()
    out: list[dict[str, str]] = []
    for p, fm in _iter_message_frontmatters(root):
        if fm.get("to") == lane and fm.get("status") == "open":
            out.append({
                "wr_id": str(fm.get("wr_id", "")),
                "from": str(fm.get("from", "")),
                "registered_at": str(fm.get("registered_at", "")),
                "path": str(p.resolve()),
            })
    out.sort(key=lambda e: e["registered_at"])
    return out


@mcp.tool()
def wr_info() -> dict[str, Any]:
    """Return current session status: lane, root, inbox path, and open counts."""
    lane, root = _require_session()
    sent_open = 0
    received_open = 0
    for _, fm in _iter_message_frontmatters(root):
        if fm.get("status") != "open":
            continue
        if fm.get("from") == lane:
            sent_open += 1
        if fm.get("to") == lane:
            received_open += 1
    return {
        "lane": lane,
        "root": str(root),
        "inbox": str(root / "inbox" / f"{lane}.log"),
        "sent_open": sent_open,
        "received_open": received_open,
    }


def main() -> None:
    """Entry point for the `wr-mcp` console script. Runs over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
