"""
contractguard.cli
=================
Click command-line interface for ContractGuard.

Auditor registry
----------------
To add a new auditor, append one entry to AUDITOR_REGISTRY — that's it::

    AUDITOR_REGISTRY = [
        ("security", audit_security, "source"),
        ("drift",    audit_drift,    "both"),
        ("slop",     audit_slop,     "both"),
        # ("my-new",  audit_my_new,  "source"),  ← one-line change
    ]

Each entry is (name, callable, input_mode) where input_mode is:
  "source"   → callable(source_files)
  "contract" → callable(contract_files)
  "both"     → callable(source_files, contract_files)
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from contractguard.auditors.drift import audit_drift
from contractguard.auditors.security import audit_security
from contractguard.auditors.slop import audit_slop
from contractguard.indexer import index_repo
from contractguard.reporter import findings_to_json, print_findings_table
from contractguard.triage import triage_findings

_console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Auditor registry — add a new auditor here (one-line change)
# ---------------------------------------------------------------------------
# Each entry: (name, callable, input_mode)
#   "source"   → fn(source_files) -> list[Finding]
#   "contract" → fn(contract_files) -> list[Finding]
#   "both"     → fn(source_files, contract_files) -> list[Finding]

AUDITOR_REGISTRY: list[tuple[str, object, str]] = [
    ("security", audit_security, "source"),
    ("drift",    audit_drift,    "both"),
    ("slop",     audit_slop,     "both"),
]


def _run_auditors(
    source_files: list,
    contract_files: object,
    no_llm: bool = True,
) -> list:
    """Run every registered auditor and return the combined raw findings."""
    all_findings: list = []
    for name, fn, mode in AUDITOR_REGISTRY:
        try:
            if mode == "source":
                result = fn(source_files)  # type: ignore[call-arg]
            elif mode == "contract":
                result = fn(contract_files)  # type: ignore[call-arg]
            else:  # "both"
                result = fn(source_files, contract_files)  # type: ignore[call-arg]
            all_findings.extend(result)
        except Exception as exc:  # auditor must never crash the CLI
            _console.print(f"[yellow]⚠ Auditor '{name}' raised: {exc}[/yellow]")
    return all_findings


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def cli() -> None:
    """ContractGuard — audit a repository as a living contract."""


# ---------------------------------------------------------------------------
# audit command
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--json", "output_json", is_flag=True, default=False,
              help="Output findings as a JSON array instead of a Rich table.")
@click.option("--no-llm", is_flag=True, default=False,
              help="Disable LLM-assisted patch synthesis (deterministic only).")
def audit(path: Path, output_json: bool, no_llm: bool) -> None:
    """Audit the repository at PATH and report findings."""
    if not output_json:
        _console.print(f"[bold]ContractGuard[/bold] auditing [cyan]{path}[/cyan] …")

    contract_files, source_files = index_repo(path)

    if not output_json:
        _console.print(
            f"  Indexed [bold]{len(source_files)}[/bold] source files, "
            f"[bold]{len(contract_files.all_contract_files())}[/bold] contract files."
        )

    raw = _run_auditors(source_files, contract_files, no_llm=no_llm)
    findings = triage_findings(raw)

    if output_json:
        # JSON goes to stdout (clean, pipe-safe); no progress noise on stderr either
        click.echo(findings_to_json(findings))
    else:
        print_findings_table(findings)
        _console.print(
            f"\n[bold]Total:[/bold] [bold]{len(findings)}[/bold] finding(s) "
            f"after deduplication and ranking."
        )


# ---------------------------------------------------------------------------
# heal command (placeholder — Phase 3)
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--branch", default="contractguard/clean",
              help="Git branch to promote verified patches to.")
@click.option("--no-llm", is_flag=True, default=False,
              help="Disable LLM-assisted patch synthesis.")
def heal(path: Path, branch: str, no_llm: bool) -> None:
    """Apply fixes in a shadow worktree, verify each, and promote to BRANCH.

    [Phase 3 — not yet implemented]
    """
    _console.print(
        "[yellow]⚠ 'heal' is not yet implemented (Phase 3).[/yellow]\n"
        f"  Target: [cyan]{path}[/cyan]  Branch: [cyan]{branch}[/cyan]"
    )


# ---------------------------------------------------------------------------
# Entry point (also used by pyproject.toml console_scripts)
# ---------------------------------------------------------------------------

def main() -> None:
    """Console-script entry point."""
    cli()


if __name__ == "__main__":
    main()
