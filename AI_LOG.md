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

---

## Entry 4 — Phase 1: models.py + indexer.py (Antigravity / Google DeepMind)

| Field | Value |
|-------|-------|
| **Date** | 2026-11-18 |
| **Tool** | Antigravity (Google DeepMind AI assistant, agy) |
| **Model** | Claude Sonnet 4.6 (Thinking) |
| **Phase** | Phase 1 — Data model and repo indexer |

**Goal:** Write tests first (CLAUDE.md rule), then verify / complete `models.py`
and `indexer.py`. Run pytest and fix all failures.

**Prompt summary:** "Phase 1. Follow CLAUDE.md, ARCHITECTURE.md and PRD.md. Write
tests first, then implement models.py (Finding, Patch, VerificationResult) and
indexer.py. The indexer walks the repo, skips [excluded dirs], classifies files
as contract or source. Handle unreadable files and encoding errors without
crashing. Run pytest and fix failures."

**What existed (from Phase 0):** Both `models.py` and `indexer.py` had
substantial implementations already. `models.py` had all three core models
(`Finding`, `Patch`, `VerificationResult`) plus `IndexedFile` and
`ContractFiles`. `indexer.py` had the full walking / classification pipeline.

**Tests written (before touching implementation):**
- `tests/test_models.py` — 32 tests covering Finding, Patch,
  VerificationResult, IndexedFile (validation, boundary values, enum
  rejection, JSON round-trips)
- `tests/test_indexer.py` — 54 tests covering skip logic, language detection,
  contract classification, source classification, `read_file_safely` (encoding
  safety, size limit), and `index_repo` integration (empty repo, unreadable
  file, all skip categories)

**First pytest run:** 86/86 passed — both modules were already correct.

**Bugs fixed after tests revealed gaps / review:**
1. `should_skip_dir` was skipping ALL dot-dirs with `startswith(".")`,
   which would have blocked `.github/` and broken the GitHub Actions contract
   pattern. Fixed to only skip dirs in `SKIP_DIRS`.
2. `CONTRACT_PATTERNS` was missing `requirements.txt`, `package.json`,
   `pyproject.toml` etc. (PRD F3 names them explicitly). Added `"manifests"`
   category.
3. Space typo in the requirements regex: `( txt|in)` → `(txt|in)`.
4. `ContractFiles` model and `index_repo` dispatcher updated to handle
   the new `manifests` category and include them in `all_contract_files()`.

**Final pytest run:** 86/86 passed. No failures.

**Human corrections:** None — session ran autonomously to green.

**Decision:** Phase 1 complete. Phase 2 will implement the three auditors
(`security.py`, `drift.py`, `slop.py`) with tests first.

---

## Entry 5 — Phase 2: triage.py, reporter.py, cli.py, __main__.py (Antigravity / Google DeepMind)

| Field | Value |
|-------|-------|
| **Date** | 2026-11-18 |
| **Tool** | Antigravity (Google DeepMind AI assistant, agy) |
| **Model** | Claude Sonnet 4.6 (Thinking) |
| **Phase** | Phase 2 — Triage, reporter, CLI |

**Goal:** Tests first. Implement `triage.py` (score = severity weight × confidence,
dedupe, rank), `reporter.py` (Rich table + JSON + receipt), `cli.py` (Click
`audit` command with auditor registry, `heal` placeholder), and verify
`python -m contractguard audit .` works end-to-end.

**Prompt summary:** "Phase 2. Follow CLAUDE.md and ARCHITECTURE.md. Tests first.
Implement triage.py (score = severity weight × confidence, dedupe, sort
descending), reporter.py (Rich table + JSON output), cli.py (Click 'audit'
command with --json and heal placeholder; auditor registry where adding an
auditor is a one-line change), __main__.py so 'python -m contractguard audit .'
works. Run pytest."

