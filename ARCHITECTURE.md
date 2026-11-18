# ContractGuard: Architecture

## 1. Overview
```
 target repo
     |
 [indexer] --> contract files (README, .env.example, manifests, compose, yaml)
     |     \-> source files
     v
 [auditors] security | drift | slop  --> list[Finding]
     |
 [triage] rank by severity x confidence, dedupe
     |
 audit mode --> [reporter] (Rich / JSON)
     |
 heal mode:
 [fixer] deterministic fixes first, LLM patches second (strict JSON hunks)
     |
 [sandbox] git worktree (or temp copy) -> apply patch -> detect verifier -> run
     |            pass: VERIFIED, promote to branch   fail: ROLLED_BACK
     v
 [reporter] VERIFICATION_RECEIPT.md
```

## 2. Modules

| Module | Responsibility |
|--------|---------------|
| `cli.py` | Click commands: `audit`, `heal`, `verify`; flags `--json`, `--branch`, `--no-llm` |
| `models.py` | Pydantic `Finding`, `Patch`, `VerificationResult` |
| `indexer.py` | Walk repo, skip `.git`/`node_modules`/venv/binaries, classify contract vs source |
| `auditors/security.py` | Regex and AST checks for secrets and insecure defaults |
| `auditors/drift.py` | Env var extraction (`os.getenv`, `process.env`, `os.Getenv`) diffed against `.env.example`/compose; README endpoint/command check |
| `auditors/slop.py` | Import graph for orphan files; manifest vs imports for unused deps |
| `triage.py` | Score = severity weight x confidence; dedupe; sort |
| `fixer.py` | Deterministic fixers plus optional Groq patch generator |
| `sandbox.py` | Worktree lifecycle, patch apply, verifier detection, gate, rollback |
| `reporter.py` | Rich summary, JSON output, `VERIFICATION_RECEIPT.md` |

## 3. Data model
```python
class Finding(BaseModel):
    id: str
    category: Literal["security", "drift", "slop"]
    severity: Literal["critical", "high", "medium", "low", "info"]
    confidence: float          # 0.0 - 1.0
    file: str
    line: int | None
    title: str
    evidence: str
    suggested_fix: str | None
```

## 4. Verification gate (key differentiator)
1. Create `git worktree add --detach <tmp>`; fall back to a temp copy if not a git repo or tree is dirty.
2. Run a **baseline** verifier first. If the baseline already fails, record it and compare against it, not against zero.
3. Apply one patch at a time. Run verifier. Exit code 0 and no new failures: `VERIFIED`. Otherwise revert that patch: `ROLLED_BACK`.
4. Verifier detection order: `pytest` -> `npm test` -> `go test ./...` -> `cargo check` -> syntax fallback (`python -m compileall`, `node --check`).
5. Strength is recorded: `TESTS_PASSED`, `SYNTAX_ONLY`, `NO_VERIFIER`.
6. Promote verified patches to `contractguard/clean`. Cleanup in `try/finally` with `git worktree remove --force`.

## 5. Safety rules
- Target working tree is never edited in place.
- Protected paths (entry points, `tests/`, configs, lockfiles) cannot be deleted.
- LLM output must parse as strict JSON hunks and the search string must match exactly once, or it is discarded.
- Secrets in evidence are masked in reports.

## 6. Extensibility
Auditors implement `audit(index) -> list[Finding]`. New language support means adding patterns to an extractor table, not changing the pipeline.
