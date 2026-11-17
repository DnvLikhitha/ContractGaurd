"""
contractguard.cli
=================
Click command-line interface for ContractGuard.

Commands
--------
audit <path> [--json] [--no-llm]
    Walk *path*, run all auditors, triage findings, and display a ranked
    report in the terminal (Rich table) or as JSON on stdout.

heal <path> [--branch <name>] [--no-llm]
    Run ``audit`` then apply fixes one at a time inside a shadow git
    worktree, verify each with the detected test runner, keep or roll back,
    and promote verified patches to *branch* (default: contractguard/clean).

verify <path>
    Re-run only the verifier step against an already-patched shadow worktree
    (useful for debugging the gate in isolation).

This module is a stub – no logic is implemented yet.
"""

# TODO (Phase 1): implement using click>=8.1.7