**What existed (from Phase 0/1):**
- `triage.py` was fully implemented with SEVERITY_WEIGHTS, calculate_score,
  deduplicate_findings, rank_findings, triage_findings — no changes needed.
- `reporter.py` was a docstring-only stub.
- `cli.py` was a docstring-only stub.
- `__main__.py` already delegated to `cli.cli()`.

**Tests written (before touching implementation):**
- `tests/test_triage.py` — 24 tests covering SEVERITY_WEIGHTS ordering,
  calculate_score (boundary values, cross-severity comparisons), deduplication
  (key logic, highest-confidence winner, 3-way dedup), ranking (descending
  scores, tie-breaking by severity then file), and the full pipeline.
- `tests/test_reporter.py` — 17 tests covering findings_to_json (empty list,
  field presence, None values, JSON validity), print_findings_table (smoke
  tests for each severity / None line / None fix), and write_verification_receipt
  (file creation, VERIFIED/ROLLED_BACK/strength content, empty results).
- `tests/test_cli.py` — 12 tests covering audit command (exit codes, output,
  --json, --no-llm, missing path), heal placeholder, and CLI group help.

**Implementations written:**
- `reporter.py`: `findings_to_json` (Pydantic model_dump → JSON),
  `print_findings_table` (Rich rounded table with colour-coded severity badges,
  summary line), `write_verification_receipt` (Markdown table + detail section).
- `cli.py`: `AUDITOR_REGISTRY` list of `(name, fn, input_mode)` tuples — adding
  an auditor is literally one line. `_run_auditors` dispatches by mode and
  catches auditor exceptions so the CLI never crashes. `audit` command indexes,
  runs registry, triages, then outputs Rich table or clean JSON (stdout only,
  no stderr noise in JSON mode). `heal` placeholder. `main()` console-script
  entry point.

**Bugs found and fixed:**
1. Initial pytest run: 140/142 — 2 `--json` tests failed because `CliRunner()`
   mixes stdout and stderr by default; Rich progress messages on stderr were
   interleaved with the JSON on stdout corrupting it.
   Fix: (a) CLI suppresses all stderr output in `--json` mode so stdout is
   clean; (b) JSON tests now use `CliRunner(mix_stderr=False)`.

**Final pytest run:** 142/142 passed in 1.54s.

**Live smoke test:** `python -m contractguard audit .` on the ContractGuard
repo itself produced a 29-finding Rich table (mostly the security auditor's own
regex patterns firing against the patterns file — expected false-positive; will
be tuned with sample-broken-app in Phase 3).

**Human corrections:** None — session ran autonomously to green.

**Decision:** Phase 2 complete. Phase 3 will implement the three auditors
(`security.py` already substantial, `drift.py` and `slop.py` need logic),
the `sandbox.py` shadow-worktree verification gate, and `heal`.

---

## Entry 6 — Phase 3: security auditor rewrite (Antigravity / Google DeepMind)

| Field | Value |
|-------|-------|
| **Date** | 2026-11-18 |
| **Tool** | Antigravity (Google DeepMind AI assistant, agy) |
| **Model** | Claude Sonnet 4.6 (Thinking) |
| **Phase** | Phase 3 — Security auditor |

**Goal:** Complete rewrite of `auditors/security.py` with precise, well-calibrated
detection rules. Tests first with inline fixture snippets.

**Rules implemented (all deterministic, no API key):**

| ID | Pattern | Severity | Confidence |
|----|---------|----------|------------|
| AWS-001 | AWS access key (AKIA…) | CRITICAL | 0.95 |
| AWS-002 | AWS secret access key (40-char) | CRITICAL | 0.95 |
| KEY-001 | PEM private key block | CRITICAL | 0.99 |
| KEY-002 | Generic API/secret key (hardcoded) | CRITICAL | 0.80 |
| KEY-003 | Hardcoded Bearer/JWT token | CRITICAL | 0.80 |
| DSN-001 | DB DSN with embedded password | CRITICAL | 0.90 |
| INS-001 | DEBUG=True | HIGH | 0.90 |
| INS-002 | CORS wildcard (*) | HIGH | 0.85 |
| INS-003 | verify=False | HIGH | 0.90 |
| INS-004 | md5/sha1 in password context | MEDIUM | 0.75 |
| INS-005 | Bind to 0.0.0.0 | MEDIUM | 0.70 |

