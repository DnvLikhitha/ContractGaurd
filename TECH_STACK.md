# ContractGuard: Tech Stack

## Language and runtime
- Python 3.10+

## Dependencies (`requirements.txt`)
```text
click>=8.1.7          # CLI framework
rich>=13.7.0          # Terminal tables and progress
pydantic>=2.7.0       # Finding/Patch schemas and LLM JSON validation
pyyaml>=6.0.1         # Parse compose/config/OpenAPI
groq>=0.9.0           # Optional: fast LLM patch synthesis and explanations
scikit-learn>=1.5.0   # Optional (P1): TF-IDF for README-to-code matching
```

## Dev dependencies
```text
pytest>=8.0
pytest-cov
ruff            # lint
```

## Standard library used heavily
`ast` (Python import graph), `re` (cross-language patterns), `subprocess` (git and verifiers), `tempfile`, `pathlib`, `json`, `shutil`

## External tools (detected at runtime, never required)
`git`, `pytest`, `node`/`npm`, `go`, `cargo`

## Why these choices
| Choice | Reason |
|--------|--------|
| Click | Simple, testable CLI with minimal code |
| Rich | Polished demo output for the video |
| Pydantic | Strict validation for findings and untrusted LLM output |
| Groq | Fast, low-latency inference; optional so the tool works with no key |
| `ast` plus regex | Accurate for Python, lightweight and architecture-agnostic for everything else |
| scikit-learn | Kept optional; symbol matching alone covers the P0 drift case |

## Packaging
`pyproject.toml` with console script `contractguard`, so both `contractguard audit .` and `python -m contractguard audit .` work.

## Testing
- Pytest unit tests per auditor using fixture snippets
- Integration test: run `audit` and `heal` against `sample-broken-app`
- Self-run: ContractGuard on its own repo produces `SELF_VERIFICATION.md`

## Config
`GROQ_API_KEY` env var (optional); `--no-llm` flag forces deterministic-only mode.
