"""Sandbox: git worktree lifecycle, patch apply, verifier detection, gate, rollback."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from contractguard.models import Patch, VerificationResult, VerificationStrength, FixStatus


class SandboxError(Exception):
    """Raised when sandbox operations fail."""
    pass


class VerifierDetector:
    """Detects and runs the appropriate verifier for a repository."""

    VERIFIERS = [
        ("pytest", ["pytest", "-q"], "TESTS_PASSED"),
        ("npm_test", ["npm", "test"], "TESTS_PASSED"),
        ("go_test", ["go", "test", "./..."], "TESTS_PASSED"),
        ("cargo_check", ["cargo", "check"], "TESTS_PASSED"),
        ("python_compile", ["python", "-m", "compileall", "-q", "."], "SYNTAX_ONLY"),
        ("node_check", ["node", "--check", "."], "SYNTAX_ONLY"),
    ]

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def detect_verifier(self) -> tuple[list[str], VerificationStrength, str]:
        """Detect the best verifier to use. Returns (command, strength, name)."""
        # Check for pytest
        if (self.repo_path / "pytest.ini").exists() or \
           (self.repo_path / "pyproject.toml").exists() or \
           any(self.repo_path.glob("test_*.py")) or \
           any(self.repo_path.glob("*_test.py")):
            return (["pytest", "-q"], VerificationStrength.TESTS_PASSED, "pytest")

        # Check for npm test
        if (self.repo_path / "package.json").exists():
            # Check if test script exists
            try:
                import json
                pkg = json.loads((self.repo_path / "package.json").read_text())
                if pkg.get("scripts", {}).get("test"):
                    return (["npm", "test"], VerificationStrength.TESTS_PASSED, "npm test")
            except Exception:
                pass

        # Check for go test
        if (self.repo_path / "go.mod").exists():
            return (["go", "test", "./..."], VerificationStrength.TESTS_PASSED, "go test")

        # Check for cargo
        if (self.repo_path / "Cargo.toml").exists():
            return (["cargo", "check"], VerificationStrength.TESTS_PASSED, "cargo check")

        # Fallback: Python syntax check
        if any(self.repo_path.glob("*.py")):
            return (["python", "-m", "compileall", "-q", "."], VerificationStrength.SYNTAX_ONLY, "python -m compileall")

        # Fallback: Node syntax check
        if any(self.repo_path.glob("*.js")) or any(self.repo_path.glob("*.ts")):
            return (["node", "--check", "."], VerificationStrength.SYNTAX_ONLY, "node --check")

        return ([], VerificationStrength.NO_VERIFIER, "none")

    def run_verifier(self, command: list[str], cwd: Path) -> tuple[bool, str]:
        """Run a verifier command. Returns (success, output)."""
        if not command:
            return (True, "No verifier available")

        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = result.stdout + "\n" + result.stderr
            return (result.returncode == 0, output)
        except subprocess.TimeoutExpired:
            return (False, "Verifier timed out after 120 seconds")
        except FileNotFoundError:
            return (False, f"Verifier command not found: {command[0]}")
        except Exception as e:
            return (False, f"Verifier error: {e}")


class Sandbox:
    """Manages a git worktree (or temp copy) for verifying patches."""

    def __init__(self, repo_path: Path, branch_name: str = "contractguard/clean"):
        self.repo_path = repo_path.resolve()
        self.branch_name = branch_name
        self.worktree_path: Optional[Path] = None
        self.is_git_repo = (self.repo_path / ".git").exists()
        self.original_branch = None
        self._temp_dir: Optional[Path] = None

    def __enter__(self) -> "Sandbox":
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cleanup()

    def setup(self) -> None:
        """Create worktree or temp copy."""
        if self.is_git_repo:
            self._setup_git_worktree()
        else:
            self._setup_temp_copy()

    def _setup_git_worktree(self) -> None:
        """Create a detached git worktree."""
        # Get current branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        self.original_branch = result.stdout.strip() or "main"

        # Create temp directory for worktree
        self._temp_dir = Path(tempfile.mkdtemp(prefix="contractguard-wt-"))
        self.worktree_path = self._temp_dir / "worktree"

        # Create detached worktree
        result = subprocess.run(
            ["git", "worktree", "add", "--detach", str(self.worktree_path)],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # If dirty tree, try force
            result = subprocess.run(
                ["git", "worktree", "add", "--detach", "--force", str(self.worktree_path)],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )
        if result.returncode != 0:
            raise SandboxError(f"Failed to create worktree: {result.stderr}")

    def _setup_temp_copy(self) -> None:
        """Create a temporary copy of the repo (for non-git or dirty repos)."""
        self._temp_dir = Path(tempfile.mkdtemp(prefix="contractguard-copy-"))
        self.worktree_path = self._temp_dir / "repo"
        shutil.copytree(self.repo_path, self.worktree_path, ignore=shutil.ignore_patterns(".git"))

    def cleanup(self) -> None:
        """Clean up worktree and temp directory."""
        if self.worktree_path and self.worktree_path.exists():
            if self.is_git_repo:
                # Remove worktree
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(self.worktree_path)],
                    cwd=self.repo_path,
                    capture_output=True,
                )
        if self._temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)

    def apply_patch(self, patch: Patch) -> bool:
        """Apply a patch to the worktree. Returns True if successful."""
        file_path = self.worktree_path / patch.file
        if not file_path.exists():
            return False

        content = file_path.read_text(encoding="utf-8", errors="replace")

        # Verify search string matches exactly once
        count = content.count(patch.search)
        if count != 1:
            return False

        new_content = content.replace(patch.search, patch.replace, 1)
        file_path.write_text(new_content, encoding="utf-8")
        return True

    def revert_patch(self, patch: Patch) -> bool:
        """Revert a patch (swap search/replace)."""
        file_path = self.worktree_path / patch.file
        if not file_path.exists():
            return False

        content = file_path.read_text(encoding="utf-8", errors="replace")

        # Verify replace string matches exactly once
        count = content.count(patch.replace)
        if count != 1:
            return False

        new_content = content.replace(patch.replace, patch.search, 1)
        file_path.write_text(new_content, encoding="utf-8")
        return True

    def run_baseline_verifier(self) -> tuple[bool, str, list[str], VerificationStrength, str]:
        """Run baseline verifier. Returns (passed, output, command, strength, name)."""
        detector = VerifierDetector(self.worktree_path)
        command, strength, name = detector.detect_verifier()
        passed, output = detector.run_verifier(command, self.worktree_path)
        return (passed, output, command, strength, name)

    def verify_patch(
        self,
        patch: Patch,
        baseline_passed: bool,
        baseline_output: str,
        verifier_command: list[str],
        verifier_strength: VerificationStrength,
        verifier_name: str
    ) -> VerificationResult:
        """Apply patch, run verifier, and return result."""
        # Apply patch
        applied = self.apply_patch(patch)
        if not applied:
            return VerificationResult(
                finding_id=patch.finding_id,
                patch=patch,
                status=FixStatus.ROLLED_BACK,
                strength=verifier_strength,
                verifier_used=verifier_name,
                baseline_passed=baseline_passed,
                patch_passed=False,
                output="Failed to apply patch (search string not found or matched multiple times)",
                error="Patch application failed",
            )

        # Run verifier
        patch_passed, output = VerifierDetector(self.worktree_path).run_verifier(
            verifier_command, self.worktree_path
        )

        if patch_passed:
            # Verify no new failures compared to baseline
            # (For simplicity, we just check exit code; could compare output)
            status = FixStatus.VERIFIED
        else:
            # Revert patch
            self.revert_patch(patch)
            status = FixStatus.ROLLED_BACK

        return VerificationResult(
            finding_id=patch.finding_id,
            patch=patch,
            status=status,
            strength=verifier_strength,
            verifier_used=verifier_name,
            baseline_passed=baseline_passed,
            patch_passed=patch_passed,
            output=output,
            error=None if patch_passed else "Tests failed after patch",
        )

    def promote_verified_patches(self, results: list[VerificationResult]) -> bool:
        """Promote verified patches to the target branch."""
        if not self.is_git_repo:
            return False

        verified_patches = [r for r in results if r.status == FixStatus.VERIFIED]
        if not verified_patches:
            return True

        try:
            # Create/switch to branch in main repo
            subprocess.run(
                ["git", "checkout", "-B", self.branch_name],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )

            # Apply each verified patch to main repo
            for result in verified_patches:
                patch = result.patch
                file_path = self.repo_path / patch.file
                content = file_path.read_text(encoding="utf-8", errors="replace")
                count = content.count(patch.search)
                if count == 1:
                    new_content = content.replace(patch.search, patch.replace, 1)
                    file_path.write_text(new_content, encoding="utf-8")
                else:
                    return False

            # Commit changes
            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "contractguard: apply verified fixes"],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )

            return True
        except subprocess.CalledProcessError:
            return False