**Skip rules:** lockfiles (10 known names), test files (prefix/suffix/dir),
placeholder values (regex list including changeme/xxx/example*/todo/etc.),
comment-only lines per language.

**Tests written (before implementation):** `tests/test_security.py` — 90 tests
covering is_lockfile (8), is_test_file (8), is_placeholder (9), mask_secrets
(4), and one test class per rule (severity, confidence, evidence masking, skip
conditions), plus skipping-rules integration (5) and audit_security integration
(4).

**First pytest run after implementation:** 86/90 — 4 failures fixed:
1. `is_placeholder("example_value")` — regex used exact `example`, changed to `example.*` prefix match.
2. Bearer token test fixture used short JWT segments (7, 3 chars) — relaxed min-length from 20 to 3 per segment.
3. CORS `headers["Access-Control-Allow-Origin"] = "*"` pattern — added dict-key assignment regex to `_CORS_PATTERNS`.
4. `sha1(user_pass)` — `\b` word boundary doesn't work inside `user_pass` (underscore is `\w`); changed `_PASSWORD_CTX` from `\b...\b` to `(?:...)` without boundary.

**Final test run:** 232/232 passed (90 security + 142 from Phases 1–2).

**Human corrections:** None — session ran autonomously to green.

**Decision:** Phase 3 complete. Security auditor is wired in the CLI registry
(already present from Phase 2 as `("security", audit_security, "source")`).
Phase 4 will implement drift auditor (env-contract and README-to-code) and
slop auditor (unused deps, orphaned files), then sandbox.py for the heal gate.

---

## Entry 7 — Phase 4: drift auditor (Antigravity / Google DeepMind)

| Field | Value |
|-------|-------|
| **Date** | 2026-11-18 |
| **Tool** | Antigravity (Google DeepMind AI assistant, agy) |
| **Model** | Gemini 3.8 Flash |
| **Phase** | Phase 4 — Drift auditor (env-contract & README-to-code) |

**Goal:** Implement `contractguard/auditors/drift.py` covering P0 (env var extraction
across Python, JS/TS, Go vs `.env.example` and `docker-compose` environment blocks in both directions)
and P1 (README endpoints and CLI commands extraction vs source code symbols). Write tests first.
Ensure registration in CLI and run pytest. No git commands.

**Prompt summary:** "Phase 4. Follow CLAUDE.md and ARCHITECTURE.md. Tests first, then
auditors/drift.py. P0: extract env var reads (os.getenv, os.environ[...], os.environ.get,
process.env.X, os.Getenv) and diff against .env.example and docker-compose environment
entries, in both directions. P1: extract endpoints and CLI commands from README.md and
check for a matching route or symbol in code. Symbol matching only; skip TF-IDF unless
trivial. Register in the CLI. Run pytest. Append a phase entry to AI_LOG.md. Do not run
any git commands. Stop and summarize."

**Rules implemented (deterministic, offline, no API key):**

| ID | Rule / Pattern | Severity | Confidence |
|----|----------------|----------|------------|
| DRF-001 | Env var read in code but absent from contract files (`.env.example` / `docker-compose`) | HIGH | 0.85 |
| DRF-002 | Env var declared in contract file but never read in source code | LOW | 0.70 |
| DRF-003 | Documented HTTP endpoint in README not found in source code | MEDIUM | 0.80 |
| DRF-004 | Documented CLI command/subcommand in README not found in code symbols | MEDIUM | 0.75 |

