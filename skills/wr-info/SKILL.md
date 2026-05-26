---
name: wr-info
description: Show current WR session status (lane, root, inbox path, and open WR counts). Trigger when the user types /wr-info.
---

# wr-info — WR session status

## Steps

1. Call the MCP tool `wr_info()`.
2. Pretty-print the result as:

   ```
   Lane:           <lane>
   Root:           <root>
   Inbox log:      <inbox>
   Open (sent):    <sent_open>
   Open (received): <received_open>
   ```

3. **If `received_open > 0`**, also call `wr_list_open()` and append:

   ```
   --- open inbound WRs ---
   <wr_id>  from=<from>  registered_at=<registered_at>
   ...
   ```

4. **If `wr_info()` raises `RuntimeError`** (session not registered yet),
   tell the user to run `/wr-init <lane>` first.
