"""Sandbox: git worktree lifecycle, patch apply, verifier detection, gate, rollback.

Verification Gate (ARCHITECTURE.md Section 4):
1. Create `git worktree add --detach <tmp>`; fall back to temp copy if not a git repo or tree is dirty.
2. Run a baseline verifier first. If baseline already fails, record it.
3. Apply one patch at a time. Run verifier. Exit code 0: VERIFIED. Otherwise revert patch: ROLLED_BACK.
4. Verifier detection order: pytest -> npm test -> go test ./... -> cargo check -> syntax fallback (compileall, node --check).
5. Strength is recorded: TESTS_PASSED, SYNTAX_ONLY, NO_VERIFIER.
6. Promote verified patches to branch (e.g. contractguard/clean).
7. Cleanup in try/finally with `git worktree remove --force`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from contractguard.models import FixStatus, Patch, VerificationResult, VerificationStrength


class SandboxError(Exception):
    """Raised when sandbox operations fail."""
    pass


class VerifierDetector:
    """Detects and runs the appropriate verifier for a repository."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def detect_verifier(self) -> tuple[list[str], VerificationStrength, str]:
        """Detect the best verifier to use. Returns (command, strength, name).

        Order:
          1. pytest
          2. npm test
          3. go test ./...
          4. cargo check
          5. python -m compileall / node --check (syntax fallback)
          6. none
        """
        # 1. Check for pytest
        if (
            (self.repo_path / "pytest.ini").exists()
            or any(self.repo_path.glob("test_*.py"))
            or any(self.repo_path.glob("*_test.py"))
            or any(self.repo_path.glob("tests/*.py"))
            or any(self.repo_path.glob("test/*.py"))
            or (
                (self.repo_path / "pyproject.toml").exists()
                and "pytest" in (self.repo_path / "pyproject.toml").read_text(encoding="utf-8", errors="replace")
            )
        ):
            return (
                [sys.executable, "-m", "pytest", "-q"],
                VerificationStrength.TESTS_PASSED,
                "pytest",
            )

        # 2. Check for npm test
        pkg_json = self.repo_path / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
                if isinstance(data, dict) and data.get("scripts", {}).get("test"):
                    return (["npm", "test"], VerificationStrength.TESTS_PASSED, "npm test")
            except Exception:
                pass

        # 3. Check for go test
        if (self.repo_path / "go.mod").exists() or any(self.repo_path.glob("*.go")):
            return (["go", "test", "./..."], VerificationStrength.TESTS_PASSED, "go test")

        # 4. Check for cargo check
        if (self.repo_path / "Cargo.toml").exists():
            return (["cargo", "check"], VerificationStrength.TESTS_PASSED, "cargo check")

        # 5. Syntax fallback: Python compileall
        if any(self.repo_path.rglob("*.py")):
            return (
                [sys.executable, "-m", "compileall", "-q", "."],
                VerificationStrength.SYNTAX_ONLY,
                "python -m compileall",
            )

        # 5. Syntax fallback: Node check
        if any(self.repo_path.rglob("*.js")) or any(self.repo_path.rglob("*.ts")):
            return (["node", "--check", "."], VerificationStrength.SYNTAX_ONLY, "node --check")

        # 6. No verifier available
        return ([], VerificationStrength.NO_VERIFIER, "none")

    def run_verifier(self, command: list[str], cwd: Path) -> tuple[bool, str]:
        """Run a verifier command in cwd. Returns (success, output)."""
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
            output = (result.stdout or "") + "\n" + (result.stderr or "")
            return (result.returncode == 0, output.strip())
        except subprocess.TimeoutExpired:
            return (False, "Verifier timed out after 120 seconds")
        except FileNotFoundError:
            return (False, f"Verifier command not found: {command[0]}")
        except Exception as e:
            return (False, f"Verifier error: {e}")