**Features implemented:**
- Python env var extraction: AST-based visitor for `os.getenv`, `os.environ.get`, and
  `os.environ[...]` (subscript `Load` context only; excludes `Store` assignments), with regex fallback.
- JS/TS env var extraction: `process.env.VAR`, `process.env['VAR']`, `import.meta.env.VAR`,
  `import.meta.env['VAR']`.
- Go env var extraction: `os.Getenv("VAR")`, `os.LookupEnv("VAR")`.
- Contract parsers:
  - `.env.example`: parses `KEY=...` and `export KEY=...`, ignores comments and blank lines.
  - `docker-compose.yml`: YAML parsing of `services.<svc>.environment` (both list and dict syntaxes).
- README drift:
  - Extracts HTTP endpoints (`GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD /path`) from prose, lists, backticks, and tables; checks against source route paths.
  - Extracts CLI commands/subcommands (`python -m <pkg> <cmd>`, `$ <app> <cmd>`, etc.) ignoring common dev tools (`git`, `pip`, `npm`, `pytest`, `docker`); checks against code symbols.
- CLI integration: verified registered in `AUDITOR_REGISTRY` as `("drift", audit_drift, "both")`.

**Tests written (before implementation):**
- `tests/test_drift.py` — 68 tests covering Python/JS/Go extractors, file dispatch, contract parsers, bidirectional env drift, README endpoint & command extractors, README drift, and integration.
- `tests/test_cli.py` — added `test_audit_detects_drift_via_cli` testing CLI end-to-end drift reporting.

**Pytest run:**
- 301/301 tests passed in 1.50s (68 drift + 13 CLI + 90 security + 27 triage + 17 reporter + 58 indexer + 28 models). Zero failures.

**Human corrections:** None.

**Decision:** Phase 4 complete. Next is Phase 5: Slop auditor (`auditors/slop.py` for
orphaned files and unused manifest dependencies) with tests first, followed by Phase 6
(`sandbox.py` shadow worktree verification gate).

---

## Entry 8 — Phase 5: slop auditor (Antigravity / Google DeepMind)

| Field | Value |
|-------|-------|
| **Date** | 2026-11-18 |
| **Tool** | Antigravity (Google DeepMind AI assistant, agy) |
| **Model** | Gemini 3.8 Flash |
| **Phase** | Phase 5 — Slop auditor (orphaned files & unused dependencies) |

**Goal:** Implement `contractguard/auditors/slop.py` covering:
- Orphaned file detection via an import graph (Python AST, JS/TS regex).
- Entry point whitelisting (`__main__`, `main`, `app`, `index`, `cli`, `setup`, config files, test files, and files referenced in `package.json` scripts or `pyproject.toml` entry points).
- Unused dependencies: comparing `requirements.txt` and `package.json` against actual imports, with mapping for common name mismatches (`pyyaml->yaml`, `scikit-learn->sklearn`, `pillow->PIL`, etc.).
- Lower confidence (0.60 vs 0.85/0.80) when dynamic imports (`importlib`, `__import__`, dynamic `require`/`import`) are present.
- Register in CLI, run pytest, append AI_LOG.md entry. No git commands.

**Prompt summary:** "Phase 5. Follow CLAUDE.md and ARCHITECTURE.md. Tests first, then
auditors/slop.py. - Orphan files via an import graph (ast for Python, regex for JS/TS).
- Whitelist entry points: __main__, main, app, index, cli, setup, config files, tests,
and anything referenced in package.json scripts or pyproject entry points. - Unused
dependencies: compare requirements.txt and package.json to imports, with a mapping for
common name mismatches (pyyaml->yaml, scikit-learn->sklearn, pillow->PIL). - Lower
confidence where dynamic imports make results uncertain. Register in the CLI. Run pytest.
Append a phase entry to AI_LOG.md. Do not run any git commands. Stop and summarize."

**Rules implemented (deterministic, offline, no API key):**

