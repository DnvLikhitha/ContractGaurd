"""Tests for Sandbox and Verification Gate.

Tests are written BEFORE implementation per CLAUDE.md rules.
Uses temporary git repo fixtures created in tmp_path.
NEVER runs git commands against the project's own repository.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from contractguard.models import FixStatus, Patch, VerificationStrength
from contractguard.sandbox import Sandbox, SandboxError, VerifierDetector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def target_git_repo(tmp_path: Path) -> Path:
    """Create a minimal, clean git repository in tmp_path."""
    repo = tmp_path / "target_repo"
    repo.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)

    # Initial code and test
    (repo / "app.py").write_text("def add(a, b):\n    return a + b\n")
    (repo / "test_app.py").write_text("from app import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")

    # Initial commit
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, check=True, capture_output=True)

    return repo


@pytest.fixture
def non_git_repo(tmp_path: Path) -> Path:
    """Create a plain non-git directory with some code."""
    repo = tmp_path / "plain_repo"
    repo.mkdir()
    (repo / "app.py").write_text("x = 1\n")
    return repo


# ---------------------------------------------------------------------------
# VerifierDetector tests
# ---------------------------------------------------------------------------

class TestVerifierDetector:
    def test_detects_pytest_when_tests_exist(self, tmp_path):
        repo = tmp_path / "py_repo"
        repo.mkdir()
        (repo / "app.py").write_text("x = 1\n")
        (repo / "test_app.py").write_text("def test_x(): pass\n")

        detector = VerifierDetector(repo)
        cmd, strength, name = detector.detect_verifier()
        assert strength == VerificationStrength.TESTS_PASSED
        assert "pytest" in name.lower()
        assert any("pytest" in c for c in cmd)

    def test_detects_npm_test_when_package_json_has_test(self, tmp_path):
        repo = tmp_path / "node_repo"
        repo.mkdir()
        (repo / "package.json").write_text('{"scripts": {"test": "echo test passed"}}')

        detector = VerifierDetector(repo)
        cmd, strength, name = detector.detect_verifier()
        assert strength == VerificationStrength.TESTS_PASSED
        assert "npm" in name.lower()
        assert cmd == ["npm", "test"]

    def test_detects_go_test_when_go_mod_exists(self, tmp_path):
        repo = tmp_path / "go_repo"
        repo.mkdir()
        (repo / "go.mod").write_text("module example.com/app\n")

        detector = VerifierDetector(repo)
        cmd, strength, name = detector.detect_verifier()
        assert strength == VerificationStrength.TESTS_PASSED
        assert "go" in name.lower()
        assert cmd == ["go", "test", "./..."]

    def test_detects_cargo_check_when_cargo_toml_exists(self, tmp_path):
        repo = tmp_path / "rust_repo"
        repo.mkdir()
        (repo / "Cargo.toml").write_text("[package]\nname = 'app'\n")

        detector = VerifierDetector(repo)
        cmd, strength, name = detector.detect_verifier()
        assert strength == VerificationStrength.TESTS_PASSED
        assert "cargo" in name.lower()
        assert cmd == ["cargo", "check"]

    def test_detects_python_compile_as_syntax_fallback(self, tmp_path):
        repo = tmp_path / "py_syntax_only"
        repo.mkdir()
        # Only source, no tests or config
        (repo / "worker.py").write_text("print('hello')\n")

        detector = VerifierDetector(repo)
        cmd, strength, name = detector.detect_verifier()
        assert strength == VerificationStrength.SYNTAX_ONLY
        assert "compileall" in name.lower()

    def test_no_verifier_detected(self, tmp_path):
        repo = tmp_path / "text_only"
        repo.mkdir()
        (repo / "README.md").write_text("# Hello\n")
        (repo / "notes.txt").write_text("some notes\n")

        detector = VerifierDetector(repo)
        cmd, strength, name = detector.detect_verifier()
        assert strength == VerificationStrength.NO_VERIFIER
        assert cmd == []

    def test_detection_order_pytest_over_compileall(self, tmp_path):
        repo = tmp_path / "both_repo"
        repo.mkdir()
        (repo / "app.py").write_text("x = 1\n")
        (repo / "test_app.py").write_text("def test_x(): pass\n")

        detector = VerifierDetector(repo)
        _, strength, name = detector.detect_verifier()
        # Must detect pytest (TESTS_PASSED), not compileall (SYNTAX_ONLY)
        assert strength == VerificationStrength.TESTS_PASSED
        assert "pytest" in name


# ---------------------------------------------------------------------------
# Sandbox Worktree Lifecycle tests
# ---------------------------------------------------------------------------

class TestSandboxLifecycle:
    def test_worktree_creation_for_clean_git_repo(self, target_git_repo):
        with Sandbox(target_git_repo) as sb:
            assert sb.worktree_path is not None
            assert sb.worktree_path.exists()
            assert (sb.worktree_path / "app.py").exists()
            # Must NOT be the same path as the target repo (isolated!)
            assert sb.worktree_path.resolve() != target_git_repo.resolve()

    def test_fallback_to_temp_copy_for_non_git_repo(self, non_git_repo):
        with Sandbox(non_git_repo) as sb:
            assert sb.worktree_path is not None
            assert sb.worktree_path.exists()
            assert (sb.worktree_path / "app.py").exists()
            assert sb.worktree_path.resolve() != non_git_repo.resolve()

    def test_fallback_to_temp_copy_for_dirty_git_repo(self, target_git_repo):
        # Create uncommitted changes in target repo
        (target_git_repo / "dirty_file.txt").write_text("uncommitted change\n")

        with Sandbox(target_git_repo) as sb:
            assert sb.worktree_path is not None
            assert sb.worktree_path.exists()
            assert (sb.worktree_path / "dirty_file.txt").exists()

    def test_cleanup_removes_worktree_and_temp_dir(self, target_git_repo):
        sb = Sandbox(target_git_repo)
        sb.setup()
        wt = sb.worktree_path
        tmp = sb._temp_dir
        assert wt.exists()
        sb.cleanup()
        assert not wt.exists()
        if tmp:
            assert not tmp.exists()

    def test_cleanup_after_a_crash(self, target_git_repo):
        wt = None
        tmp = None
        try:
            with Sandbox(target_git_repo) as sb:
                wt = sb.worktree_path
                tmp = sb._temp_dir
                assert wt.exists()
                # Simulate a crash inside the verification block
                raise RuntimeError("Simulated crash during verification")
        except RuntimeError:
            pass

        # Cleanup must have executed despite the exception
        assert wt is not None and not wt.exists()
        if tmp:
            assert not tmp.exists()


# ---------------------------------------------------------------------------
# Verification Gate tests (Passing, Breaking, Rollback, Baseline)
# ---------------------------------------------------------------------------

class TestVerificationGate:
    def test_passing_patch_verified(self, target_git_repo):
        """Applying a valid patch that keeps tests green marks it VERIFIED."""
        patch = Patch(
            finding_id="TEST-001",
            file="app.py",
            search="def add(a, b):\n    return a + b",
            replace="def add(a, b):\n    # verified improvement\n    return a + b",
            description="Add comment",
        )

        with Sandbox(target_git_repo) as sb:
            passed, out, cmd, strength, verifier_name = sb.run_baseline_verifier()
            assert passed is True
            assert strength == VerificationStrength.TESTS_PASSED

            res = sb.verify_patch(
                patch=patch,
                baseline_passed=passed,
                baseline_output=out,
                verifier_command=cmd,
                verifier_strength=strength,
                verifier_name=verifier_name,
            )

            assert res.status == FixStatus.VERIFIED
            assert res.patch_passed is True
            assert res.strength == VerificationStrength.TESTS_PASSED

    def test_breaking_patch_rolled_back(self, target_git_repo):
        """Applying a patch that breaks tests is immediately rolled back."""
        patch = Patch(
            finding_id="TEST-002",
            file="app.py",
            search="return a + b",
            replace="return a - b",  # Breaks test_add!
            description="Bad change",
        )

        with Sandbox(target_git_repo) as sb:
            passed, out, cmd, strength, verifier_name = sb.run_baseline_verifier()
            assert passed is True

            res = sb.verify_patch(
                patch=patch,
                baseline_passed=passed,
                baseline_output=out,
                verifier_command=cmd,
                verifier_strength=strength,
                verifier_name=verifier_name,
            )

            # Verification gate rejects and rolls back
            assert res.status == FixStatus.ROLLED_BACK
            assert res.patch_passed is False

            # Verify that the worktree file was reverted
            content = (sb.worktree_path / "app.py").read_text(encoding="utf-8")
            assert "return a + b" in content
            assert "return a - b" not in content

    def test_no_verifier_strength_recorded(self, tmp_path):
        """A project without any tests or verifier records NO_VERIFIER strength."""
        repo = tmp_path / "text_repo"
        repo.mkdir()
        (repo / "doc.txt").write_text("Hello World\n")

        patch = Patch(
            finding_id="DOC-001",
            file="doc.txt",
            search="Hello World",
            replace="Hello Universe",
            description="Update text",
        )

        with Sandbox(repo) as sb:
            passed, out, cmd, strength, verifier_name = sb.run_baseline_verifier()
            assert strength == VerificationStrength.NO_VERIFIER

            res = sb.verify_patch(
                patch=patch,
                baseline_passed=passed,
                baseline_output=out,
                verifier_command=cmd,
                verifier_strength=strength,
                verifier_name=verifier_name,
            )

            assert res.status == FixStatus.VERIFIED
            assert res.strength == VerificationStrength.NO_VERIFIER

    def test_baseline_already_failing(self, tmp_path):
        """When baseline is already failing, a patch that doesn't fix it is ROLLED_BACK."""
        repo = tmp_path / "failing_repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)

        # Write code that FAILS the test
        (repo / "app.py").write_text("def mul(a, b):\n    return a + b\n")
        (repo / "test_app.py").write_text("from app import mul\n\ndef test_mul():\n    assert mul(2, 3) == 6\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init broken"], cwd=repo, check=True, capture_output=True)

        # Patch 1: irrelevant patch that leaves test failing
        bad_patch = Patch(
            finding_id="FAIL-001",
            file="app.py",
            search="def mul",
            replace="# comment\ndef mul",
            description="Irrelevant comment",
        )

        # Patch 2: fixes the bug!
        good_patch = Patch(
            finding_id="FIX-001",
            file="app.py",
            search="return a + b",
            replace="return a * b",
            description="Fix multiplication",
        )

        with Sandbox(repo) as sb:
            passed, out, cmd, strength, verifier_name = sb.run_baseline_verifier()
            assert passed is False  # Baseline is failing!

            # Bad patch does not fix test -> ROLLED_BACK
            res_bad = sb.verify_patch(
                patch=bad_patch,
                baseline_passed=passed,
                baseline_output=out,
                verifier_command=cmd,
                verifier_strength=strength,
                verifier_name=verifier_name,
            )
            assert res_bad.status == FixStatus.ROLLED_BACK

            # Good patch fixes test -> VERIFIED
            res_good = sb.verify_patch(
                patch=good_patch,
                baseline_passed=passed,
                baseline_output=out,
                verifier_command=cmd,
                verifier_strength=strength,
                verifier_name=verifier_name,
            )
            assert res_good.status == FixStatus.VERIFIED
            assert res_good.patch_passed is True

    def test_patch_search_string_not_found(self, target_git_repo):
        """Search string not found in target file fails safely without applying."""
        patch = Patch(
            finding_id="MISSING-001",
            file="app.py",
            search="this string does not exist in app.py",
            replace="something else",
            description="Invalid search",
        )

        with Sandbox(target_git_repo) as sb:
            passed, out, cmd, strength, verifier_name = sb.run_baseline_verifier()
            res = sb.verify_patch(
                patch=patch,
                baseline_passed=passed,
                baseline_output=out,
                verifier_command=cmd,
                verifier_strength=strength,
                verifier_name=verifier_name,
            )
            assert res.status == FixStatus.ROLLED_BACK
            assert "failed to apply patch" in res.output.lower()

    def test_promote_verified_patches_to_branch(self, target_git_repo):
        """Verified patches are promoted to contractguard/clean branch."""
        patch = Patch(
            finding_id="PROMOTE-001",
            file="app.py",
            search="def add(a, b):",
            replace="# verified\ndef add(a, b):",
            description="Add header",
        )

        with Sandbox(target_git_repo, branch_name="contractguard/clean") as sb:
            passed, out, cmd, strength, verifier_name = sb.run_baseline_verifier()
            res = sb.verify_patch(
                patch=patch,
                baseline_passed=passed,
                baseline_output=out,
                verifier_command=cmd,
                verifier_strength=strength,
                verifier_name=verifier_name,
            )
            assert res.status == FixStatus.VERIFIED

            # Promote verified patches
            success = sb.promote_verified_patches([res])
            assert success is True

        # Check target repo branch was created and has the commit
        branches = subprocess.run(
            ["git", "branch"], cwd=target_git_repo, capture_output=True, text=True
        ).stdout
        assert "contractguard/clean" in branches

        content = (target_git_repo / "app.py").read_text(encoding="utf-8")
        assert "# verified" in content
