# ContractGuard — Evaluator Walkthrough

> A step-by-step guide for judges and evaluators to run ContractGuard end to end in under 5 minutes.

---

## Prerequisites

- Python 3.10+
- Git installed and on PATH
- A terminal (Windows Terminal recommended for best Rich table rendering)

---

## Step 1: Clone & Install

```bash
git clone https://github.com/DnvLikhitha/ContractGaurd.git
cd ContractGaurd

# Create and activate a virtual environment
python -m venv .venv

# Windows
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

# Install dependencies and the package
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .
```

Verify the CLI is available:

```bash
contractguard --help
```

Expected output:
```
Usage: contractguard [OPTIONS] COMMAND [ARGS]...

  ContractGuard — audit a repository as a living contract.

Commands:
  audit  Audit the repository at PATH and report findings.
  heal   Apply fixes in a shadow worktree, verify each, and promote to...
```

---

## Step 2: Audit the Demo App (Rich Table Output)

The `sample-broken-app/` directory ships with **8 deliberately seeded defects**:

| # | Defect | Type |
|---|--------|------|
| 1 | Hardcoded fake API key (`sk_demo_not_a_real_key_12345`) | Security |
| 2 | `DEBUG = True` in production code | Security |
| 3 | CORS wildcard `*` in Python | Security |
| 4 | CORS wildcard `*` in Node.js | Security |
| 5 | `APP_EXTRA_SECRET_TOKEN` read in code, absent from `.env.example` | Drift |
| 6 | `NODE_SESSION_SECRET` read in Node, absent from `.env.example` | Drift |
| 7 | `GET /api/v1/nonexistent_stats` documented in README but not in code | Drift |
| 8 | `unused-xml-parser`, `unused-node-lib`, orphan `services/orphan_service.py` | Slop |

Run the audit:

```bash
contractguard audit sample-broken-app
```

You should see a **colour-coded Rich table** ranked by triage score (Severity × Confidence):

```
ContractGuard auditing sample-broken-app …
  Indexed 4 source files, 4 contract files.
Findings: 1 CRITICAL  5 HIGH  2 MEDIUM  5 LOW
┌──────┬────────────────┬───────────┬──────────────────────────────┬──────────────────────────────────────────┬───────┐
│ #    │ Severity       │ Category  │ File:Line                    │ Title                                    │ Conf. │
├──────┼────────────────┼───────────┼──────────────────────────────┼──────────────────────────────────────────┼───────┤
│ 1    │ [CRITICAL]     │ security  │ app.py:4                     │ Hardcoded API / Secret Key               │ 0.80  │
│ 2    │ [HIGH]         │ security  │ app.py:7                     │ DEBUG=True in production code            │ 0.90  │
│ 3    │ [HIGH]         │ drift     │ app.py                       │ Env var 'APP_EXTRA_SECRET_TOKEN' absent  │ 0.85  │
│ 4    │ [HIGH]         │ security  │ app.py:10                    │ CORS Wildcard (*) — all origins allowed  │ 0.85  │
│ 5    │ [HIGH]         │ drift     │ server.js                    │ Env var 'NODE_SESSION_SECRET' absent     │ 0.85  │
│ 6    │ [HIGH]         │ security  │ server.js:7                  │ CORS Wildcard (*) — all origins allowed  │ 0.85  │
│ 7    │ [MEDIUM]       │ drift     │ README.md                    │ Endpoint '/api/v1/nonexistent_stats'...  │ 0.80  │
...
└──────┴────────────────┴───────────┴──────────────────────────────┴──────────────────────────────────────────┴───────┘
Total: 13 finding(s) after deduplication and ranking.
```

---

## Step 3: Machine-Readable JSON Output

```bash
contractguard audit sample-broken-app --json
```

Returns a clean JSON array — suitable for piping into CI/CD systems. Notice:
- **Secrets are masked**: `"evidence": "API_KEY=***MASKED***"`
- Each finding includes `id`, `category`, `severity`, `confidence`, `file`, `line`, `title`, `evidence`, and `suggested_fix`.

---

## Step 4: The Verification Gate — The Key Differentiator

```bash
contractguard heal sample-broken-app --no-llm
```

**What happens internally:**

1. ContractGuard creates an **isolated temporary copy** of `sample-broken-app/` — your working directory is never touched.
2. It detects `pytest` as the verifier and runs a **baseline** to confirm tests are currently green.
3. For each generated patch, it:
   - Applies the patch in the isolated copy
   - Runs `pytest`
   - **PASS** → marks `VERIFIED`, keeps the fix
   - **FAIL** → immediately reverts the file, marks `ROLLED_BACK`

