# ContractGuard

Read these specs before doing any work. They are the source of truth:

@PRD.md
@ARCHITECTURE.md
@TECH_STACK.md

Python CLI that audits a repo as a "living contract" (docs, env templates,
manifests vs. actual code), triages findings, and verifies every fix in a
shadow git worktree before keeping it.

## Rules

- Follow PRD.md for scope and priorities (P0 first, then P1, then P2).
- Follow ARCHITECTURE.md for modules, data model and the verification gate.
- Follow TECH_STACK.md for dependencies. New ones are allowed if justified;
  update TECH_STACK.md in the same commit.
- If you change the design, update the relevant doc in the same commit.
- Detectors are deterministic and work with NO API key. LLM (Groq) only
  writes patches and explains findings, and is always optional.
- Every finding is a pydantic `Finding`: id, category (security|drift|slop),
  severity, confidence (0-1), file, line, title, evidence, suggested_fix.
- Never modify the target repo directly. All edits happen in a temp
  worktree/copy. Always clean up in try/finally.
- Verification receipts must state strength: TESTS_PASSED, SYNTAX_ONLY,
  or NO_VERIFIER. Never claim more than was run.
- Never delete an entry point (main, **main**, bin, scripts, tests, configs).
- Python 3.10+, type hints, small functions.
- Write pytest tests before implementation. Commit after each phase.
- Append an entry to AI_LOG.md at the end of every phase (goal, prompt,
  output, what I corrected, decision).
- Work one phase at a time and stop for my review after each.

## Layout

contractguard/{cli,models,indexer,triage,fixer,sandbox,reporter}.py
contractguard/auditors/{security,drift,slop}.py
sample-broken-app/, tests/, arena.json, README.md, AI_LOG.md,
SELF_VERIFICATION.md

## Commands

python -m contractguard audit <path> [--json]
python -m contractguard heal <path> --branch contractguard/clean
pytest
