"""Tests for Fixer — deterministic fixers and optional LLM patch generator.

Tests are written BEFORE implementation per CLAUDE.md rules.
Fixtures use inline snippets and temporary directories.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from contractguard.fixer import (
    is_protected_path,
    generate_env_example_fix,
    generate_unused_dep_fix,
    generate_remove_orphan_file_fix,
    generate_deterministic_fixes,
    generate_llm_patch,
    generate_all_patches,
)
from contractguard.models import Finding, Patch, Category, Severity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _drift_finding(var_name: str, file: str = ".env.example") -> Finding:
    return Finding(
        id="DRF-001",
        category=Category.DRIFT,
        severity=Severity.HIGH,
        confidence=0.85,
        file=file,
        line=None,
        title=f"Env var '{var_name}' used in code but absent from contract files",
        evidence=f"{var_name} is used in source code but not declared in {file}",
        suggested_fix=f"Add '{var_name}=<description>' to {file}",
    )


def _unused_dep_finding(dep: str, file: str = "requirements.txt") -> Finding:
    return Finding(
        id="SLP-002",
        category=Category.SLOP,
        severity=Severity.LOW,
        confidence=0.80,
        file=file,
        line=None,
        title=f"Unused dependency '{dep}' in {file}",
        evidence=f"'{dep}' is declared in {file} but never imported in source files",
        suggested_fix=f"Remove '{dep}' from {file}",
    )


def _orphan_file_finding(file: str) -> Finding:
    return Finding(
        id="SLP-001",
        category=Category.SLOP,
        severity=Severity.LOW,
        confidence=0.85,
        file=file,
        line=None,
        title=f"Orphaned file '{file}' is never imported",
        evidence=f"No other file in the repository imports '{file}'",
        suggested_fix=f"Import '{file}' or remove it if obsolete",
    )


# ---------------------------------------------------------------------------
# Protected paths tests
# ---------------------------------------------------------------------------

class TestProtectedPaths:
    @pytest.mark.parametrize("path", [
        "main.py",
        "__main__.py",
        "app.py",
        "cli.py",
        "index.js",
        "index.ts",
        "main.js",
        "server.py",
        "setup.py",
        "conftest.py",
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "Dockerfile",
        "docker-compose.yml",
        "tests/test_something.py",
        "test/helper.py",
        "__tests__/app.test.js",
        ".github/workflows/ci.yml",
    ])
    def test_protected_paths_identified(self, path):
        assert is_protected_path(path) is True

    @pytest.mark.parametrize("path", [
        "src/dead_helper.py",
        "lib/abandoned_component.js",
        "legacy/unused_module.py",
        "utils/orphan_tool.ts",
    ])
    def test_non_protected_paths(self, path):
        assert is_protected_path(path) is False


# ---------------------------------------------------------------------------
# Deterministic fixers tests
# ---------------------------------------------------------------------------

class TestDeterministicFixers:
    def test_env_example_fix_appends_to_existing_file(self, tmp_path):
        env_ex = tmp_path / ".env.example"
        env_ex.write_text("DATABASE_URL=\nSECRET_KEY=\n")

        finding = _drift_finding("PORT")
        patch = generate_env_example_fix(finding, repo_path=tmp_path)

        assert patch is not None
        assert patch.file == ".env.example"
        assert patch.finding_id == "DRF-001"
        # Search string must match exactly once in existing content
        content = env_ex.read_text()
        assert content.count(patch.search) == 1
        # When applied, PORT is added
        new_content = content.replace(patch.search, patch.replace, 1)
        assert "PORT=" in new_content

    def test_env_example_fix_when_file_is_empty(self, tmp_path):
        env_ex = tmp_path / ".env.example"
        env_ex.write_text("")

        finding = _drift_finding("API_KEY")
        patch = generate_env_example_fix(finding, repo_path=tmp_path)

        assert patch is not None
        assert patch.file == ".env.example"
        content = env_ex.read_text()
        assert content.count(patch.search) == 1
        new_content = content.replace(patch.search, patch.replace, 1)
        assert "API_KEY=" in new_content

    def test_unused_dependency_fix_requirements_txt(self, tmp_path):
        reqs = tmp_path / "requirements.txt"
        reqs.write_text("requests==2.28.1\nunused-mock-dep==1.0.0\nflask>=2.0\n")

        finding = _unused_dep_finding("unused-mock-dep", file="requirements.txt")
        patch = generate_unused_dep_fix(finding, repo_path=tmp_path)

        assert patch is not None
        assert patch.file == "requirements.txt"
        content = reqs.read_text()
        assert content.count(patch.search) == 1
        new_content = content.replace(patch.search, patch.replace, 1)
        assert "unused-mock-dep" not in new_content
        assert "requests==2.28.1" in new_content
        assert "flask>=2.0" in new_content

    def test_unused_dependency_fix_package_json(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text("""{
  "dependencies": {
    "express": "^4.18.2",
    "dead-pkg": "^1.0.0"
  }
}""")

        finding = _unused_dep_finding("dead-pkg", file="package.json")
        patch = generate_unused_dep_fix(finding, repo_path=tmp_path)

        assert patch is not None
        assert patch.file == "package.json"
        content = pkg.read_text()
        assert content.count(patch.search) == 1
        new_content = content.replace(patch.search, patch.replace, 1)
        assert "dead-pkg" not in new_content
        assert "express" in new_content

    def test_remove_orphan_file_fix(self, tmp_path):
        orphan = tmp_path / "src" / "dead_code.py"
        orphan.parent.mkdir(parents=True, exist_ok=True)
        orphan.write_text("def unused(): pass\n")

        finding = _orphan_file_finding("src/dead_code.py")
        patch = generate_remove_orphan_file_fix(finding, repo_path=tmp_path)

        assert patch is not None
        assert patch.file == "src/dead_code.py"
        assert patch.replace == ""
        # Search must be the entire file content so removing it deletes/empties
        content = orphan.read_text()
        assert patch.search == content

    def test_orphan_file_fix_refuses_protected_path(self, tmp_path):
        finding = _orphan_file_finding("main.py")
        patch = generate_remove_orphan_file_fix(finding, repo_path=tmp_path)
        # MUST NEVER generate a patch to delete a protected file
        assert patch is None

    def test_generate_deterministic_fixes_combines_all(self, tmp_path):
        (tmp_path / ".env.example").write_text("DB=1\n")
        (tmp_path / "requirements.txt").write_text("unused-pkg==1.0\n")
        (tmp_path / "legacy.py").write_text("pass\n")

        findings = [
            _drift_finding("REDIS_URL"),
            _unused_dep_finding("unused-pkg"),
            _orphan_file_finding("legacy.py"),
        ]

        patches = generate_deterministic_fixes(findings, repo_path=tmp_path)
        assert len(patches) == 3
        patch_files = [p.file for p in patches]
        assert ".env.example" in patch_files
        assert "requirements.txt" in patch_files
        assert "legacy.py" in patch_files


# ---------------------------------------------------------------------------
# Groq LLM patch generator tests
# ---------------------------------------------------------------------------

class TestLLMPatchGenerator:
    def test_llm_patch_disabled_with_no_llm_or_empty_key(self, tmp_path):
        finding = Finding(
            id="SEC-001",
            category=Category.SECURITY,
            severity=Severity.HIGH,
            confidence=0.90,
            file="app.py",
            line=10,
            title="DEBUG=True in production",
            evidence="DEBUG = True",
            suggested_fix="Set DEBUG = False",
        )
        assert generate_llm_patch(finding, repo_path=tmp_path, api_key=None) is None
        assert generate_llm_patch(finding, repo_path=tmp_path, api_key="") is None

    def test_llm_patch_valid_json_exact_match(self, tmp_path):
        target = tmp_path / "app.py"
        target.write_text("DEBUG = True\nrun_app()\n")

        finding = Finding(
            id="SEC-001",
            category=Category.SECURITY,
            severity=Severity.HIGH,
            confidence=0.90,
            file="app.py",
            line=1,
            title="DEBUG=True in production",
            evidence="DEBUG = True",
            suggested_fix="Set DEBUG = False",
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"search": "DEBUG = True", "replace": "DEBUG = False", "description": "Disable debug mode"}'))
        ]
        mock_client.chat.completions.create.return_value = mock_response

        patch = generate_llm_patch(finding, repo_path=tmp_path, api_key="mock_key", client=mock_client)
        assert patch is not None
        assert patch.finding_id == "SEC-001"
        assert patch.file == "app.py"
        assert patch.search == "DEBUG = True"
        assert patch.replace == "DEBUG = False"

    def test_llm_patch_discarded_if_search_not_matching_once(self, tmp_path):
        target = tmp_path / "app.py"
        target.write_text("DEBUG = True\nDEBUG = True\n")  # Appears twice!

        finding = Finding(
            id="SEC-001",
            category=Category.SECURITY,
            severity=Severity.HIGH,
            confidence=0.90,
            file="app.py",
            line=1,
            title="DEBUG=True in production",
            evidence="DEBUG = True",
            suggested_fix="Set DEBUG = False",
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"search": "DEBUG = True", "replace": "DEBUG = False", "description": "Disable debug"}'))
        ]
        mock_client.chat.completions.create.return_value = mock_response

        patch = generate_llm_patch(finding, repo_path=tmp_path, api_key="mock_key", client=mock_client)
        # Search string matched twice -> MUST BE DISCARDED per ARCHITECTURE.md rule
        assert patch is None

    def test_llm_patch_handles_invalid_json_gracefully(self, tmp_path):
        target = tmp_path / "app.py"
        target.write_text("x = 1\n")

        finding = Finding(
            id="SEC-002",
            category=Category.SECURITY,
            severity=Severity.HIGH,
            confidence=0.90,
            file="app.py",
            line=1,
            title="Test finding",
            evidence="x = 1",
            suggested_fix="x = 2",
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='Sorry, here is the fix: search for x = 1 and replace with x = 2'))
        ]
        mock_client.chat.completions.create.return_value = mock_response

        patch = generate_llm_patch(finding, repo_path=tmp_path, api_key="mock_key", client=mock_client)
        assert patch is None

    def test_llm_patch_handles_api_exception_gracefully(self, tmp_path):
        target = tmp_path / "app.py"
        target.write_text("x = 1\n")

        finding = Finding(
            id="SEC-003",
            category=Category.SECURITY,
            severity=Severity.HIGH,
            confidence=0.90,
            file="app.py",
            line=1,
            title="Test finding",
            evidence="x = 1",
            suggested_fix="x = 2",
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("Groq API rate limit or network error")

        patch = generate_llm_patch(finding, repo_path=tmp_path, api_key="mock_key", client=mock_client)
        assert patch is None

    def test_generate_all_patches_priority(self, tmp_path):
        """Deterministic fixes first, LLM only invoked for findings without a deterministic fix."""
        (tmp_path / ".env.example").write_text("FOO=1\n")
        (tmp_path / "app.py").write_text("DEBUG = True\n")

        drift = _drift_finding("BAR")
        sec = Finding(
            id="SEC-001",
            category=Category.SECURITY,
            severity=Severity.HIGH,
            confidence=0.90,
            file="app.py",
            line=1,
            title="DEBUG=True",
            evidence="DEBUG = True",
            suggested_fix="DEBUG = False",
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"search": "DEBUG = True", "replace": "DEBUG = False", "description": "Fix debug"}'))
        ]
        mock_client.chat.completions.create.return_value = mock_response

        # Call generate_all_patches with both
        patches = generate_all_patches(
            [drift, sec],
            repo_path=tmp_path,
            use_llm=True,
            api_key="mock_key",
            llm_client=mock_client,
        )

        assert len(patches) == 2
        # Deterministic patch for drift
        assert any(p.finding_id == "DRF-001" and p.file == ".env.example" for p in patches)
        # LLM patch for sec
        assert any(p.finding_id == "SEC-001" and p.file == "app.py" for p in patches)
        # LLM should ONLY have been called for SEC-001, not for DRF-001!
        assert mock_client.chat.completions.create.call_count == 1
