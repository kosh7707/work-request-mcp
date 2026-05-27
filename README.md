# wr-mcp

MCP server for inter-session **Work Request (WR)** messaging in Claude Code.

Each Claude Code session registers itself as a *lane* (e.g. `s1`, `s2`).
Sessions exchange WRs (markdown files with YAML frontmatter) through a shared
on-disk root. Recipients detect inbound WRs by tailing a per-lane inbox log
with Claude Code's built-in `Monitor` tool — no human in the loop.

## TL;DR

1. `git clone https://github.com/kosh7707/work-request-mcp.git && cd work-request-mcp`
2. Create a venv and `pip install -e '.[dev]'`
3. `claude mcp add wr-mcp -s user -- <absolute path to the installed wr-mcp binary>`
4. Copy `skills/wr-init/SKILL.md` and `skills/wr-info/SKILL.md` into
   `~/.claude/skills/<name>/SKILL.md`
5. **Restart Claude Code.**
6. In every session you want to participate, run `/wr-init <lane> <shared-root>`
7. From any session: ask Claude in plain language to "send a WR to `<other lane>`: ...".
   Recipients react automatically.

Full step-by-step setup with verify commands is below.

## Why

You already do this manually: open multiple Claude Code sessions, tell one to
write a WR, tell another to read it. `wr-mcp` automates the routing so the
sessions handle the back-and-forth themselves while keeping every message as a
durable markdown file you can audit later.

## Architecture

```
session s1                wr-mcp (per session)            shared <root>/
─────────                 ──────────────────              ──────────────
  /wr-init s1   ─────►    wr_register(lane, root) ───►    messages/
  "send WR     ─────►     wr_send(to, body)        ───►     wr-<ms>-s1-s2-<slug>.md
   to s2: ..."                                      ───►    inbox/
                                                            s2.log  (notify line appended)

session s2
─────────
  Monitor: python tailer streams new lines from inbox/s2.log
  notify line   ─────►    wr_read(wr_id)           ───►    (loads md)
  "complete it" ─────►    wr_complete(wr_id, note) ───►    (md status=completed)
```

- 1:1 messaging only. To broadcast, send N individual WRs.
- WR body is markdown. Frontmatter is YAML.
- Inbox log is append-only; each line is `notify wr_id=<id> from=<lane> path=<abs>`.
- The Monitor command is supplied by `wr_register` as a `monitor_cmd` field
  — a pure-Python tailer that works on Linux, macOS, and Windows without
  any extra dependencies.

## Prerequisites

- **Python 3.10 or newer** (`python --version` / `python3 --version`)
- **git**
- **Claude Code** with the `claude` CLI on your `PATH`
- Either Linux, macOS, or Windows. No WSL, Cygwin, or Git Bash required.

## Setup

> **Important:** Claude Code only loads MCP servers and SKILLs at session
> startup. You must restart any running Claude Code session **after** each of
> the registration steps below for the new tools/skills to appear.

### Step 1 — Clone and install (one-time)

**Linux / macOS:**

```bash
git clone https://github.com/kosh7707/work-request-mcp.git
cd work-request-mcp
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

**Windows (PowerShell):**

```powershell
git clone https://github.com/kosh7707/work-request-mcp.git
cd work-request-mcp
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
```

Verify the binary exists and the test suite is green:

| OS | Command |
|----|---------|
| Linux / macOS | `.venv/bin/pytest -v` |
| Windows | `.\.venv\Scripts\pytest.exe -v` |

Expected: all tests pass.

Record the **absolute path** to the `wr-mcp` binary — you need it in Step 2.

| OS | Path |
|----|------|
| Linux / macOS | `<repo>/.venv/bin/wr-mcp` |
| Windows | `<repo>\.venv\Scripts\wr-mcp.exe` |

### Step 2 — Register the MCP server (global user scope)

**Linux / macOS:**

```bash
claude mcp add wr-mcp -s user -- /absolute/path/to/work-request-mcp/.venv/bin/wr-mcp
```

**Windows (PowerShell):**

```powershell
claude mcp add wr-mcp -s user -- "C:\absolute\path\to\work-request-mcp\.venv\Scripts\wr-mcp.exe"
```

If your `claude` CLI version doesn't support `-s user`, hand-edit
`~/.claude.json` (or `%USERPROFILE%\.claude.json` on Windows) and add
`wr-mcp` under the top-level `mcpServers` key:

```json
{
  "mcpServers": {
    "wr-mcp": {
      "command": "/absolute/path/to/work-request-mcp/.venv/bin/wr-mcp"
    }
  }
}
```

Confirm registration:

```bash
claude mcp list
```

Look for a line containing `wr-mcp` in the output. On Linux / macOS you can
filter with `claude mcp list | grep wr-mcp`; on Windows PowerShell, use
`claude mcp list | Select-String wr-mcp`.

### Step 3 — Install the two helper SKILLs (global)

**Linux / macOS:**

```bash
mkdir -p ~/.claude/skills/wr-init ~/.claude/skills/wr-info
cp skills/wr-init/SKILL.md ~/.claude/skills/wr-init/SKILL.md
cp skills/wr-info/SKILL.md ~/.claude/skills/wr-info/SKILL.md
```

**Windows (PowerShell):**

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\skills\wr-init" | Out-Null
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\skills\wr-info" | Out-Null
Copy-Item skills\wr-init\SKILL.md "$env:USERPROFILE\.claude\skills\wr-init\SKILL.md"
Copy-Item skills\wr-info\SKILL.md "$env:USERPROFILE\.claude\skills\wr-info\SKILL.md"
```

