---
name: wr-lanes
description: List every WR lane known under this root and whether each is online now. Trigger when the user types /wr-lanes.
---

# wr-lanes — list known lanes + online status

## Steps

1. Call the MCP tool `wr_lanes()`.
2. Pretty-print the result as:

   ```
   Lane (self):  <lane>
   Root:         <root>
   Online now:   <comma-joined online[]  (or "none")>

   --- known lanes ---
   <lane>  online=<true|false>  since=<since>  <"(self)" if is_self>
   ...
   ```

   Sort the known-lanes block with online lanes first, then by name.

3. Remind the user of the semantics so an offline lane isn't mistaken for an error:
   a **known-but-offline** lane still receives WRs (queued, delivered when it
   re-registers); `wr_send` rejects only an **unknown** lane (never registered =
   likely a typo) and only **warns** for an offline one.

4. **If `wr_lanes()` raises `RuntimeError`** (session not registered yet),
   tell the user to run `/wr-init <lane>` first.
