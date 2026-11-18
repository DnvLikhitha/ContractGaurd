"""Integration tests verifying sample-broken-app seeded issues and rollback gate."""

import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from contractguard.cli import cli
from contractguard.indexer import index_repo
from contractguard.cli import _run_auditors
from contractguard.triage import triage_findings


@pytest.fixture
def sample_app_copy(tmp_path: Path) -> Path:
    """Make an isolated copy of sample-broken-app in tmp_path."""
    src = Path(__file__).parent.parent / "sample-broken-app"
    dst = tmp_path / "sample-broken-app"
    shutil.copytree(src, dst)

    # Initialize a git repo so sandbox test and rollback can be verified
    subprocess.run(["git", "init"], cwd=dst, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=dst, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=dst, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=dst, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init sample app"], cwd=dst, check=True, capture_output=True)

    return dst


class TestSampleBrokenApp:
    def test_all_seeded_issues_detected(self):
        """Verify zero false negatives on all seeded defects."""
        sample_path = Path(__file__).parent.parent / "sample-broken-app"
        contract_files, source_files = index_repo(sample_path)
        raw = _run_auditors(source_files, contract_files)
        findings = triage_findings(raw)

        titles = [f.title for f in findings]
        files = [f.file for f in findings]

        # 1. Hardcoded fake secret
        assert any("API" in t or "Secret" in t for t in titles)
        # 2. DEBUG=True
        assert any("DEBUG=True" in t for t in titles)
        # 3. CORS wildcard
        assert any("CORS Wildcard" in t for t in titles)
        # 4. Env vars missing from .env.example
        assert any("APP_EXTRA_SECRET_TOKEN" in t for t in titles)
        assert any("NODE_SESSION_SECRET" in t for t in titles)
        # 5. Unused dependency
        assert any("unused-xml-parser" in t for t in titles)
        assert any("unused-node-lib" in t for t in titles)
        assert any("legacy-compat-dep" in t for t in titles)
        # 6. Orphan file
        assert any("orphan_service.py" in f for f in files)
        # 7. Documented endpoint missing from code
        assert any("/api/v1/nonexistent_stats" in t for t in titles)

    def test_heal_rolls_back_bad_fix_and_keeps_good_fixes(self, sample_app_copy):
        """Verify the key differentiator: sandbox rolls back the tempting fix that breaks tests."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["heal", str(sample_app_copy), "--branch", "contractguard/clean", "--no-llm"],
        )

        assert result.exit_code == 0, result.output

        receipt_file = sample_app_copy / "VERIFICATION_RECEIPT.md"
        assert receipt_file.exists()
        receipt_text = receipt_file.read_text(encoding="utf-8")

        # 1. Check that VERIFIED and ROLLED_BACK are both in the receipt
        assert "VERIFIED" in receipt_text
        assert "ROLLED_BACK" in receipt_text

        # 2. Check that the tempting fix (removing legacy-compat-dep) was rolled back
        assert "legacy-compat-dep" in receipt_text
        # legacy-compat-dep must STILL be in requirements.txt because the patch was rolled back
        req_content = (sample_app_copy / "requirements.txt").read_text(encoding="utf-8")
        assert "legacy-compat-dep" in req_content, "Tempting fix was kept when it should have been rolled back!"

        # 3. Check that safe fixes were verified and kept:
        # e.g., APP_EXTRA_SECRET_TOKEN was added to .env.example
        env_content = (sample_app_copy / ".env.example").read_text(encoding="utf-8")
        assert "APP_EXTRA_SECRET_TOKEN=" in env_content

        # 4. Working tests still pass on sample_app_copy
        import sys
        test_res = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=sample_app_copy,
            capture_output=True,
            text=True,
        )
        assert test_res.returncode == 0, test_res.stdout