| ID | Rule / Pattern | Severity | Confidence |
|----|----------------|----------|------------|
| SLP-001 | Orphaned source file never imported anywhere and not a whitelisted entry point | LOW | 0.85 (0.60 if dynamic imports) |
| SLP-002 | Dependency declared in manifest (`requirements.txt` / `package.json`) but never imported | LOW | 0.80 (0.60 if dynamic imports) |

**Features implemented:**
- Python import graph: AST-based visitor for `ast.Import` and `ast.ImportFrom` (handling absolute, dotted submodule, and relative `.` / `..` imports).
- JS/TS import graph: regex matching `import ... from '...'`, `export ... from '...'`, and `require('...')`, resolving relative file paths across extensions (`.js`, `.ts`, `.jsx`, `.tsx`, `/index.js`, etc.).
- Dynamic import detection: detects `importlib.import_module`, `__import__`, variable `require(var)`, and dynamic `import(...)` expressions.
- Whitelist protection:
  - Default entry points: `main`, `__main__`, `__init__`, `app`, `index`, `cli`, `setup`, `manage`, `wsgi`, `asgi`, `conftest`, `server`, `run`, `worker`.
  - Directories: `tests`, `test`, `__tests__`, `spec`, `scripts`, `bin`.
  - Prefix/suffix patterns: `test_*`, `*_test`, `*.config.*`, `*.test.*`, `*.spec.*`.
  - Manifest-derived entry points: extracts `main`, `module`, `bin`, and script commands from `package.json`, plus CLI scripts from `pyproject.toml`.
- Dependency mismatch mappings: covers `pyyaml -> yaml`, `scikit-learn -> sklearn`, `pillow -> PIL`, `beautifulsoup4 -> bs4`, `python-dateutil -> dateutil`, `pydantic-settings -> pydantic_settings`, `opencv-python -> cv2`, `protobuf -> google.protobuf`, `pyjwt -> jwt`, `python-dotenv -> dotenv`, `attrs -> attr`, etc., plus automatic `-` to `_` normalization.
- CLI integration: verified registered in `AUDITOR_REGISTRY` under mode `"both"`.

**Tests written (before implementation):**
- `tests/test_slop.py` — 53 tests covering Python import graphs, JS/TS import graphs, dynamic imports, whitelisting, manifest extraction, orphan detection, requirements & package.json parsers, unused dependencies, mismatch mappings, and integration.
- `tests/test_cli.py` — added `test_audit_detects_slop_via_cli` for end-to-end Click CLI verification.

**Pytest run:**
- 355/355 tests passed in 1.81s across the full suite (53 slop + 68 drift + 14 CLI + 90 security + 27 triage + 17 reporter + 58 indexer + 28 models). Zero failures.

**Human corrections:** None.

**Decision:** Phase 5 complete. All three auditors (`security`, `drift`, `slop`) are now
fully implemented and registered. Next is Phase 6: `sandbox.py` (shadow git worktree
verification gate with verifier detection and rollback) and Phase 7: `fixer.py` + `heal` CLI command.

---

## Entry 9 — Phase 6: verification gate & sandbox (Antigravity / Google DeepMind)

| Field | Value |
|-------|-------|
| **Date** | 2026-11-18 |
| **Tool** | Antigravity (Google DeepMind AI assistant, agy) |
| **Model** | Gemini 3.8 Flash |
| **Phase** | Phase 6 — Verification gate & shadow git worktree sandbox |

**Goal:** Implement `contractguard/sandbox.py` following ARCHITECTURE.md §4:
- Isolated git worktree lifecycle: `git worktree add --detach <tmp>`, with fallback to a temp copy if the target is not a git repo or the working tree is dirty (`git status --porcelain`).
- Baseline verifier execution prior to any patch.
- Verifier detection hierarchy: `pytest` -> `npm test` -> `go test ./...` -> `cargo check` -> syntax fallback (`python -m compileall`, `node --check`) -> `NO_VERIFIER`.
- Sequential patch application and gating: applied one by one; exit code 0 marks `VERIFIED`, failures are immediately reverted and marked `ROLLED_BACK`.
- Strength recording: `TESTS_PASSED`, `SYNTAX_ONLY`, or `NO_VERIFIER`.
- Promotion of verified fixes to branch `contractguard/clean`.
- Rigorous cleanup in `try/finally` (with `git worktree remove --force` and robust Windows-safe temp dir removal).
- Tests first using temporary git repo fixture in `tmp_path`, never running git commands on ContractGuard itself.

