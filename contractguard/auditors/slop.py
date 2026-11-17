"""Slop auditor: detects orphaned files and unused dependencies.

This module will:
- Build import graph for Python/JS to find orphaned source files
- Compare package.json/pyproject.toml imports against actual usage
- Detect dead code and unused exports
"""

from contractguard.models import Finding, IndexedFile


def build_python_import_graph(source_files: list[IndexedFile]) -> dict[str, set[str]]:
    """Build import graph for Python files."""
    # TODO: Implement AST-based import graph
    return {}


def build_js_import_graph(source_files: list[IndexedFile]) -> dict[str, set[str]]:
    """Build import graph for JavaScript/TypeScript files."""
    # TODO: Implement regex/AST-based import graph
    return {}


def find_orphaned_files(
    source_files: list[IndexedFile],
    import_graph: dict[str, set[str]]
) -> list[Finding]:
    """Find source files that are not imported by any other file (except entry points)."""
    # TODO: Implement orphan detection
    # Entry points to protect: main.py, __main__.py, cli.py, app.py, index.js, etc.
    return []


def parse_python_dependencies(content: str) -> set[str]:
    """Parse dependencies from pyproject.toml / requirements.txt / setup.py."""
    # TODO: Implement parsing
    return set()


def parse_js_dependencies(content: str) -> set[str]:
    """Parse dependencies from package.json."""
    # TODO: Implement parsing
    return set()


def check_unused_dependencies(
    source_files: list[IndexedFile],
    contract_files_content: dict[str, str]
) -> list[Finding]:
    """Check for dependencies declared but not imported in code."""
    # TODO: Implement unused dependency detection
    return []


def audit_slop(
    source_files: list[IndexedFile],
    contract_files: dict[str, str]
) -> list[Finding]:
    """Main entry point for slop auditor."""
    findings = []
    # TODO: Implement
    return findings