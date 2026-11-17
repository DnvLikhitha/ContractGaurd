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
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(cli, ["audit", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        # JSON should be parseable
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_audit_json_each_item_has_required_fields(self, tmp_path):
        # Plant a known issue so there's at least one finding
        make_repo(tmp_path)
        (tmp_path / "src" / "bad.py").write_text("DEBUG = True\n")
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(cli, ["audit", str(tmp_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for item in data:
            for field in ("id", "category", "severity", "confidence", "file", "title"):
                assert field in item, f"Missing field {field!r} in {item}"

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
        # Placeholder - just must not crash with unknown option
        assert result.exit_code in (0, 1)


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
