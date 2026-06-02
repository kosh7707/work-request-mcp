"""wr-mcp server: MCP tools for inter-session WR messaging."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from filelock import FileLock
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("wr-mcp")


class NotRecipientError(PermissionError):
    """Raised when a non-recipient tries to complete a WR."""


class LaneClaimedError(RuntimeError):
    """Raised when a lane is already held by another live process."""


_SLUG_RE = re.compile(r"[^a-z0-9]+")
_MAX_SLUG_LEN = 50

_lane: str | None = None
_root: Path | None = None

# One cached FileLock instance per root. filelock is NOT reentrant across two
# separate instances on the same path within one process, so reuse one.
_root_locks: dict[str, FileLock] = {}


def _rootlock(root: Path) -> FileLock:
    key = str(root)
    lock = _root_locks.get(key)
    if lock is None:
        lock = FileLock(str(root / ".wr.lock"))
        _root_locks[key] = lock
    return lock


def _pid_alive(pid: int) -> bool:
    """True if a process with `pid` exists. Cross-platform.

    POSIX uses signal 0 as a non-destructive liveness probe. On Windows
    `os.kill(pid, 0)` is destructive, so probe via a read-only process handle.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        return _pid_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _pid_alive_windows(pid: int) -> bool:  # pragma: no cover - POSIX CI
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return code.value == STILL_ACTIVE
        return False
    finally:
        kernel32.CloseHandle(handle)


def _claim_path(root: Path, lane: str) -> Path:
    return root / "inbox" / f"{lane}.claim"


def _inbox_log(root: Path, lane: str) -> Path:
    return root / "inbox" / f"{lane}.log"


def _read_claim(path: Path) -> dict:
    """Parse a .claim file's JSON, returning {} on missing/corrupt content."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _claim_alive(data: dict) -> bool:
    """True if the claim's pid is set and that process is alive."""
    pid = data.get("pid")
    return bool(pid) and _pid_alive(pid)


def _reset_for_tests() -> None:
    global _lane, _root
    _lane = None
    _root = None
    _root_locks.clear()