**Expected output:**
```
ContractGuard heal inspecting C:\...\sample-broken-app ...
Generating fixes for 13 finding(s)...
Applying and verifying 6 patch(es) in sandbox...
  Baseline verifier: pytest (Strength: TESTS_PASSED)
  Patch for DRF-001 (.env.example): VERIFIED
  Patch for DRF-002 (.env.example): VERIFIED
  Patch for SLP-001 (services\orphan_service.py): VERIFIED
  Patch for SLP-002 (package.json): VERIFIED
  Patch for SLP-003 (requirements.txt): ROLLED_BACK   ← tempting fix that breaks a test
  Patch for SLP-004 (requirements.txt): ROLLED_BACK
✔ Verification receipt written to ...\VERIFICATION_RECEIPT.md
```

> **Why is `SLP-003` rolled back?**  
> `legacy-compat-dep` looks unused — no Python file imports it. A naive tool would delete it.  
> But `sample-broken-app/test_app.py::test_legacy_dependency_contract` deliberately asserts that the dependency exists in `requirements.txt` as a **backwards-compatibility contract test**. ContractGuard's gate catches the failure and reverts the file. This is exactly the guarantee the tool provides.

---

## Step 5: Read the Verification Receipt

```bash
# Windows
type sample-broken-app\VERIFICATION_RECEIPT.md

# macOS / Linux
cat sample-broken-app/VERIFICATION_RECEIPT.md
```

The receipt shows each finding, its status, the exact test command run, full test output, and the **verification strength**:

| Strength | Meaning |
|----------|---------|
| `TESTS_PASSED` | The repo's own test suite confirmed the fix is safe |
| `SYNTAX_ONLY` | No test suite found; syntax validation was used |
| `NO_VERIFIER` | No verifier detected; change is explicitly flagged as unverified |

---

## Step 6: Run the Full Test Suite

```bash
pytest
```

Expected:
```
414 passed in ~50s
```

The 414 tests cover all modules: models, indexer, triage, reporter, security auditor, drift auditor, slop auditor, sandbox gate, fixer, CLI, heal integration, and the sample broken app integration.

---

## Step 7: Self-Verification (Bonus)

```bash
contractguard audit .
```

ContractGuard audits its own codebase. It detects 29 findings — including its own internal regex pattern strings, development-only dependencies, and an uncontracted `GROQ_API_KEY` environment variable. The full honest analysis is in [`SELF_VERIFICATION.md`](SELF_VERIFICATION.md).

---

## Project Structure

```
ContractGuard/
├── contractguard/              # Core Python package
│   ├── cli.py                  # Click CLI (audit + heal commands)
│   ├── models.py               # Pydantic data models (Finding, Patch, VerificationResult)
│   ├── indexer.py              # Repo walker and file classifier
│   ├── triage.py               # Score = severity_weight × confidence, dedupe, rank
│   ├── reporter.py             # Rich table, JSON output, VERIFICATION_RECEIPT.md
│   ├── fixer.py                # Deterministic fixers + optional Groq LLM patch generator
│   ├── sandbox.py              # Shadow worktree lifecycle + verification gate
│   └── auditors/
│       ├── security.py         # 11 security rules (secrets, debug, CORS, SSL, weak hashes)
│       ├── drift.py            # Env-contract bidirectional diff + README endpoint/command check
│       └── slop.py             # Import graph, orphan files, unused manifest dependencies
├── sample-broken-app/          # Demo app with 8 seeded defects
├── tests/                      # 414 unit + integration tests
├── SELF_VERIFICATION.md        # ContractGuard auditing itself
├── AI_LOG.md                   # Full AI session log (Phases 0–10)
├── arena.json                  # Hackathon submission metadata
└── README.md                   # Full documentation
```

---

## Auditor Coverage Summary

| Auditor | What It Detects |
|---------|----------------|
| **Security** | AWS keys, PEM private keys, generic API/Bearer secrets, DB DSN passwords, `DEBUG=True`, CORS `*`, `verify=False`, MD5/SHA1 for passwords, `0.0.0.0` binds |
| **Drift** | Env vars in code vs `.env.example` / `docker-compose.yml` (both directions), README HTTP endpoints and CLI commands vs source code symbols |
| **Slop** | Orphaned files via Python AST + JS/TS regex import graph (with entry-point whitelist), unused dependencies in `requirements.txt` and `package.json` (with name mismatch map: `pyyaml→yaml`, `pillow→PIL`, etc.) |
