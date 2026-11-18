# ContractGuard

> **Hackathon:** Mycrobo Arena · Nov 17–18, 2026 · **Track:** AI Triage  
> **Tagline:** Audit your repo as a living contract, triage findings deterministically, and verify every fix in a shadow git worktree before keeping it.

[![Tests](https://img.shields.io/badge/tests-414%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

---

## 1. The Problem

Modern repositories define implicit and explicit contracts across multiple files:
- **Environment contracts**: `.env.example`, `docker-compose.yml`, Helm charts.
- **Dependency contracts**: `requirements.txt`, `package.json`, `pyproject.toml`.
- **Documentation contracts**: `README.md` listing API endpoints and CLI commands.

Over time, source code silently drifts from these contracts:
1. Developers read new environment variables in source code without adding them to `.env.example`.
2. Packages remain in manifests long after code referencing them was refactored away ("slop").
3. Dead code ("orphans") lingers, confusing newcomers and AI coding agents.
4. Security smells (hardcoded secrets, `DEBUG=True`, CORS `*`, unverified SSL) creep in.

Worse, **automated remediation tools and LLM fixers frequently introduce hallucinations that break builds**. Typical AI refactoring tools blindly apply edits directly to the working tree. If a patch removes a dependency that a test relied on, the build is silently broken.

---

## 2. The Solution: ContractGuard

ContractGuard approaches repository health from two core principles:

1. **Deterministic Living Contract Auditing (No API Key Required)**:  
   ContractGuard cross-checks documentation, environment templates, and manifests against actual code using AST and deterministic heuristics. Every finding is assigned an explicit severity, confidence score, and calculated triage rank.

2. **The Verification Gate (Shadow Git Worktree)**:  
   ContractGuard never modifies your active working tree directly. Every fix (whether deterministic or LLM-generated) is executed in an isolated shadow git worktree, tested against the repository's native test suite or compiler, and **automatically rolled back if any test fails**.

---

## 3. Installation

Requires Python 3.10+:

```bash
# Clone the repository
git clone https://github.com/DnvLikhitha/ContractGaurd.git
cd ContractGaurd

# Install in editable mode
pip install -e .
```

To run development tests:
```bash
pip install -r requirements-dev.txt
pytest
```

---

## 4. Usage

### Auditing a Repository

Audit any directory or repository:

```bash
# Human-friendly Rich table output
contractguard audit /path/to/repo

# Or via Python module execution
python -m contractguard audit .

# Clean JSON output for CI/CD pipelines
contractguard audit /path/to/repo --json
```

### Healing a Repository

Run the automated remediation pipeline with the shadow worktree verification gate:

```bash
# Heal using deterministic fixers (offline, no API key needed)
contractguard heal /path/to/repo --no-llm

# Heal with optional Groq LLM assistance for complex security findings
export GROQ_API_KEY="your-groq-api-key"
contractguard heal /path/to/repo --branch contractguard/clean
```

Upon completion, verified fixes are promoted to the designated branch, and a comprehensive `VERIFICATION_RECEIPT.md` is generated in the repository root.

---

## 5. Example Output

### Rich CLI Output

```text
ContractGuard auditing sample-broken-app …
  Indexed 4 source files, 3 contract files.
Findings: 1 CRITICAL  4 HIGH  0 MEDIUM  4 LOW
┌──────┬────────────┬──────────┬─────────────────────────────┬────────────────────────────────────────────────────────┬───────┐
│ #    │ Severity   │ Category │ File:Line                   │ Title                                                  │ Conf. │
├──────┼────────────┼──────────┼─────────────────────────────┼────────────────────────────────────────────────────────┼───────┤
│ 1    │ [CRITICAL] │ security │ app.py:4                    │ Hardcoded API / Secret Key                             │ 0.80  │
│ 2    │ [HIGH]     │ security │ app.py:7                    │ DEBUG=True in production code                          │ 0.90  │
│ 3    │ [HIGH]     │ drift    │ app.py                      │ Env var 'APP_EXTRA_SECRET_TOKEN' absent from contract  │ 0.85  │
│ 4    │ [HIGH]     │ security │ app.py:10                   │ CORS Wildcard (*) — all origins allowed                │ 0.85  │
│ 5    │ [HIGH]     │ security │ server.js:7                 │ CORS Wildcard (*) — all origins allowed                │ 0.85  │
│ 6    │ [LOW]      │ drift    │ .env.example                │ Env var 'DATABASE_URL' declared but not used in code   │ 0.70  │
│ 7    │ [LOW]      │ slop     │ package.json                │ Unused dependency 'unused-node-lib'                    │ 0.60  │
│ 8    │ [LOW]      │ slop     │ requirements.txt            │ Unused dependency 'unused-xml-parser'                  │ 0.60  │
│ 9    │ [LOW]      │ slop     │ services/orphan_service.py  │ Orphaned file is never imported                        │ 0.60  │
└──────┴────────────┴──────────┴─────────────────────────────┴────────────────────────────────────────────────────────┴───────┘
Total: 9 finding(s) after deduplication and ranking.
```

### Machine-Readable JSON Output (`--json`)

```json
[
  {
    "id": "SEC-0001",
    "category": "security",
    "severity": "critical",
    "confidence": 0.8,
    "file": "app.py",
    "line": 4,
    "title": "Hardcoded API / Secret Key",
    "evidence": "API_KEY=***MASKED***",
    "suggested_fix": "Move secret to an environment variable or secrets manager."
  }
]
```

---

## 6. How the Verification Gate Works

The verification gate is the core differentiator of ContractGuard:

```
Target Repo ───► Create Shadow Git Worktree (Detached)
                       │
                       ▼
                 Run Baseline Verifier (e.g. pytest)
                       │
                       ▼
              For each triaged patch:
                 ├── Apply patch (Exact 1-match hunk)
                 ├── Run verifier
                 ├── PASS: Mark VERIFIED
                 └── FAIL: git checkout / revert & Mark ROLLED_BACK
                       │
                       ▼
         Promote VERIFIED patches to branch 'contractguard/clean'
                       │
                       ▼
           Write VERIFICATION_RECEIPT.md (Guaranteed cleanup in try/finally)
```

1. **Isolation**: A temporary git worktree is spawned (`git worktree add --detach <tmp>`). If the target is not a git repo or has uncommitted changes, an isolated temporary directory copy is used as a fallback.
2. **Native Verifier Detection Hierarchy**:
   - `pytest` (Python)
   - `npm test` (JavaScript/Node.js)
   - `go test ./...` (Go)
   - `cargo check` (Rust)
   - Syntax validation fallback (`python -m compileall`, `node --check`)
   - `NO_VERIFIER` fallback
3. **Receipt Strength**: ContractGuard records the exact verification strength:
   - `TESTS_PASSED`: The repository's test suite passed.
   - `SYNTAX_ONLY`: No test suite was found; syntax was validated.
   - `NO_VERIFIER`: No verifier was detected; changes are explicitly noted as unverified.
4. **Zero Collateral Damage**: If a tempting patch breaks an existing test (e.g. removing a legacy package that a backwards-compatibility test actually imports), the patch is instantly rolled back.

---

## 7. Honest Limitations

- **Heuristic Static Analysis**: AST and regex parsers capture explicit environment variable reads (`os.getenv`, `process.env`) and imports. Dynamic reflection (`getattr(os.environ, ...)` or runtime string lookups) will have lower confidence or be missed.
- **Language Depth**: Deep AST import analysis is currently implemented for Python and JavaScript/TypeScript. Go and other languages are currently supported for environment drift and verifier execution.
- **Single-Match Rule for LLM Hunks**: When the optional Groq patch generator runs, it enforces a strict single-occurrence rule (`content.count(search) == 1`). If a search string matches zero or multiple times, the patch is discarded to prevent unintended edits.
- **Verifier Runtime**: For massive monolithic test suites, gating fixes sequentially can take time proportional to the test run duration.

---

## 8. AI Usage & Provenance

In accordance with hackathon transparency guidelines:
- **Process Logging**: Every step of ContractGuard's design, scaffolding, testing, and debugging is meticulously recorded in [`AI_LOG.md`](AI_LOG.md).
- **Session Transcripts**: Raw session transcripts and conversation logs are preserved in [`transcripts/`](transcripts/).
- **AI Boundaries**: All detectors (`security`, `drift`, `slop`), triage formulas, indexers, sandbox worktree gates, and test suites are 100% deterministic code that operates offline without any external API calls. AI (Groq) is strictly used as an optional patch generator.

---

## 9. Verification & Self-Audit

ContractGuard was audited against its own codebase. See [`SELF_VERIFICATION.md`](SELF_VERIFICATION.md) for the full report and analysis.
