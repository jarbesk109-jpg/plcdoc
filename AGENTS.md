# PLCdoc — Agent Instructions

**PLCdoc — Documentation and version diff for PLC projects.**
Reads PLCopen XML exports and generates an I/O table, a variable cross-reference
and a program tree (Markdown/Excel export), plus a side-by-side diff between two versions.

## Before you start
1. Read `docs/decisions.md`.
2. If `.local/PLAN.md` exists, read it. It holds the milestone plan and current status.
3. Work on exactly one milestone per session. Do not start the next one unasked.

## Architecture
- `plcdoc/` — core Python library (parsing, docs, diff). No web code here.
- `backend/` — FastAPI, a thin wrapper around the core library.
- `frontend/` — React.
- `samples/` — real PLCopen XML files exported from CODESYS. Used by tests and by the web demo.
- `tests/` — pytest.

## Rules
- Write the parser against the real files in `samples/`, never against assumptions about the format.
- Never change the agreed plan silently. Propose the change, explain why, and wait for approval.
- Every feature ships with tests. Run `pytest` before finishing. Never finish with failing tests.
- No UI polish while core tests are failing.
- Commit messages: `feat:`, `fix:`, `test:`, `docs:`, `chore:`.
- Record any non-obvious technical decision in `docs/decisions.md` (what, why, alternatives).
- Before ending a session: commit all work, and update the handoff in `.local/STATE.md` if it exists
  (rewrite only Verified state, Done and Next; Decisions and Known issues are append-only; never commit in `.local/`).
  `.local/PLAN.md` is human-owned and read-only for agents: never edit it.
  Another agent (Claude Code or Codex) may continue from where you stop.
