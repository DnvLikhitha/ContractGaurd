"""Drift auditor: detects env-contract drift and README-to-code drift.

This module will:
- Extract env vars used in code (os.getenv, process.env, etc.)
- Compare against .env.example, docker-compose, GitHub Actions
- Check README documented endpoints/commands against actual code
"""

from contractguard.models import Finding, ContractFiles, IndexedFile


def extract_env_vars_from_python(content: str) -> set[str]:
    """Extract environment variable names from Python code."""
    # TODO: Implement AST-based extraction for os.getenv, os.environ, etc.
    return set()


def extract_env_vars_from_js(content: str) -> set[str]:
    """Extract environment variable names from JavaScript/TypeScript code."""
    # TODO: Implement regex-based extraction for process.env, import.meta.env, etc.
    return set()


def extract_env_vars_from_file(file: IndexedFile) -> set[str]:
    """Extract environment variables from a source file based on its language."""
    if file.language == "python":
        return extract_env_vars_from_python(file.content)
    elif file.language in ("javascript", "typescript"):
        return extract_env_vars_from_js(file.content)
    # TODO: Add more languages
    return set()


def parse_env_example(content: str) -> set[str]:
    """Parse variable names from .env.example file."""
    # TODO: Implement parsing
    return set()


def parse_docker_compose_env(content: str) -> set[str]:
    """Parse environment variables from docker-compose.yml."""
    # TODO: Implement YAML parsing
    return set()


def check_env_drift(
    source_files: list[IndexedFile],
    contract_files: ContractFiles
) -> list[Finding]:
    """Check for environment variable drift between code and contract files."""
    # TODO: Implement drift detection
    # 1. Collect all env vars used in source code
    # 2. Collect all env vars defined in contract files
    # 3. Find missing in .env.example (code uses but not documented)
    # 4. Find unused in .env.example (documented but not used)
    return []


def check_readme_drift(
    source_files: list[IndexedFile],
    contract_files: ContractFiles
) -> list[Finding]:
    """Check for README-to-code drift (documented endpoints/commands missing in code)."""
    # TODO: Implement README endpoint/command extraction and matching
    return []


def audit_drift(
    source_files: list[IndexedFile],
    contract_files: ContractFiles
) -> list[Finding]:
    """Main entry point for drift auditor."""
    findings = []
    findings.extend(check_env_drift(source_files, contract_files))
    findings.extend(check_readme_drift(source_files, contract_files))
    return findings