def _slugify(text: str) -> str:
    s = text.lower().lstrip("#").strip()
    s = _SLUG_RE.sub("-", s).strip("-")
    s = s[:_MAX_SLUG_LEN]
    return s or "untitled"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_text(path: Path, text: str, suffix: str = "") -> None:
    """Write `text` via a temp file + os.replace so a concurrent reader never
    sees a truncated/partial file (rename is a single atomic operation)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=suffix)
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


def _write_md(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    """Atomically write a markdown file with YAML frontmatter.

    None-valued frontmatter keys are omitted on write.
    """
    fm = {k: v for k, v in frontmatter.items() if v is not None}
    front = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
    text = f"---\n{front}---\n{body}"
    _atomic_write_text(Path(path), text, suffix=".md")


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
def wr_register(lane: str, root: str, force: bool = False) -> dict[str, Any]:
    """Register this session as a WR lane.

    Creates `<root>/messages/` and `<root>/inbox/` directories, touches the
    inbox log file for the given lane (without truncating it), and stores
    `lane` and `root` in module-level state for use by other tools.

    Claims the lane by writing `<root>/inbox/<lane>.claim` ({pid, at}). If the
    lane is already claimed by a *different live* process, raises
    `LaneClaimedError` unless `force=True` (steal). A claim held by a dead pid
    is stolen automatically, so a crashed session never locks the lane.

    Returns a `monitor_cmd` field that the calling skill should pass verbatim
    to the Claude Code `Monitor` tool. The command spawns a cross-platform
    tail process (Python-based) so the SKILL does not depend on shell
    coreutils — works on Linux, macOS, and Windows alike. The returned
    `previous_lane` is the lane this session held before (None on first call)
    so the skill can stop a stale Monitor when switching lanes.
    """
    global _lane, _root
    prev = _lane
    root_path = Path(root).expanduser().resolve()
    (root_path / "messages").mkdir(parents=True, exist_ok=True)
    (root_path / "inbox").mkdir(parents=True, exist_ok=True)
    inbox_log = _inbox_log(root_path, lane)
    inbox_log.touch(exist_ok=True)
    claim_path = _claim_path(root_path, lane)
    me = os.getpid()
    with _rootlock(root_path):
        if claim_path.exists():
            data = _read_claim(claim_path)
            other = data.get("pid")
            if other and other != me and _pid_alive(other) and not force:
                raise LaneClaimedError(
                    f"lane {lane!r} already held by pid {other} since "
                    f"{data.get('at')}. stop it, pick another lane, or "
                    f"wr_register(force=True) to steal."
                )
        # temp suffix is .tmp (NOT .claim) so the in-flight temp file is never
        # matched by _peer_claims' inbox/*.claim glob.
        _atomic_write_text(
            claim_path,
            json.dumps({"pid": me, "at": _now_iso()}),
            suffix=".tmp",
        )
    _lane = lane
    _root = root_path
    monitor_cmd = f'"{sys.executable}" -m wr_mcp.tailer "{inbox_log}"'
    return {
        "lane": lane,
        "root": str(root_path),
        "inbox": str(inbox_log),
        "monitor_cmd": monitor_cmd,
        "previous_lane": prev,
    }


@mcp.tool()
def wr_unregister() -> dict[str, Any]:
    """Release the current lane and clear this session's state.

    Removes this session's own `inbox/<lane>.claim` — but only if it is still
    held by THIS process (pid match), so a lane already stolen by another live
    session is left intact. The inbox log and all messages are preserved
    (durable history). Returns `released=True` only when our claim was removed.
    """
    global _lane, _root
    lane, root = _require_session()
    me = os.getpid()
    claim_path = _claim_path(root, lane)
    released = False
    with _rootlock(root):
        if claim_path.exists():
            data = _read_claim(claim_path)
            if data.get("pid") == me:
                claim_path.unlink()
                released = True
    result = {"lane": lane, "root": str(root), "released": released}
    _lane = None
    _root = None
    return result


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

    # Recipient must have an inbox (i.e. have registered) before we can send.
    # Without this, open(..., "a") silently creates a log nobody reads, so a
    # typo'd or never-registered lane swallows the WR with no error.
    inbox_log = _inbox_log(root, to)
    if not inbox_log.exists():
        existing = sorted(p.stem for p in (root / "inbox").glob("*.log"))
        raise ValueError(
            f"cannot send to lane {to!r}: no inbox (never registered). "
            f"registered lanes: {existing}"
        )

    # Online-awareness (soft): a KNOWN-but-offline recipient is NOT an error — the WR is
    # queued and read when it re-registers (mailbox semantics). We surface its liveness so
    # the sender knows, but never block on it. (Only the unknown-lane guard above is hard.)
    recipient_online = _lane_online(root, to)

    body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    chosen_slug = _derive_slug_from_body(body) if slug is None else _slugify(slug)
    with _rootlock(root):
        # Dedup: an identical still-open WR (same from/to/related_to/body) means
        # a retry or accidental double-send — return the existing one instead of
        # spawning a duplicate the recipient would see twice.
        for p, fm_existing in _iter_message_frontmatters(root):
            if (
                fm_existing.get("from") == lane
                and fm_existing.get("to") == to
                and fm_existing.get("status") == "open"
                and fm_existing.get("related_to") == related_to
                and fm_existing.get("body_sha256") == body_sha
            ):
                return {
                    "wr_id": str(fm_existing.get("wr_id", "")),
                    "path": str(p.resolve()),
                    "dedup": True,
                    "recipient_online": recipient_online,
                }

        unix_ms = int(time.time() * 1000)
        wr_id = f"wr-{unix_ms}-{lane}-{to}-{chosen_slug}"
        md_path = (root / "messages" / f"{wr_id}.md").resolve()
        # Avoid id collision: two sends in the same ms to the same target+slug
        # would otherwise produce an identical wr_id and os.replace would
        # silently overwrite the first file while both notify lines append.
        while md_path.exists():
            unix_ms += 1
            wr_id = f"wr-{unix_ms}-{lane}-{to}-{chosen_slug}"
            md_path = (root / "messages" / f"{wr_id}.md").resolve()

        fm: dict[str, Any] = {
            "wr_id": wr_id,
            "from": lane,
            "to": to,
            "status": "open",
            "registered_at": _now_iso(),
            "body_sha256": body_sha,
        }
        if related_to is not None:
            fm["related_to"] = related_to
        _write_md(md_path, fm, body)

        line = f"notify wr_id={wr_id} from={lane} path={md_path}\n"
        with open(inbox_log, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    result = {"wr_id": wr_id, "path": str(md_path), "recipient_online": recipient_online}
    if not recipient_online:
        result["warning"] = (
            f"lane {to!r} is offline (no live claim); WR is queued and will be "
            f"delivered when it re-registers"
        )
    return result


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
    with _rootlock(root):
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


def _lane_online(root: Path, lane: str) -> bool:
    """True if `lane` currently holds a live claim (registered AND its pid is alive)."""
    return _claim_alive(_read_claim(_claim_path(root, lane)))


def _lane_status(root: Path, self_lane: str) -> list[dict[str, Any]]:
    """Every lane KNOWN under this root (registered at least once = has an inbox log),
    each with its online status. `online` = the lane holds a live claim. A known-but-
    offline lane still receives WRs (mailbox semantics); only an UNKNOWN lane (no inbox
    log) is rejected by wr_send. Sorted by lane name."""
    claims: dict[str, dict] = {
        p.stem: _read_claim(p) for p in (root / "inbox").glob("*.claim")
    }
    out: list[dict[str, Any]] = []
    for log in sorted((root / "inbox").glob("*.log")):
        ln = log.stem
        data = claims.get(ln, {})
        pid = data.get("pid")
        out.append({
            "lane": ln,
            "online": _claim_alive(data),
            "pid": pid,
            "since": data.get("at"),
            "is_self": ln == self_lane,
        })
    return out


def _peer_claims(root: Path, self_lane: str) -> list[dict[str, Any]]:
    """Liveness of other lanes registered under this root, from their .claim files.

    Each lane's claim records the pid that holds it; `_pid_alive` says whether
    that process is still up. Lets a session see whether a peer it wants to talk
    to (or that may be racing its lane) is actually live.
    """
    peers: list[dict[str, Any]] = []
    for p in sorted((root / "inbox").glob("*.claim")):
        if p.stem == self_lane:
            continue
        data = _read_claim(p)
        peers.append({
            "lane": p.stem,
            "pid": data.get("pid"),
            "alive": _claim_alive(data),
            "at": data.get("at"),
        })
    return peers


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
        "inbox": str(_inbox_log(root, lane)),
        "sent_open": sent_open,
        "received_open": received_open,
        "peers": _peer_claims(root, lane),
    }


@mcp.tool()
def wr_lanes() -> dict[str, Any]:
    """List every lane KNOWN under this root (registered at least once) with online status.

    Lets a sender check reachability before sending. `online` = the lane holds a live claim
    now. A known-but-offline lane is NOT an error: a WR sent to it is queued and delivered
    when it re-registers (mailbox semantics). wr_send rejects only UNKNOWN lanes (never
    registered) — the common typo guard — and warns (without blocking) for offline ones.

    Returns `online` (the reachable-now lane names) and `lanes` (every known lane with
    {lane, online, pid, since, is_self}).
    """
    lane, root = _require_session()
    lanes = _lane_status(root, lane)
    return {
        "lane": lane,
        "root": str(root),
        "online": [entry["lane"] for entry in lanes if entry["online"]],
        "lanes": lanes,
    }


def main() -> None:
    """Entry point for the `wr-mcp` console script. Runs over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
