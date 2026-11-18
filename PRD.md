# ContractGuard: Product Requirements Document

**Hackathon:** Mycrobo Arena (Nov 17-18, 2026) | **Track:** AI triage
**Brief:** A simple, architecture-agnostic agent for security, pulling slop, and finding coding gaps and loose ends.

## 1. Problem
Cleanup tools either miss high-level mismatches (docs, env templates and manifests that disagree with code) or "fix" things in ways that break the build. Developers, especially with AI-generated code, end up with leaked secrets, orphaned files, unused dependencies, undocumented env vars and README promises the code never delivered.

## 2. Solution
ContractGuard treats a repository as a **living contract**. It cross-checks contract files (README, `.env.example`, manifests, compose/config) against source code, triages findings by severity and confidence, then proposes fixes and **verifies each one in an isolated shadow git worktree** before keeping it.

## 3. Target users
- Solo developers and hackathon teams shipping fast with AI assistance
- Reviewers doing a pre-merge or pre-release hygiene pass
- Teams inheriting an unfamiliar codebase

## 4. Goals and non-goals
**Goals**
- One command to audit any repo, with no API key required
- Ranked, explainable findings (severity x confidence)
- Fixes are only kept if verification passes; the receipt states how strong that verification was

**Non-goals (24h scope)**
- Deep semantic analysis for every language (Python and JS/TS get depth, others get regex-level checks)
- Replacing SAST suites or full linters
- Auto-merging to the main branch

## 5. Functional requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| F1 | `audit <path>` produces a ranked findings report (Rich terminal and `--json`) | P0 |
| F2 | Security auditor: secrets, `DEBUG=True`, CORS `*`, `verify=False`, weak hashes, `0.0.0.0` binds | P0 |
| F3 | Env-contract drift: env vars read in code vs `.env.example`/compose | P0 |
| F4 | Slop auditor: orphaned files, unused dependencies | P0 |
| F5 | `heal <path>` applies fixes in a shadow worktree, runs verifier, keeps or rolls back each patch | P0 |
| F6 | `VERIFICATION_RECEIPT.md` with per-fix status and verification strength (TESTS_PASSED / SYNTAX_ONLY / NO_VERIFIER) | P0 |
| F7 | README-to-code drift: documented endpoints/commands missing in code | P1 |
| F8 | LLM (Groq) patch synthesis and finding explanations, optional | P1 |
| F9 | Deterministic fixes (e.g. append missing vars to `.env.example`) | P1 |
| F10 | Error-boundary gap check, AI-comment clutter detection | P2 |

## 6. Non-functional requirements
- Works offline for detection; LLM failures degrade gracefully
- Never modifies the target working tree directly; worktrees are always cleaned up
- Never deletes entry points, tests or config files
- Scan of a medium repo (~500 files) completes in under 30 seconds
- Python 3.10+, installable with `pip install -e .`

## 7. Success criteria
- Detects seeded issues in `sample-broken-app` with zero false negatives on the seeded set
- At least one fix rolled back in the demo, proving the gate works
- `SELF_VERIFICATION.md` produced by running ContractGuard on itself
- Repo contains `arena.json`, `README.md`, `AI_LOG.md` at root

## 8. Deliverables
Public GitHub repo, `sample-broken-app/`, `SELF_VERIFICATION.md`, 2-minute demo video, honest limitations section in README.

## 9. Risks and mitigations
| Risk | Mitigation |
|------|-----------|
| False-positive deletions | Entry-point whitelist, confidence thresholds, verifier gate |
| Target is not a git repo or has a dirty tree | Fall back to temp-dir copy |
| Weak or missing tests give false confidence | Receipt labels verification strength |
| LLM rate limits or bad JSON | Deterministic detectors, strict JSON validation, skip on failure |
