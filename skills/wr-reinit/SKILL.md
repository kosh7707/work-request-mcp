---
name: wr-reinit
description: Re-initialize a WR session lane after a resume or lane switch. Stops the stale inbox Monitor, steals the lane's own claim, restarts the tailer, and catches up on WRs missed while the tailer was detached. Trigger when the user types /wr-reinit [<lane>] [<root>], on session resume, or when /wr-init reports the lane is already claimed.
argument-hint: "[<lane>] [<root>]"
---

# wr-reinit — recover a WR session lane

Use this when the inbox Monitor may have detached but the lane is still "yours":
after a Claude Code **resume**, after switching lanes, or when `/wr-init` raised
`LaneClaimedError` because a stale claim from a previous (crashed or resumed)
process is still on disk.

> Key model: the notify log is **best-effort live** delivery, not a durable
> queue. The tailer only sees lines appended *after* it attaches, so anything
> sent while it was detached is invisible to it. `wr_list_open()` reads the
> **disk truth** and is the only reliable catch-up. This skill always runs it.

## Arguments

`$ARGUMENTS` has 0–2 tokens. Reuse the current session's lane/root when omitted:

- **lane** (optional): defaults to the lane from the active session (`wr_info()`).
- **root** (optional): defaults to the root from the active session.

If neither is known (no prior `/wr-init` this session), tell the user to run
`/wr-init <lane> [<root>]` instead and stop.

## Steps (execute in this order)

1. Determine `lane` and `root`. Prefer `$ARGUMENTS`. If a token is missing,
   call `wr_info()` to recover it — but `wr_info()` raises `RuntimeError` when
   no session is registered yet this process. If that happens and `lane` is
   still unknown, stop and tell the user to run `/wr-init <lane> [<root>]`.

2. **Stop the stale Monitor.** If a previous `wr-init`/`wr-reinit` in this
   session started a persistent Monitor for this lane, stop it (TaskStop on
   that Monitor task) so you don't end up with two tailers on one inbox.

3. Call `wr_register(lane=<lane>, root=<root>, force=True)`. `force=True` steals
   this lane's own stale claim left by the detached/previous process. (A claim
   held by a *dead* pid is stolen automatically even without `force`; `force`
   covers the case where the old pid still looks alive after a resume.)
   Record `inbox` and `monitor_cmd` from the response. Note `previous_lane`:
   if it is set and differs from `<lane>`, also stop that lane's old Monitor.

4. Start a fresh **Monitor** with the returned `monitor_cmd` (verbatim),
   `persistent: true`, `description: WR inbox lane=<lane>`,
   `timeout_ms: 3600000`.

5. **Catch up.** Call `wr_list_open()` and present every open inbound WR —
   these include anything that arrived while the tailer was detached and would
   otherwise be lost. For each: `<wr_id> from=<from> registered_at=<registered_at>`.

6. Report: `WR session re-initialized. lane=<lane> root=<root> inbox=<inbox> open=<N>`.

## Behavioral rules

The send / receive / status rules are identical to `/wr-init` — see that skill.
The only difference here is recovery: **always** finish with a `wr_list_open()`
catch-up, because the tailer cannot replay what it missed.