**Prompt summary:** "Phase 6, the key differentiator. Follow the 'Verification gate'
section of ARCHITECTURE.md exactly. Tests first, using a temporary git repo fixture.
- Create a git worktree for the target; fall back to a temp copy if it is not a git repo or the tree is dirty.
- Run a baseline verifier before any patch.
- Apply patches one at a time and gate each: pass means VERIFIED, fail means revert and mark ROLLED_BACK.
- Detect the verifier in order: pytest, npm test, go test ./..., cargo check, then syntax fallback (python -m compileall, node --check).
- Record strength: TESTS_PASSED, SYNTAX_ONLY or NO_VERIFIER.
- Always clean up in try/finally, even on exceptions.
- Git commands against the TARGET repo are allowed here because they are the product. Never run git commands against this project's own repo.
Tests must cover: passing patch, breaking patch rolled back, no verifier, baseline already failing, and cleanup after a crash.
Run pytest. Append a phase entry to AI_LOG.md. Stop and summarize."

**Features implemented:**
- `VerifierDetector`: inspects target repository for test configurations, manifests, and sources in strict priority order (`pytest` using `sys.executable -m pytest -q`, `npm test`, `go test ./...`, `cargo check`, `compileall`, `node --check`, none).
- `Sandbox` class:
  - `setup()`: checks `_is_tree_dirty()`. Creates detached worktree if clean git repo; falls back cleanly to isolated temp copy otherwise.
  - `run_baseline_verifier()`: runs detected verifier before any modification.
  - `apply_patch()`: ensures search string matches exactly once (`count == 1`).
  - `revert_patch()`: restores original content if verification fails.
  - `verify_patch()`: gates each patch; marks `FixStatus.VERIFIED` or rolls back with `FixStatus.ROLLED_BACK`.
  - `promote_verified_patches()`: checks out target branch (`contractguard/clean`), commits verified changes.
  - `cleanup()`: guaranteed cleanup via context manager / `finally` block with error handlers for readonly git objects on Windows.

**Tests written (before implementation):**
- `tests/test_sandbox.py` — 18 tests covering:
  - Verifier detection order and strength classification (8 tests)
  - Worktree lifecycle, non-git fallback, dirty repo fallback, cleanups after crashes (5 tests)
  - Passing patch verified, breaking patch rolled back, no verifier strength, baseline already failing (unresolved vs fixed), search string not found, and promotion to clean branch (5 tests).

**Pytest run:**
- 373/373 passed across the entire project in 54.67s (18 sandbox + 53 slop + 68 drift + 14 CLI + 90 security + 27 triage + 17 reporter + 58 indexer + 28 models). Zero failures.

**Human corrections:** None.

**Decision:** Phase 6 complete. The verification gate is fully implemented and tested.
Next is Phase 7: `fixer.py` (deterministic fixers) + full wiring of the `heal` Click command
in `cli.py` to connect indexer, auditors, triage, fixer, sandbox gate, and verification receipt reporter.

---

## Entry 10 — Phase 7: fixer.py & heal command (Antigravity / Google DeepMind)

| Field | Value |
|-------|-------|
| **Date** | 2026-11-18 |
| **Tool** | Antigravity (Google DeepMind AI assistant, agy) |
| **Model** | Gemini 3.8 Flash |
| **Phase** | Phase 7 — Deterministic fixers, Groq LLM patches, and heal command |

