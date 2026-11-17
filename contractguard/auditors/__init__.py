"""
contractguard.auditors
======================
Sub-package containing the three auditor modules:

- security  Regex and AST checks for secrets and insecure defaults
- drift     Env-var contract vs code mismatches; README-to-code drift
- slop      Orphaned files, unused dependencies

Each auditor exposes a single function::

    def audit(index: RepoIndex) -> list[Finding]: ...

This module is a stub – no logic is implemented yet.
"""
