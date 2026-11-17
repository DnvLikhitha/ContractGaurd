"""
contractguard
=============
ContractGuard – audits a repository as a 'living contract'.

This package exposes the CLI via ``python -m contractguard`` and the
``contractguard`` console script defined in ``pyproject.toml``.

Public re-exports (populated as modules are implemented):
    - cli        Click application entry-point
    - models     Pydantic data model (Finding, Patch, VerificationResult)
    - indexer    Repo walker / file classifier
    - triage     Severity × confidence scorer
    - fixer      Deterministic and LLM-assisted patch generator
    - sandbox    Shadow worktree lifecycle and verification gate
    - reporter   Rich terminal output and VERIFICATION_RECEIPT.md writer
"""
