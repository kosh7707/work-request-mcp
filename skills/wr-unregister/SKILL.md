---
name: wr-unregister
description: Release the current WR lane. Stops the inbox Monitor, removes this session's own lane claim, and clears session state so the lane is immediately free for another session. Trigger when the user types /wr-unregister, or wants to cleanly hand off / step out of a lane.
---

# wr-unregister — release the current lane

Use this to cleanly step out of a WR lane (e.g. before closing the session, or
to hand the lane to another session) instead of relying on dead-pid detection.

> What it does NOT do: it never deletes the inbox log or any messages — those
> are durable history. It only removes **this session's own** claim. If the
> lane was already stolen by another live session, the claim is left intact.

## Steps

1. **Stop the inbox Monitor.** If this session started a persistent Monitor
   for the lane (via `/wr-init` or `/wr-reinit`), stop it (TaskStop on that
   Monitor task). Skip if none is running.

2. Call the MCP tool `wr_unregister()`. It returns `{lane, root, released}`.
   - `released: true` — your claim was removed; the lane is now free.
   - `released: false` — there was no claim of yours to remove (already gone,
     or held by another process). Session state is cleared either way.

3. **If `wr_unregister()` raises `RuntimeError`** (no session registered this
   process), tell the user there is nothing to release.

4. Report: `WR lane released. lane=<lane> root=<root> released=<true|false>`.

## After this

No further WR sends/reads work until the user runs `/wr-init <lane>` again —
session state has been cleared. To resume the same lane, `/wr-init <lane>`
re-registers cleanly (the freed claim no longer blocks it).
