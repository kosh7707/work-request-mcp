---
name: wr-init
description: Initialize a WR (work-request) session lane. Registers the lane with wr-mcp, starts a cross-platform tailer Monitor on the inbox log, and lists any open inbound WRs. Trigger when the user types /wr-init <lane> [<root>].
argument-hint: "<lane> [<root>]"
---

# wr-init — initialize WR session

## Arguments

`$ARGUMENTS` contains 1 or 2 tokens:

- **lane** (required): short identifier like `s1`, `s2`, etc.
- **root** (optional): absolute filesystem path under which `messages/` and
  `inbox/` directories live.

## Steps (execute in this order)

1. Parse `$ARGUMENTS`. First whitespace-separated token is `lane`, second (if
   present) is `root`.

2. **If `root` is missing**, invoke `AskUserQuestion` with three options:
   - `$PWD/wrs` (recommended) — per-project isolation
   - `~/wrs` — global single root across all projects
   - `Other` — free-text input

   `wr_register` resolves `~` and relative paths server-side, so you can pass
   the chosen value through as-is **except for `$PWD`**: the shell variable
   is not expanded server-side, so substitute it with the Claude Code working
   directory yourself before calling the tool.

3. Call the MCP tool `wr_register(lane=<lane>, root=<root>)`. Record the
   returned `inbox` path and `monitor_cmd` string.

   > If this raises `LaneClaimedError`, another live process already holds the
   > lane. Do **not** force it blindly — either pick a different lane, or, if
   > you know this is your own session resuming after a detach, run
   > `/wr-reinit <lane>` (it steals the stale claim and catches up on missed
   > WRs).

4. Call the **Monitor** tool with:
   - `command`: the `monitor_cmd` value from the `wr_register` response,
     passed verbatim. (It runs a Python-based tailer that works identically
     on Linux, macOS, and Windows — do not substitute `tail -F` or any
     shell-specific variant.)
   - `persistent`: `true`
   - `description`: `WR inbox lane=<lane>`
   - `timeout_ms`: `3600000` (1 hour; can be longer if `persistent` is true)

5. Call `wr_list_open()`. If non-empty, list each entry compactly:
   `<wr_id> from=<from> registered_at=<registered_at>`.

6. Report to the user:
   `WR session ready. lane=<lane> root=<root> inbox=<inbox> open=<N>`.

## Behavioral rules for the rest of this session

Apply these rules until the session ends or the user explicitly switches
lanes by calling `/wr-init` again.

### On Monitor inbox events

Each Monitor event is a single line. When the line matches the regex
`^notify wr_id=(\S+) from=(\S+) path=(.+)$`:

> `path` is the **last field** on the line and may contain spaces if `<root>`
> does. Capture with `(.+)$`, not `\S+`.

1. Extract `wr_id`, `from_lane`, `path`.
2. Call `wr_read(wr_id)` to load the full WR.
3. Present a short summary to the user: from, registered_at, first
   paragraph of body. Offer the full body if the user wants it.
4. Completing a WR is your autonomous judgment: when the ask is resolved
   (whether by a user resolution like "tell them yes" / "we already did
   that", or by work you carried out), compose a short note and call
   `wr_complete(wr_id, note=<summary of resolution>)`.

### On natural-language send requests

When the user says something like "send a WR to s2 asking X" or "WR s7:
please look at Y":

1. Identify the target lane.
2. Compose the body as markdown (start with a `# Title` heading that
   captures the ask).
3. Call `wr_send(to=<lane>, body=<markdown>, related_to=<prior_wr_id_if_reply>)`.
4. Report the returned `wr_id` and `path` back to the user.

### On status requests

When the user asks "what's open" or "WR status", call `wr_info()` (or use
the `/wr-info` skill) and present the result.

### Never

- Do **not** call `wr_register` again in this session unless the user
  explicitly switches lanes.
- Do **not** broadcast: WRs are 1:1 only. If the user wants several
  recipients, send N separate WRs.
