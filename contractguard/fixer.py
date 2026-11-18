"""Fixer: generates deterministic fixes and optional Groq LLM patches.

Architecture:
- Deterministic fixers first:
  1. Append missing env vars to .env.example
  2. Remove confirmed unused dependencies (requirements.txt / package.json)
  3. Remove confirmed orphaned files (NEVER delete protected paths)
- Optional Groq patch generator producing strict JSON search-and-replace hunks:
  - Validated with Pydantic
  - Search string must match exactly once or hunk is discarded
  - Degrades gracefully with --no-llm, missing GROQ_API_KEY, or API errors
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from contractguard.models import Finding, Patch

# ---------------------------------------------------------------------------
# Protected paths that should never be deleted
# ---------------------------------------------------------------------------
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
    ".gitignore", "README.md",
}

PROTECTED_DIRS = {
    "tests", "test", "__tests__", "spec", "specs",
    ".github", ".gitlab", ".circleci", ".vscode", ".idea",
}


def is_protected_path(filepath: str) -> bool:
    """Check if a path is protected (entry point, test, config)."""
    norm = filepath.replace("\\", "/").lower()
    p = Path(norm)
    name = p.name
    stem = p.stem

    # Check protected filenames
    if name in {x.lower() for x in PROTECTED_PATHS}:
        return True

    # Check protected directories
    parts = set(p.parts)
    if parts & PROTECTED_DIRS:
        return True

    # Check test and config patterns
    if stem.startswith("test_") or stem.endswith("_test"):
        return True
    if ".config" in name or ".test." in name or ".spec." in name:
        return True

    return False


# ---------------------------------------------------------------------------
# Deterministic Fixer 1: Append missing env var to .env.example
# ---------------------------------------------------------------------------

_VAR_NAME_RE = re.compile(r"['\"]([A-Za-z0-9_]+)['\"]|Env var ([A-Za-z0-9_]+)")


def generate_env_example_fix(
    finding: Finding,
    repo_path: Optional[Path] = None,
) -> Optional[Patch]:
    """Generate fix for missing env var in .env.example."""
    category = getattr(finding.category, "value", str(finding.category)).lower()
    if category != "drift" and "drift" not in category:
        return None

    title_lower = finding.title.lower()
    if "absent" not in title_lower and "missing" not in title_lower:
        return None

    # Extract variable name from title or evidence
    m = _VAR_NAME_RE.search(finding.title) or _VAR_NAME_RE.search(finding.evidence)
    if not m:
        return None
    var_name = m.group(1) or m.group(2)
    if not var_name:
        return None

    target_rel = ".env.example"
    content = ""
    if repo_path:
        target_file = repo_path / target_rel
        if target_file.exists():
            content = target_file.read_text(encoding="utf-8", errors="replace")

    # If file is empty, search string is ""
    if not content:
        return Patch(
            finding_id=finding.id,
            file=target_rel,
            search="",
            replace=f"{var_name}=\n",
            description=f"Add missing environment variable {var_name} to {target_rel}",
        )

    # If file has content, search is full content and replace appends to it
    # S.count(S) is guaranteed to be 1 for any non-empty string S
    suffix = f"{var_name}=\n"
    if not content.endswith("\n"):
        new_content = content + "\n" + suffix
    else:
        new_content = content + suffix

    return Patch(
        finding_id=finding.id,
        file=target_rel,
        search=content,
        replace=new_content,
        description=f"Add missing environment variable {var_name} to {target_rel}",
    )


# ---------------------------------------------------------------------------
# Deterministic Fixer 2: Remove confirmed unused dependency
# ---------------------------------------------------------------------------

_DEP_NAME_RE = re.compile(r"['\"]([a-zA-Z0-9_.\-]+)['\"]")


def generate_unused_dep_fix(
    finding: Finding,
    repo_path: Optional[Path] = None,
) -> Optional[Patch]:
    """Generate fix to remove unused dependency from requirements.txt or package.json."""
    category = getattr(finding.category, "value", str(finding.category)).lower()
    if "slop" not in category or "unused dependency" not in finding.title.lower():
        return None

    m = _DEP_NAME_RE.search(finding.title)
    if not m:
        return None
    dep_name = m.group(1).strip()

    target_rel = finding.file
    if not repo_path:
        return None

    target_file = repo_path / target_rel
    if not target_file.exists():
        return None

    content = target_file.read_text(encoding="utf-8", errors="replace")
    filename = target_file.name.lower()

    # 1. requirements.txt
    if filename.startswith("requirements") and filename.endswith((".txt", ".in")):
        pattern = re.compile(
            rf"(?m)^[ \t]*({re.escape(dep_name)}(?:[><=~!~;\[].*)?)\r?\n?",
            re.IGNORECASE,
        )
        match = pattern.search(content)
        if match and content.count(match.group(0)) == 1:
            return Patch(
                finding_id=finding.id,
                file=target_rel,
                search=match.group(0),
                replace="",
                description=f"Remove unused dependency '{dep_name}' from {target_rel}",
            )

    # 2. package.json
    elif filename == "package.json":
        pattern = re.compile(
            rf'([ \t]*"{re.escape(dep_name)}"[ \t]*:[ \t]*"[^"]*",?[ \t]*\r?\n?)',
            re.IGNORECASE,
        )
        match = pattern.search(content)
        if match and content.count(match.group(0)) == 1:
            return Patch(
                finding_id=finding.id,
                file=target_rel,
                search=match.group(0),
                replace="",
                description=f"Remove unused dependency '{dep_name}' from package.json",
            )

    return None


# ---------------------------------------------------------------------------
# Deterministic Fixer 3: Remove confirmed orphan file
# ---------------------------------------------------------------------------

def generate_remove_orphan_file_fix(
    finding: Finding,
    repo_path: Optional[Path] = None,
) -> Optional[Patch]:
    """Generate fix to delete an orphaned file (NEVER deletes protected paths)."""
    category = getattr(finding.category, "value", str(finding.category)).lower()
    if "slop" not in category or "orphaned file" not in finding.title.lower():
        return None

    target_rel = finding.file

    # Hard safety guard: NEVER delete protected files
    if is_protected_path(target_rel):
        return None

    content = ""
    if repo_path:
        target_file = repo_path / target_rel
        if not target_file.exists():
            return None
        content = target_file.read_text(encoding="utf-8", errors="replace")

    return Patch(
        finding_id=finding.id,
        file=target_rel,
        search=content,
        replace="",
        description=f"Remove orphaned file '{target_rel}'",
    )


# ---------------------------------------------------------------------------
# Deterministic runner
# ---------------------------------------------------------------------------

def generate_deterministic_fixes(
    findings: list[Finding],
    repo_path: Optional[Path] = None,
) -> list[Patch]:
    """Generate all deterministic fixes for findings."""
    patches: list[Patch] = []

    fixers = [
        generate_env_example_fix,
        generate_unused_dep_fix,
        generate_remove_orphan_file_fix,
    ]

    for finding in findings:
        for fixer in fixers:
            patch = fixer(finding, repo_path=repo_path)
            if patch:
                patches.append(patch)
                break

    return patches


# ---------------------------------------------------------------------------
# Optional Groq LLM Patch Generator
# ---------------------------------------------------------------------------

def generate_llm_patch(
    finding: Finding,
    repo_path: Optional[Path] = None,
    api_key: Optional[str] = None,
    client: Any = None,
) -> Optional[Patch]:
    """Generate a patch using Groq LLM with strict JSON validation.

    Ensures the search string matches exactly once in the target file,
    otherwise the hunk is discarded.
    """
    if not api_key and client is None:
        return None

    if not repo_path:
        return None

    target_file = repo_path / finding.file
    if not target_file.exists() or not target_file.is_file():
        return None

    file_content = target_file.read_text(encoding="utf-8", errors="replace")

    # Set up client
    groq_client = client
    if groq_client is None:
        try:
            from groq import Groq
            groq_client = Groq(api_key=api_key)
        except Exception:
            return None

    prompt = (
        f"File: {finding.file}\n"
        f"Issue title: {finding.title}\n"
        f"Evidence: {finding.evidence}\n"
        f"Suggested fix: {finding.suggested_fix or 'Fix the issue'}\n\n"
        f"Target file content:\n```\n{file_content}\n```\n\n"
        "Generate a strict JSON search-and-replace hunk. Requirements:\n"
        "1. 'search' must be the exact substring in the file to replace (must match exactly once).\n"
        "2. 'replace' must be the replacement string.\n"
        "3. 'description' must be a concise summary of the change.\n"
        "Respond ONLY with valid JSON."
    )

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a software repair assistant. You output ONLY valid JSON search-and-replace objects.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        content_str = response.choices[0].message.content
        if not content_str:
            return None

        data = json.loads(content_str)
        search_str = data.get("search")
        replace_str = data.get("replace")
        desc = data.get("description", f"Fix {finding.title}")

        if not isinstance(search_str, str) or not isinstance(replace_str, str):
            return None

        # STRICT RULE: Search string must match exactly once
        if file_content.count(search_str) != 1:
            return None

        return Patch(
            finding_id=finding.id,
            file=finding.file,
            search=search_str,
            replace=replace_str,
            description=desc,
        )
    except Exception:
        # Gracefully handle API errors, network timeouts, invalid JSON
        return None


# ---------------------------------------------------------------------------
# All Patches Runner
# ---------------------------------------------------------------------------

def generate_all_patches(
    findings: list[Finding],
    repo_path: Optional[Path] = None,
    use_llm: bool = False,
    api_key: Optional[str] = None,
    llm_client: Any = None,
) -> list[Patch]:
    """Generate all patches: deterministic first, then optional LLM for remainder."""
    effective_key = api_key or os.getenv("GROQ_API_KEY")
    patches = generate_deterministic_fixes(findings, repo_path=repo_path)

    # For findings without a deterministic fix, try LLM if enabled
    if use_llm and (effective_key or llm_client is not None):
        patched_finding_ids = {p.finding_id for p in patches}
        for finding in findings:
            if finding.id not in patched_finding_ids:
                patch = generate_llm_patch(
                    finding,
                    repo_path=repo_path,
                    api_key=effective_key,
                    client=llm_client,
                )
                if patch:
                    patches.append(patch)
                    patched_finding_ids.add(finding.id)

    return patches
