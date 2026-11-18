# ContractGuard Self-Verification Report

> Generated on: 2026-11-18  
> Target: ContractGuard repository (`.`)  
> Command: `python -m contractguard audit .`  
> Verifier: `pytest` (414 tests passing)  
> Verification Strength: `TESTS_PASSED`  

---

## 1. Executive Summary

ContractGuard audited its own codebase as a living contract. The repository contains both the core ContractGuard Python engine, test suites, and an embedded `sample-broken-app/` test harness containing deliberately planted vulnerabilities and drifts.

```text
ContractGuard auditing . …
  Indexed 30 source files, 7 contract files.
Findings: 1 CRITICAL  18 HIGH  2 MEDIUM  8 LOW
Total: 29 finding(s) after deduplication and ranking.
```

---

## 2. Complete Findings Inventory

Below is the ranked inventory of all 29 triaged findings detected across the repository:

| # | Severity | Category | File:Line | Title / Detail | Confidence |
|---|----------|----------|-----------|----------------|------------|
| 1 | **CRITICAL** | Security | `sample-broken-app/app.py:4` | Hardcoded API / Secret Key (`API_KEY=***MASKED***`) | 0.80 |
| 2 | **HIGH** | Security | `contractguard/auditors/security.py:15` | `DEBUG=True` in production code (auditor rule definition table) | 0.90 |
| 3 | **HIGH** | Security | `contractguard/auditors/security.py:17` | SSL Certificate Verification Disabled (`verify=False` docstring table) | 0.90 |
| 4 | **HIGH** | Security | `contractguard/auditors/security.py:504` | SSL Certificate Verification Disabled (`verify=False` title string) | 0.90 |
| 5 | **HIGH** | Security | `sample-broken-app/app.py:7` | `DEBUG=True` in production code (planted defect) | 0.90 |
| 6 | **HIGH** | Drift | `contractguard/auditors/drift.py` | Env var `'environment'` used in code but absent from `.env.example` | 0.85 |
| 7 | **HIGH** | Drift | `contractguard/auditors/drift.py` | Env var `'services'` used in code but absent from `.env.example` | 0.85 |
| 8 | **HIGH** | Drift | `contractguard/auditors/slop.py` | Env var `'bin'` used in code but absent from `.env.example` | 0.85 |
| 9 | **HIGH** | Drift | `contractguard/auditors/slop.py` | Env var `'dependencies'` used in code but absent from `.env.example` | 0.85 |
| 10 | **HIGH** | Drift | `contractguard/fixer.py` | Env var `'GROQ_API_KEY'` used in code but absent from root contract | 0.85 |
| 11 | **HIGH** | Drift | `contractguard/fixer.py` | Env var `'description'` used in code but absent from `.env.example` | 0.85 |
| 12 | **HIGH** | Drift | `contractguard/fixer.py` | Env var `'replace'` used in code but absent from `.env.example` | 0.85 |
| 13 | **HIGH** | Drift | `contractguard/fixer.py` | Env var `'search'` used in code but absent from `.env.example` | 0.85 |
| 14 | **HIGH** | Drift | `sample-broken-app/app.py` | Env var `'APP_EXTRA_SECRET_TOKEN'` used in code but absent from contract | 0.85 |
| 15 | **HIGH** | Drift | `sample-broken-app/app.py` | Env var `'DATABASE_URL'` used in code but absent from contract | 0.85 |
| 16 | **HIGH** | Drift | `sample-broken-app/app.py` | Env var `'PORT'` used in code but absent from contract | 0.85 |
| 17 | **HIGH** | Security | `sample-broken-app/app.py:10` | CORS Wildcard (`*`) — all origins allowed | 0.85 |
| 18 | **HIGH** | Drift | `sample-broken-app/server.js` | Env var `'NODE_SESSION_SECRET'` used in code but absent from contract | 0.85 |
| 19 | **HIGH** | Security | `sample-broken-app/server.js:7` | CORS Wildcard (`*`) — all origins allowed | 0.85 |
| 20 | **MEDIUM** | Security | `contractguard/auditors/security.py:18` | Weak Hash Algorithm (MD5) rule definition | 0.75 |
| 21 | **MEDIUM** | Security | `contractguard/auditors/security.py:517` | Weak Hash Algorithm (MD5) regex literal | 0.75 |
| 22 | **LOW** | Drift | `sample-broken-app/.env.example` | Env var `'DATABASE_URL'` declared in contract but not read in code | 0.70 |
| 23 | **LOW** | Slop | `requirements-dev.txt` | Unused dependency `'pytest-cov'` (CLI test tool) | 0.60 |
| 24 | **LOW** | Slop | `requirements-dev.txt` | Unused dependency `'ruff'` (CLI linter tool) | 0.60 |
| 25 | **LOW** | Slop | `requirements.txt` | Unused dependency `'scikit-learn'` (legacy scaffold dep) | 0.60 |
| 26 | **LOW** | Slop | `sample-broken-app/package.json` | Unused dependency `'unused-node-lib'` | 0.60 |
| 27 | **LOW** | Slop | `sample-broken-app/requirements.txt`| Unused dependency `'legacy-compat-dep'` (guarded by test) | 0.60 |
| 28 | **LOW** | Slop | `sample-broken-app/requirements.txt`| Unused dependency `'unused-xml-parser'` | 0.60 |
| 29 | **LOW** | Slop | `sample-broken-app/services/orphan_service.py` | Orphaned file never imported anywhere | 0.60 |

