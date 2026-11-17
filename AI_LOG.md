# AI_LOG.md — ContractGuard

This file records every AI-assisted session on this project: the tool and
model used, the goal, the prompt summary, the output, human corrections, and
decisions made. Required by CLAUDE.md Rule §"Append an entry to AI_LOG.md
at the end of every phase."

---

## Entry 1 — Planning session (Claude chat)

| Field | Value |
|-------|-------|
| **Date** | 2026-11-17 |
| **Tool** | Claude.ai web chat |
| **Model** | Claude (web, model unspecified by user at time of session) |
| **Phase** | Pre-Phase 0 — Project planning |

**Goal:** Define the product idea, write PRD.md, ARCHITECTURE.md,
TECH_STACK.md, and CLAUDE.md to serve as source-of-truth for all subsequent
coding sessions.

**Prompt summary:** User described the concept of a "living contract" auditor
for hackathon submission. Asked Claude to structure the PRD, architecture, and
tech-stack documentation.

**Output:** `PRD.md`, `ARCHITECTURE.md`, `TECH_STACK.md`, `CLAUDE.md`
produced and placed in the repo root.

**Human corrections:** None recorded.

**Decision:** Treat these four docs as immutable source of truth for the
session; any design changes must update the relevant doc in the same commit.

---

## Entry 2 — Phase 0 scaffold (Claude Code, non-Claude model)

| Field | Value |
|-------|-------|
| **Date** | 2026-11-18 (early hours) |
| **Tool** | Claude Code (VS Code extension) |
| **Model** | Non-Claude model (exact name not recorded; noted in task as "Phase 0 in Claude Code using a non-Claude model") |
| **Phase** | Phase 0 — Repo scaffold |

**Goal:** Create the initial repo structure: `pyproject.toml`,
`requirements.txt`, `requirements-dev.txt`, `contractguard/` package skeleton
(all modules except `__init__.py`, `__main__.py`, `cli.py`, `reporter.py`),
`sample-broken-app/`, `tests/`.

**Prompt summary:** Scaffold the ContractGuard repo per ARCHITECTURE.md and
TECH_STACK.md. Do not implement logic; stubs only.

**Output:** `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`,
`contractguard/{models,indexer,triage,fixer,sandbox}.py`,
`contractguard/auditors/{security,drift,slop}.py`, `.venv/` created,
`sample-broken-app/` and `tests/` directories.

**Human corrections:** Noted that `__init__.py`, `__main__.py`, `cli.py`,
`reporter.py`, and `contractguard/auditors/__init__.py` were missing.
Also missing: `.gitignore`, `README.md`, `arena.json`, `AI_LOG.md`,
`AGENTS.md`, `transcripts/`.

**Decision:** Complete the scaffold in the next session (this one) without
overwriting correct existing files.

---

## Entry 3 — Phase 0 completion (Antigravity / Google DeepMind)

| Field | Value |
|-------|-------|
| **Date** | 2026-11-18 |
| **Tool** | Antigravity (Google DeepMind AI assistant, agy) |
| **Model** | Claude Sonnet 4.6 (Thinking) |
| **Phase** | Phase 0 — Scaffold completion |

**Goal:** Complete the repo scaffold without overwriting existing correct
files. Specifically: `.gitignore`, missing `contractguard/` modules
(`__init__.py`, `__main__.py`, `cli.py`, `reporter.py`),
`contractguard/auditors/__init__.py`, `README.md`, `arena.json`, `AI_LOG.md`,
`AGENTS.md` (copy of `CLAUDE.md`), `transcripts/.gitkeep`.

**Prompt summary:** Read all four spec docs, inspect the tree, then create
only the missing files as docstring-only stubs. No logic, no git commands.

**Output (this session):**
- `.gitignore` — covers Python artifacts, venvs, caches, node_modules,
  secrets, tool temp dirs, editor/OS files; explicitly does NOT ignore spec
  docs or `transcripts/`
- `contractguard/__init__.py` — package docstring stub
- `contractguard/__main__.py` — delegates to `cli.cli()`
- `contractguard/cli.py` — command docstring stub (audit / heal / verify)
- `contractguard/reporter.py` — reporter docstring stub
- `contractguard/auditors/__init__.py` — sub-package docstring stub
- `README.md` — project stub with quick-start and feature table
- `arena.json` — hackathon metadata placeholder
- `AI_LOG.md` — this file
- `AGENTS.md` — copied from `CLAUDE.md`
- `transcripts/.gitkeep` — ensures the transcripts/ folder is tracked

**Human corrections:** None yet (session in progress).

**Decision:** Scaffold is now complete. Next phase (Phase 1) will implement
`models.py` (Pydantic data model) and begin the `indexer.py` implementation,
preceded by pytest tests per CLAUDE.md rules.
