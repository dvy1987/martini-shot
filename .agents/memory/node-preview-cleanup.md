---
name: Node preview cleanup
description: Process cleanup for Node smoke checks that launch npm or Vite child processes
---

Smoke checks that launch a package-manager wrapper and its dev server should run the
server in a separate process group and terminate that group in `finally`. Killing
only the npm parent can leave the server alive and make an otherwise successful CI
command hang.

**Why:** npm forwards the preview command to a child process, so terminating the
wrapper alone is not a reliable cleanup boundary.

**How to apply:** Use process-group cleanup for future Node scripts that start local
preview servers; keep a short force-kill timeout as a last resort.