Verify both files are in place. On Linux / macOS:

```bash
ls ~/.claude/skills/wr-init/SKILL.md ~/.claude/skills/wr-info/SKILL.md
```

On Windows:

```powershell
Get-Item "$env:USERPROFILE\.claude\skills\wr-init\SKILL.md", "$env:USERPROFILE\.claude\skills\wr-info\SKILL.md"
```

### Step 4 — Restart Claude Code

**Close all Claude Code sessions and start a fresh one.** This is the step
people forget. MCP servers and SKILLs registered above will not appear in
any session that was already running.

In the new session, confirm both are loaded:

- The 6 `mcp__wr-mcp__wr_*` tools should be listed when you ask Claude what
  MCP tools are available.
- `/wr-init` and `/wr-info` should appear as slash commands.

### Step 5 — Initialize the session

```
/wr-init <lane> [<root>]
```

- `<lane>` is the short identifier this session will use (e.g. `s1`, `s2`).
- `<root>` is the directory under which WRs are stored. If omitted, the skill
  asks you to choose between `$PWD/wrs` (per-project), `~/wrs` (global), or
  a custom path.

The skill registers the lane, starts a persistent Monitor running a
Python-based cross-platform tailer (`python -m wr_mcp.tailer <inbox>`) on
the inbox log, lists any open WRs you've received, and reports the session
status. After this, `/wr-info` shows the current state at any time.

> Cross-platform note: the tailer is pure Python so the SKILL is identical
> on Linux, macOS, and Windows. You do **not** need Git Bash, WSL, or any
> Unix coreutils.

## Tools

| Tool | Signature | Notes |
|------|-----------|-------|
| `wr_register` | `(lane: str, root: str)` | Session init. Idempotent. |
| `wr_send` | `(to: str, body: str, slug?: str, related_to?: str)` | Writes md + appends notify line. |
| `wr_read` | `(wr_id: str)` | Returns `{frontmatter, body, path}`. |
| `wr_complete` | `(wr_id: str, note?: str)` | Recipient-only. Raises `NotRecipientError` otherwise. |
| `wr_list_open` | `()` | Open WRs **addressed to current lane**, sorted by `registered_at`. |
| `wr_info` | `()` | `{lane, root, inbox, sent_open, received_open}` |

## File layout under `<root>/`

```
<root>/
├── messages/
│   └── wr-<unix_ms>-<from>-<to>-<slug>.md
└── inbox/
    └── <lane>.log      # append-only, one notify line per WR
```

### WR md frontmatter

```yaml
wr_id: wr-<unix_ms>-<from>-<to>-<slug>
from: s1
to: s2
status: open            # or completed
registered_at: 2026-05-26T15:00:00.123456+00:00
completed_at: <iso>?    # only when completed
related_to: <wr_id>?    # optional reply linkage
completed_note: <str>?  # optional
```

## 2-session demo

Pick a shared root path both sessions can reach. Example below uses
`/tmp/wrs-demo` (Linux / macOS) or `C:\Temp\wrs-demo` (Windows).

In **session A** (a fresh Claude Code, opened in any working directory):

```
/wr-init s1 /tmp/wrs-demo
```

Expected: a "WR session ready" line naming the lane, root, inbox, and open
count (`0` on first run).

In **session B** (a different Claude Code window — can be in any working
directory; it does not need to be the same as session A's), use the
**same root**:

```
/wr-init s2 /tmp/wrs-demo
```

In A:

```
send a WR to s2: please review src/foo.py
```

Session A returns the `wr_id`. Session B's Monitor immediately emits a
`notify ...` event; B reads the WR, presents it, and after the human (or B's
autonomous logic) resolves it, calls `wr_complete`.

In A:

```
/wr-info
```

Shows `sent_open: 0` once B has completed the WR.

## Troubleshooting

**`/wr-init` says the skill isn't found.**
SKILL files weren't installed, or Claude Code wasn't restarted after copying
them. Re-do Step 3 + Step 4.

**Claude says the `wr_*` tools don't exist, or `/wr-init` fails on
`wr_register`.**
MCP server isn't registered, or Claude Code wasn't restarted after `claude
mcp add`. Run `claude mcp list` and look for `wr-mcp` in the output (on
Windows PowerShell use `claude mcp list | Select-String wr-mcp`). If
absent, redo Step 2. If present, restart Claude Code (Step 4).

**`claude mcp add` worked, but starting a fresh session still shows nothing.**
You likely passed a relative path to `claude mcp add`. The path must be
absolute (e.g. `/home/you/work-request-mcp/.venv/bin/wr-mcp`). Re-register
with the absolute path. `claude mcp remove wr-mcp -s user` first if you
need to clear the old entry.

**`wr_send` from session A succeeds, but session B never reacts.**
Check that B's `/wr-init` was run with the **same `<root>`** as A. The lanes
only see each other if they share a root directory. Confirm with `/wr-info`
in both sessions — `root` and `inbox` paths should both point inside the
same root.

**`pytest` fails on `mcp.server.fastmcp` import.**
Wrong Python environment. Use the venv's pytest, not the system `pytest`:
- Linux / macOS: `.venv/bin/pytest`
- Windows: `.\.venv\Scripts\pytest.exe`

**`python` is not recognized / pip fails on install.**
Check `python --version` returns 3.10 or newer. On Linux / macOS the
executable may be `python3`. On Windows install Python from python.org or
the Microsoft Store and make sure "Add to PATH" was checked.

## License

MIT — see [LICENSE](LICENSE).
