"""Fixer: generates deterministic fixes and optional LLM patches."""

from contractguard.models import Finding, Patch
from typing import Optional


# Protected paths that should never be deleted
PROTECTED_PATHS = {
    "main.py", "__main__.py", "cli.py", "app.py", "manage.py",
    "index.js", "index.ts", "main.js", "main.ts",
    "server.py", "server.js", "server.ts",
    "wsgi.py", "asgi.py",
    "conftest.py", "pytest.ini", "pyproject.toml", "setup.py", "setup.cfg",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum",
    "pom.xml", "build.gradle", "build.gradle.kts",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ".github", ".gitlab", ".circleci",
}


def is_protected_path(filepath: str) -> bool:
    """Check if a path is protected (entry point, test, config)."""
    name = filepath.split("/")[-1]
    if name in PROTECTED_PATHS:
        return True
    # Protect test directories
    if "test" in filepath.split("/") or "spec" in filepath.split("/"):
        return True
    # Protect config directories
    if any(d in filepath for d in [".github", ".gitlab", ".circleci", ".vscode", ".idea"]):
        return True
    return False


def generate_env_example_fix(finding: Finding) -> Optional[Patch]:
    """Generate fix for missing env var in .env.example."""
    if finding.category != "drift" or "missing in .env.example" not in finding.title.lower():
        return None

    # Extract variable name from evidence or title
    # TODO: Implement proper extraction
    var_name = "MISSING_VAR"

    return Patch(
        finding_id=finding.id,
        file=".env.example",
        search="",
        replace=f"{var_name}=\n",
        description=f"Add missing environment variable {var_name} to .env.example",
    )


def generate_remove_unused_import_fix(finding: Finding) -> Optional[Patch]:
    """Generate fix for unused import."""
    if finding.category != "slop" or "unused import" not in finding.title.lower():
        return None

    # TODO: Implement
    return None


def generate_deterministic_fixes(findings: list[Finding]) -> list[Patch]:
    """Generate all deterministic fixes for findings."""
    patches = []
    for finding in findings:
        # Try each fixer
        for fixer in [generate_env_example_fix, generate_remove_unused_import_fix]:
            patch = fixer(finding)
            if patch:
                patches.append(patch)
                break
    return patches


def generate_llm_patch(finding: Finding, api_key: str) -> Optional[Patch]:
    """Generate a patch using Groq LLM (optional)."""
    # TODO: Implement LLM patch generation with strict JSON validation
    # Must validate: search string matches exactly once in file
    return None


def generate_all_patches(
    findings: list[Finding],
    use_llm: bool = False,
    api_key: Optional[str] = None
) -> list[Patch]:
    """Generate all patches (deterministic first, then LLM if enabled)."""
    patches = generate_deterministic_fixes(findings)

    if use_llm and api_key:
        for finding in findings:
            # Only use LLM for findings without deterministic fix
            if not any(p.finding_id == finding.id for p in patches):
                patch = generate_llm_patch(finding, api_key)
                if patch:
                    patches.append(patch)

    return patches