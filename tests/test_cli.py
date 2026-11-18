"""
Tests for contractguard.cli.

Written first per CLAUDE.md rules.
Tests cover: CLI invocation via Click test runner, --json flag, heal placeholder.
"""

import json
import pytest
from click.testing import CliRunner
from pathlib import Path

from contractguard.cli import cli


def _make_runner() -> CliRunner:
    """Create a CliRunner compatible across Click versions (8.1 mix_stderr vs 8.5+)."""
    try:
        return CliRunner(mix_stderr=False)
    except TypeError:
        return CliRunner()


def make_repo(tmp_path: Path) -> Path:
    """Build a minimal valid repo for CLI tests."""
    (tmp_path / "README.md").write_text("# Test App\n")
    (tmp_path / ".env.example").write_text("DATABASE_URL=\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("import os\nDB = os.getenv('DATABASE_URL')\n")
    return tmp_path


# ---------------------------------------------------------------------------
# audit command
# ---------------------------------------------------------------------------

class TestAuditCommand:
    def test_audit_exits_zero_on_clean_repo(self, tmp_path):
        make_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["audit", str(tmp_path)])
        assert result.exit_code == 0, result.output

    def test_audit_outputs_something(self, tmp_path):
        make_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["audit", str(tmp_path)])
        assert result.output.strip() != ""

    def test_audit_json_flag_outputs_valid_json(self, tmp_path):
        make_repo(tmp_path)
        runner = _make_runner()
        result = runner.invoke(cli, ["audit", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        # JSON should be parseable
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_audit_json_each_item_has_required_fields(self, tmp_path):
        # Plant a known issue so there's at least one finding
        make_repo(tmp_path)
        (tmp_path / "src" / "bad.py").write_text("DEBUG = True\n")
        runner = _make_runner()
        result = runner.invoke(cli, ["audit", str(tmp_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for item in data:
            for field in ("id", "category", "severity", "confidence", "file", "title"):
                assert field in item, f"Missing field {field!r} in {item}"

    def test_audit_detects_drift_via_cli(self, tmp_path):
        make_repo(tmp_path)
        # Add an undocumented env var to app.py
        (tmp_path / "src" / "app.py").write_text("import os\nDB = os.getenv('SECRET_UNLISTED_TOKEN')\n")
        runner = _make_runner()
        result = runner.invoke(cli, ["audit", str(tmp_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        drift_items = [d for d in data if d["category"] == "drift"]
        assert len(drift_items) >= 1
        assert any("SECRET_UNLISTED_TOKEN" in d["title"] for d in drift_items)

    def test_audit_detects_slop_via_cli(self, tmp_path):
        make_repo(tmp_path)
        # Add an unused dependency to requirements.txt and an orphaned file
        (tmp_path / "requirements.txt").write_text("unused-mock-package==1.0.0\n")
        (tmp_path / "src" / "dead_module.py").write_text("def abandoned(): pass\n")
        runner = _make_runner()
        result = runner.invoke(cli, ["audit", str(tmp_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        slop_items = [d for d in data if d["category"] == "slop"]
        assert len(slop_items) >= 1
        assert any("unused-mock-package" in d["title"] or "dead_module.py" in d["file"] for d in slop_items)

    def test_audit_nonexistent_path_exits_nonzero(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["audit", str(tmp_path / "does_not_exist")])
        assert result.exit_code != 0

    def test_audit_no_args_shows_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["audit", "--help"])
        assert result.exit_code == 0
        assert "path" in result.output.lower() or "PATH" in result.output

    def test_audit_no_llm_flag_accepted(self, tmp_path):
        make_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["audit", str(tmp_path), "--no-llm"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# heal command (placeholder)
# ---------------------------------------------------------------------------

class TestHealCommand:
    def test_heal_exists_as_command(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["heal", "--help"])
        assert result.exit_code == 0

    def test_heal_placeholder_exits_zero_or_notimplemented(self, tmp_path):
        make_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["heal", str(tmp_path)])
        # Either exits 0 (placeholder prints message) or exits with known code
        assert result.exit_code in (0, 1)

    def test_heal_branch_flag_accepted(self, tmp_path):
        make_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["heal", str(tmp_path), "--branch", "contractguard/clean"])
        assert result.exit_code in (0, 1)

    def test_heal_executes_verification_and_writes_receipt(self, tmp_path):
        make_repo(tmp_path)
        # Add an undocumented env var in app.py
        (tmp_path / "src" / "app.py").write_text("import os\nval = os.getenv('NEW_HEAL_VAR')\n")
        runner = CliRunner()
        result = runner.invoke(cli, ["heal", str(tmp_path), "--no-llm"])
        assert result.exit_code == 0
        receipt = tmp_path / "VERIFICATION_RECEIPT.md"
        assert receipt.exists()
        content = receipt.read_text(encoding="utf-8")
        assert "VERIFICATION_RECEIPT" in content
        # Check that .env.example was healed with the missing variable
        env_ex = (tmp_path / ".env.example").read_text(encoding="utf-8")
        assert "NEW_HEAL_VAR=" in env_ex


# ---------------------------------------------------------------------------
# Top-level CLI group
# ---------------------------------------------------------------------------

class TestCliGroup:
    def test_help_works(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "audit" in result.output

    def test_unknown_command_nonzero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["nonexistent"])
        assert result.exit_code != 0
