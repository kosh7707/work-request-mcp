# wr-mcp

MCP server for inter-session **Work Request (WR)** messaging in Claude Code.

Each Claude Code session registers itself as a *lane* (e.g. `s1`, `s2`).
Sessions exchange WRs (markdown files with YAML frontmatter) through a shared
on-disk root. Recipients detect inbound WRs by tailing a per-lane inbox log
with Claude Code's built-in `Monitor` tool — no human in the loop.

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
  Monitor: tail -F inbox/s2.log
  notify line   ─────►    wr_read(wr_id)           ───►    (loads md)
  "complete it" ─────►    wr_complete(wr_id, note) ───►    (md status=completed)
```

- 1:1 messaging only. To broadcast, send N individual WRs.
- WR body is markdown. Frontmatter is YAML.
- Inbox log is append-only; each line is `notify wr_id=<id> from=<lane> path=<abs>`.

## Install

```bash
git clone https://github.com/kosh7707/work-request-mcp.git
cd work-request-mcp
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

Verify the test suite:

```bash
.venv/bin/pytest -v
```

## Register with Claude Code (global user scope)

```bash
claude mcp add wr-mcp -s user -- /absolute/path/to/work-request-mcp/.venv/bin/wr-mcp
```

If your `claude` CLI version doesn't support `-s user`, hand-edit
`~/.claude.json` and add:

```json
{
  "mcpServers": {
    "wr-mcp": {
      "command": "/absolute/path/to/work-request-mcp/.venv/bin/wr-mcp"
    }
  }
}
```

Confirm:

```bash
claude mcp list | grep wr-mcp
```

## Install the helper skills

Two skills make the session-level wiring deterministic:

```bash
mkdir -p ~/.claude/skills/wr-init ~/.claude/skills/wr-info
# Copy the SKILL.md files from this repo's skills/ directory:
cp skills/wr-init/SKILL.md ~/.claude/skills/wr-init/SKILL.md
cp skills/wr-info/SKILL.md ~/.claude/skills/wr-info/SKILL.md
```

After this, every Claude Code session can invoke:

- `/wr-init <lane> [<root>]` — registers the lane, starts a `tail -F` Monitor
  on the inbox log, and lists any open inbound WRs.
- `/wr-info` — prints lane / root / inbox / counts.

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

In **session A** (a fresh Claude Code in some project):

```
/wr-init s1 /tmp/wrs-demo
```

Expected: `Lane s1 registered. Root /tmp/wrs-demo. Open WRs: 0`.

In **session B** (different Claude Code, can be different project):

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

## License

MIT — see [LICENSE](LICENSE).
