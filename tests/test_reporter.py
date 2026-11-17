"""
Tests for contractguard.reporter.

Written first per CLAUDE.md rules.
Tests cover: JSON output, Rich table rendering (no crash), receipt writing.
"""

import json
import sys
from io import StringIO
from pathlib import Path

import pytest

from contractguard.models import Finding, Patch, VerificationResult
from contractguard.reporter import (
    findings_to_json,
    print_findings_table,
    write_verification_receipt,
)


def make_finding(**kwargs) -> Finding:
    defaults = dict(
        id="T-001",
        category="security",
        severity="critical",
        confidence=0.9,
        file="src/app.py",
        line=42,
        title="Hardcoded secret",
        evidence="SECRET_KEY = '***MASKED***'",
        suggested_fix="Move to env var",
    )
    defaults.update(kwargs)
    return Finding(**defaults)


def make_verification_result(status="VERIFIED", strength="TESTS_PASSED") -> VerificationResult:
    patch = Patch(
        finding_id="T-001",
        file="src/app.py",
        search="old",
        replace="new",
        description="fix it",
    )
    return VerificationResult(
        finding_id="T-001",
        patch=patch,
        status=status,
        strength=strength,
        verifier_used="pytest",
        baseline_passed=True,
        patch_passed=(status == "VERIFIED"),
        output="1 passed",
        error=None,
    )


# ---------------------------------------------------------------------------
# findings_to_json
# ---------------------------------------------------------------------------

class TestFindingsToJson:
    def test_empty_list(self):
        result = findings_to_json([])
        parsed = json.loads(result)
        assert parsed == []

    def test_single_finding(self):
        f = make_finding()
        result = findings_to_json([f])
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["id"] == "T-001"

    def test_multiple_findings(self):
        findings = [make_finding(id=f"T-{i:03d}") for i in range(3)]
        result = findings_to_json(findings)
        parsed = json.loads(result)
        assert len(parsed) == 3

    def test_all_fields_present(self):
        f = make_finding()
        result = findings_to_json([f])
        parsed = json.loads(result)[0]
        for field in ("id", "category", "severity", "confidence", "file", "line", "title", "evidence"):
            assert field in parsed

    def test_output_is_valid_json(self):
        f = make_finding()
        raw = findings_to_json([f])
        json.loads(raw)  # must not raise

    def test_none_line_serialised(self):
        f = make_finding(line=None)
        raw = findings_to_json([f])
        parsed = json.loads(raw)[0]
        assert parsed["line"] is None


# ---------------------------------------------------------------------------
# print_findings_table (smoke test - must not crash)
# ---------------------------------------------------------------------------

class TestPrintFindingsTable:
    def test_no_findings_does_not_crash(self, capsys):
        print_findings_table([])  # should not raise

    def test_single_finding_does_not_crash(self, capsys):
        print_findings_table([make_finding()])

    def test_mixed_severities_does_not_crash(self, capsys):
        findings = [
            make_finding(id=f"T-{i:03d}", severity=sev, line=i)
            for i, sev in enumerate(["critical", "high", "medium", "low", "info"])
        ]
        print_findings_table(findings)

    def test_finding_with_no_line_does_not_crash(self, capsys):
        print_findings_table([make_finding(line=None)])

    def test_finding_with_no_fix_does_not_crash(self, capsys):
        print_findings_table([make_finding(suggested_fix=None)])


# ---------------------------------------------------------------------------
# write_verification_receipt
# ---------------------------------------------------------------------------

class TestWriteVerificationReceipt:
    def test_creates_file(self, tmp_path):
        results = [make_verification_result()]
        out = tmp_path / "VERIFICATION_RECEIPT.md"
        write_verification_receipt(results, out)
        assert out.exists()

    def test_file_contains_verified(self, tmp_path):
        results = [make_verification_result(status="VERIFIED", strength="TESTS_PASSED")]
        out = tmp_path / "VERIFICATION_RECEIPT.md"
        write_verification_receipt(results, out)
        content = out.read_text()
        assert "VERIFIED" in content

    def test_file_contains_rolled_back(self, tmp_path):
        results = [make_verification_result(status="ROLLED_BACK", strength="SYNTAX_ONLY")]
        out = tmp_path / "VERIFICATION_RECEIPT.md"
        write_verification_receipt(results, out)
        content = out.read_text()
        assert "ROLLED_BACK" in content

    def test_file_contains_strength(self, tmp_path):
        results = [make_verification_result(strength="TESTS_PASSED")]
        out = tmp_path / "VERIFICATION_RECEIPT.md"
        write_verification_receipt(results, out)
        assert "TESTS_PASSED" in out.read_text()

    def test_empty_results_still_creates_file(self, tmp_path):
        out = tmp_path / "VERIFICATION_RECEIPT.md"
        write_verification_receipt([], out)
        assert out.exists()

    def test_multiple_results(self, tmp_path):
        results = [
            make_verification_result(status="VERIFIED", strength="TESTS_PASSED"),
            make_verification_result(status="ROLLED_BACK", strength="SYNTAX_ONLY"),
        ]
        out = tmp_path / "VERIFICATION_RECEIPT.md"
        write_verification_receipt(results, out)
        content = out.read_text()
        assert "VERIFIED" in content
        assert "ROLLED_BACK" in content