class Sandbox:
    """Manages an isolated git worktree (or temp copy) for verifying patches."""

    def __init__(self, repo_path: Path, branch_name: str = "contractguard/clean"):
        self.repo_path = repo_path.resolve()
        self.branch_name = branch_name
        self.worktree_path: Optional[Path] = None
        self.is_git_repo = (self.repo_path / ".git").exists()
        self.is_worktree = False
        self.original_branch: Optional[str] = None
        self._temp_dir: Optional[Path] = None

    def __enter__(self) -> "Sandbox":
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cleanup()

    def _is_tree_dirty(self) -> bool:
        """Check if git working tree has uncommitted or untracked changes."""
        if not self.is_git_repo:
            return True
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return True
            return bool(result.stdout.strip())
        except Exception:
            return True

    def setup(self) -> None:
        """Create worktree or temp copy."""
        # Use git worktree only if target is a clean git repository
        if self.is_git_repo and not self._is_tree_dirty():
            try:
                self._setup_git_worktree()
                return
            except Exception:
                # Fall back to temp copy if worktree add fails
                pass

        self._setup_temp_copy()

    def _setup_git_worktree(self) -> None:
        """Create a detached git worktree."""
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        self.original_branch = result.stdout.strip() or "HEAD"

        self._temp_dir = Path(tempfile.mkdtemp(prefix="contractguard-wt-"))
        self.worktree_path = self._temp_dir / "worktree"

        result = subprocess.run(
            ["git", "worktree", "add", "--detach", str(self.worktree_path)],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SandboxError(f"Failed to create worktree: {result.stderr}")

        self.is_worktree = True

    def _setup_temp_copy(self) -> None:
        """Create a temporary copy of the repo (for non-git or dirty repos)."""
        self._temp_dir = Path(tempfile.mkdtemp(prefix="contractguard-copy-"))
        self.worktree_path = self._temp_dir / "repo"
        shutil.copytree(self.repo_path, self.worktree_path, ignore=shutil.ignore_patterns(".git"))
        self.is_worktree = False

    def cleanup(self) -> None:
        """Clean up worktree and temp directory in try/finally."""
        try:
            if self.is_worktree and self.worktree_path and self.worktree_path.exists():
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(self.worktree_path)],
                    cwd=self.repo_path,
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=self.repo_path,
                    capture_output=True,
                )
        finally:
            if self._temp_dir and self._temp_dir.exists():
                def _on_rm_error(func, path, exc_info):
                    try:
                        os.chmod(path, 0o777)
                        func(path)
                    except Exception:
                        pass
                shutil.rmtree(self._temp_dir, onerror=_on_rm_error)
            self.worktree_path = None
            self._temp_dir = None

    def apply_patch(self, patch: Patch) -> bool:
        """Apply a patch to the worktree. Returns True if applied cleanly."""
        if not self.worktree_path:
            return False

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
        """Revert an applied patch in the worktree."""
        if not self.worktree_path:
            return False

        file_path = self.worktree_path / patch.file
        if not file_path.exists():
            return False

        content = file_path.read_text(encoding="utf-8", errors="replace")

        # Verify replace string matches exactly once
        count = content.count(patch.replace)
        if count != 1:
            return False

        orig_content = content.replace(patch.replace, patch.search, 1)
        file_path.write_text(orig_content, encoding="utf-8")
        return True

    def run_baseline_verifier(self) -> tuple[bool, str, list[str], VerificationStrength, str]:
        """Run baseline verifier before any patch. Returns (passed, output, command, strength, name)."""
        if not self.worktree_path:
            raise SandboxError("Sandbox not set up")

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
        verifier_name: str,
    ) -> VerificationResult:
        """Apply patch, run verifier, and gate: pass = VERIFIED, fail = ROLLED_BACK."""
        if not self.worktree_path:
            raise SandboxError("Sandbox not set up")

        # 1. Apply patch
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

        # 2. Run verifier
        patch_passed, output = VerifierDetector(self.worktree_path).run_verifier(
            verifier_command, self.worktree_path
        )

        # 3. Gate decision:
        # If verifier passed (exit code 0), patch is VERIFIED.
        # Otherwise (or if baseline was already passing and now fails), ROLLED_BACK.
        if patch_passed:
            status = FixStatus.VERIFIED
            error = None
        else:
            # Revert the patch immediately to keep worktree clean for next patches
            self.revert_patch(patch)
            status = FixStatus.ROLLED_BACK
            error = "Tests failed after patch" if baseline_passed else "Baseline failures unresolved"

        return VerificationResult(
            finding_id=patch.finding_id,
            patch=patch,
            status=status,
            strength=verifier_strength,
            verifier_used=verifier_name,
            baseline_passed=baseline_passed,
            patch_passed=patch_passed,
            output=output,
            error=error,
        )

    def promote_verified_patches(self, results: list[VerificationResult]) -> bool:
        """Promote verified patches to the target branch."""
        verified_patches = [r for r in results if r.status == FixStatus.VERIFIED]
        if not verified_patches:
            return True

        if not self.is_git_repo:
            # For non-git repos, apply verified patches directly to target directory
            for result in verified_patches:
                patch = result.patch
                file_path = self.repo_path / patch.file
                if file_path.exists():
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                    if content.count(patch.search) == 1:
                        new_content = content.replace(patch.search, patch.replace, 1)
                        file_path.write_text(new_content, encoding="utf-8")
            return True

        try:
            # Create/switch to target branch
            subprocess.run(
                ["git", "checkout", "-B", self.branch_name],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )

            # Apply each verified patch in the target repo
            for result in verified_patches:
                patch = result.patch
                file_path = self.repo_path / patch.file
                content = file_path.read_text(encoding="utf-8", errors="replace")
                if content.count(patch.search) == 1:
                    new_content = content.replace(patch.search, patch.replace, 1)
                    file_path.write_text(new_content, encoding="utf-8")
                else:
                    return False

            # Commit verified fixes
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
