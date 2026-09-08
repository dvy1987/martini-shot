---
name: Replit configuration validation
description: Safe workflow for changing deployment settings in this workspace.
---

Direct edits to `.replit` are blocked by the workspace guard. Write the candidate TOML to a temporary file and pass its absolute path to `verifyAndReplaceDotReplit`; the validator replaces the live config only when the schema is valid.

**Why:** Deployment configuration changes should be schema-checked before they affect workflows or publishing.

**How to apply:** Use this flow for future `.replit` changes instead of editing the file directly.