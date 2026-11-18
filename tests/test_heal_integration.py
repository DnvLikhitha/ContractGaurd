"""End-to-end integration tests for `contractguard heal`.

Tests the full pipeline on a temporary git repository:
1. audit
2. generate fixes
3. verify each in the sandbox
4. promote verified patches to the target branch (e.g. contractguard/clean)
5. write VERIFICATION_RECEIPT.md with finding ID, status, verifier command, output summary, and verification strength.
"""

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from contractguard.cli import cli


@pytest.fixture
def tiny_git_repo(tmp_path: Path) -> Path:
    """Create a tiny target git repository with intentional fixable drift and slop."""
    repo = tmp_path / "tiny_repo"
    repo.mkdir()

    # Initialize git repo in tmp_path (allowed: target repo)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)

    # 1. Source code with an undocumented env var read
    (repo / "app.py").write_text(
        "import os\n"
        "port = os.getenv('PORT_CONFIG')\n"
        "def compute(x):\n"
        "    return x * 2\n"
    )

    # 2. Test file ensuring verifier (pytest) is detected and green
    (repo / "test_app.py").write_text(
        "from app import compute\n"
        "def test_compute():\n"
        "    assert compute(10) == 20\n"
    )

    # 3. Contract file missing PORT_CONFIG
    (repo / ".env.example").write_text("DATABASE_URL=\n")

    # 4. Manifest with an unused dependency
    (repo / "requirements.txt").write_text("unused-mock-dep==0.9.9\n")

    # Initial commit
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, check=True, capture_output=True)

    return repo


class TestHealEndToEnd:
    def test_heal_end_to_end_pipeline(self, tiny_git_repo):
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["heal", str(tiny_git_repo), "--branch", "contractguard/clean", "--no-llm"],
        )

        assert result.exit_code == 0, result.output

        # 1. Verify VERIFICATION_RECEIPT.md was created
        receipt_file = tiny_git_repo / "VERIFICATION_RECEIPT.md"
        assert receipt_file.exists(), "VERIFICATION_RECEIPT.md was not written"

        receipt_text = receipt_file.read_text(encoding="utf-8")

        # 2. Verify receipt contains all required elements:
        # Finding, Status (VERIFIED), Verifier Command, Output Summary, Strength
        assert "VERIFIED" in receipt_text
        assert "TESTS_PASSED" in receipt_text
        assert "Verifier Command" in receipt_text
        assert "Output Summary" in receipt_text
        assert "pytest" in receipt_text

        # 3. Verify git branch promotion to contractguard/clean
        branches = subprocess.run(
            ["git", "branch"],
            cwd=tiny_git_repo,
            capture_output=True,
            text=True,
        ).stdout
        assert "contractguard/clean" in branches

        # 4. Verify that verified patches were applied to contractguard/clean
        # Missing env var PORT_CONFIG must now be in .env.example
        env_content = (tiny_git_repo / ".env.example").read_text(encoding="utf-8")
        assert "PORT_CONFIG=" in env_content

        # Unused dependency must have been removed from requirements.txt
        req_content = (tiny_git_repo / "requirements.txt").read_text(encoding="utf-8")
        assert "unused-mock-dep" not in req_content

        # 5. Verify tests still pass on the clean branch
        import sys
        test_run = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=tiny_git_repo,
            capture_output=True,
            text=True,
        )
        assert test_run.returncode == 0

    def test_heal_non_git_repo_fallback(self, tmp_path):
        repo = tmp_path / "plain_dir"
        repo.mkdir()

        (repo / "app.py").write_text("import os\nx = os.getenv('PLAIN_ENV_VAR')\n")
        (repo / ".env.example").write_text("EXISTING=1\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["heal", str(repo), "--no-llm"])
        assert result.exit_code == 0

        # Receipt written
        assert (repo / "VERIFICATION_RECEIPT.md").exists()
        # Env healed
        assert "PLAIN_ENV_VAR=" in (repo / ".env.example").read_text(encoding="utf-8")
