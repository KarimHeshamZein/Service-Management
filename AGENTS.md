# AGENTS.md

This repository's authoritative agent instructions and current-session handoff
are in `CLAUDE.md`. Read that file completely before investigating or changing
anything, then read `README.md` for architecture and operating procedures.

Key rules for Codex:

- Investigate and report a concrete plan before editing. Wait for the user's
  explicit confirmation unless the user has already directly authorized the
  implementation.
- Preserve the user's dirty worktree and all external installation data. Never
  modify `.env`, development/deployed databases, uploads, Windows services, or
  `D:\ServiceManagement` without explicit permission.
- Use `apply_patch` for source edits, Alembic for schema changes, and focused plus
  proportionate regression tests. Installer changes require a repeatable
  end-to-end repair/install test before packaging.
- Do not stage the unrelated untracked root `index.html` unless the user says it
  belongs to this application.
- The latest handoff status, RC artifact details, test result, and resume
  checklist are at the top of `CLAUDE.md`.
