"""
contractguard.reporter
======================
Responsible for all human-readable and machine-readable output.

Responsibilities
----------------
- **Rich terminal report**: ranked findings table (severity colour-coded),
  summary counts, verification status badges.
- **JSON output**: ``--json`` flag writes a JSON array of serialised
  ``Finding`` and ``VerificationResult`` objects to stdout so callers can
  pipe the output to other tools.
- **VERIFICATION_RECEIPT.md**: written to the target repo root (or stdout)
  after a ``heal`` run; records per-patch status and verification *strength*
  (TESTS_PASSED | SYNTAX_ONLY | NO_VERIFIER).

This module is a stub – no logic is implemented yet.
"""

# TODO (Phase 2): implement using rich>=13.7.0 and pydantic>=2.7.0