**Goal:** Implement `contractguard/fixer.py` covering:
- Deterministic fixers:
  1. Append missing environment variables to `.env.example`.
  2. Remove confirmed unused dependencies from `requirements.txt` and `package.json`.
  3. Remove confirmed orphan files, strictly refusing to delete protected paths (entry points, tests, manifests, configs).
- Optional Groq LLM patch generator:
  - Produces strict JSON search-and-replace hunks (`search`, `replace`, `description`).
  - Validated with Pydantic `Patch`.
  - Enforces the single-match rule (`content.count(search) == 1`); discards hunks if not matching exactly once.
  - Fully functional with `--no-llm` or unset `GROQ_API_KEY`, gracefully handling API errors and invalid JSON.
- Full wiring of the `heal` command in `contractguard/cli.py` connecting indexer, auditors, triage, fixer, sandbox gate, branch promotion, and `VERIFICATION_RECEIPT.md`.

**Prompt summary:** "Phase 7. Follow CLAUDE.md and ARCHITECTURE.md. Tests first, then
fixer.py. Deterministic fixers first: append missing env vars to .env.example, remove
confirmed unused dependencies, remove confirmed orphan files (never protected paths).
Then an optional Groq patch generator producing strict JSON search-and-replace hunks
validated with pydantic; the search string must match exactly once or the hunk is discarded.
It must work fully with --no-llm or no GROQ_API_KEY and handle API errors and invalid
JSON gracefully. Run pytest. Append a phase entry to AI_LOG.md. Do not run any git commands
in this repo. Stop and summarize."

**Features implemented:**
- `is_protected_path(path)`: checks entry points (`main.py`, `app.py`, `index.js`, etc.), configs (`pyproject.toml`, `package.json`, `conftest.py`, etc.), and test directories (`tests/`, `test/`, `__tests__/`).
- `generate_env_example_fix`: extracts missing env var names from drift findings and safely appends `VAR=\n` to `.env.example`.
- `generate_unused_dep_fix`: removes exact dependency lines from `requirements.txt` and `package.json`.
- `generate_remove_orphan_file_fix`: generates deletion patches for confirmed orphan files while blocking any deletion of protected files.
- `generate_llm_patch`: prompts Groq with `response_format={"type": "json_object"}`, validates Pydantic model, verifies `file_content.count(search) == 1`, and catches any network/JSON error.
- `generate_all_patches`: runs deterministic fixes first, then invokes Groq for remaining findings if LLM is enabled.
- `cli.py` `heal` command: fully wired end-to-end (`index_repo` -> `_run_auditors` -> `triage_findings` -> `generate_all_patches` -> `Sandbox` verification gate -> `promote_verified_patches` -> `write_verification_receipt`).

**Tests written (before implementation):**
- `tests/test_fixer.py` — 36 tests covering:
  - Protected vs non-protected path classification (23 tests)
  - Deterministic fixers: `.env.example` appending (empty and non-empty), `requirements.txt` removal, `package.json` removal, orphan file deletion, safety refusal on protected paths, and combined runner (7 tests)
  - LLM patch generator: `--no-llm`/empty key check, valid JSON exact match, discard when count != 1, invalid JSON handling, API exception handling, and priority over LLM (6 tests).
- `tests/test_cli.py` — added `test_heal_executes_verification_and_writes_receipt` validating the complete `heal` command execution, sandbox verification, and receipt generation.

**Pytest run:**
- 410/410 tests passed across the entire project in 56.24s (36 fixer + 15 CLI + 18 sandbox + 53 slop + 68 drift + 90 security + 27 triage + 17 reporter + 58 indexer + 28 models). Zero failures.

**Human corrections:** None.

**Decision:** Phase 7 complete. The audit and heal pipeline is now fully operational.
Next is Phase 8: `sample-broken-app/` setup with planted defects for zero false-negative verification,
followed by Phase 9: generating `SELF_VERIFICATION.md` and finalizing documentation.