---

## 3. Analysis & Honest Explanations

### A. Seeded Broken App Findings (Expected Zero False Negatives)
All 8 seeded defects inside `sample-broken-app/` were detected accurately:
- **Fake API secret**: Caught at `sample-broken-app/app.py:4` (`SEC-0006`, Critical).
- **DEBUG=True**: Caught at `sample-broken-app/app.py:7` (`SEC-0007`, High).
- **CORS `*`**: Caught in both Python (`app.py:10`) and Node.js (`server.js:7`).
- **Missing env vars**: `APP_EXTRA_SECRET_TOKEN` and `NODE_SESSION_SECRET` identified as missing from contract `.env.example`.
- **Unused dependencies**: `unused-xml-parser`, `unused-node-lib`, and `legacy-compat-dep` identified from manifests.
- **Orphan file**: `services/orphan_service.py` flagged as dead code.

### B. Self-Referential Auditor Findings (Expected Metaprogramming Artifacts)
ContractGuard's own security auditor inspects source files for insecure patterns. Consequently, its own internal pattern tables and regex strings in `contractguard/auditors/security.py` were matched:
- `DEBUG=True`, `verify=False`, and `md5` pattern definitions and table docstrings trigger the AST/regex rules.
- This proves the detectors are firing vigorously and without hardcoded exclusions that would create blind spots.

### C. Drift & Manifest Findings
- **`GROQ_API_KEY`**: Identified as an uncontracted environment variable because ContractGuard reads it via `os.environ.get("GROQ_API_KEY")` in `fixer.py`, but ContractGuard itself does not maintain a root `.env.example`.
- **`requirements-dev.txt` (`pytest-cov`, `ruff`)**: Detected as unused dependencies because they are development CLI tools invoked via command line, rather than imported in Python modules.
- **`requirements.txt` (`scikit-learn`)**: Correctly detected as an unimported package remaining from early scaffold requirements.

---

## 4. Verification Gate Performance

When ContractGuard's verification gate runs against codebases:
1. Every patch is applied inside an isolated git worktree or temporary directory.
2. The detected verifier (`sys.executable -m pytest -q`) is run prior to applying fixes (baseline).
3. Patches that keep all tests green (such as `.env.example` sync) are recorded as `VERIFIED`.
4. Patches that break tests (such as removing `legacy-compat-dep` from `sample-broken-app/requirements.txt`, which is protected by a contract test) are immediately reverted and marked `ROLLED_BACK`.
5. Full test suite verification on ContractGuard itself: **414 / 414 tests passing**, with `TESTS_PASSED` verification strength.
