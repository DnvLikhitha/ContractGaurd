# ContractGuard

> **Hackathon:** Mycrobo Arena · Nov 17-18, 2026 · Track: AI triage

ContractGuard treats a repository as a **living contract**. It cross-checks
contract files (README, `.env.example`, manifests, compose/config) against
source code, triages findings by severity and confidence, then proposes fixes
and **verifies each one in an isolated shadow git worktree** before keeping it.

---

## Quick start

```bash
pip install -e .
contractguard audit <path>          # ranked findings report
contractguard heal  <path>          # apply + verify fixes
python -m contractguard audit <path> --json   # JSON output
```

## Features (planned)

| ID | Feature | Priority |
|----|---------|----------|
| F1 | Ranked findings report (Rich + `--json`) | P0 |
| F2 | Security auditor: secrets, `DEBUG=True`, CORS `*`, weak hashes | P0 |
| F3 | Env-contract drift detection | P0 |
| F4 | Slop auditor: orphaned files, unused deps | P0 |
| F5 | `heal` with shadow-worktree verification gate | P0 |
| F6 | `VERIFICATION_RECEIPT.md` with per-fix verification strength | P0 |

## Limitations

> *To be filled in after the hackathon demo.*

## Development

```bash
python -m pytest
```

## AI-assisted development

This project was built with AI assistance. See [`AI_LOG.md`](AI_LOG.md) for a
full log of every session, model, prompt, and human corrections.
