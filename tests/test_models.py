"""
Tests for contractguard.models (Finding, Patch, VerificationResult).

Written before implementation per CLAUDE.md rules.
"""

import pytest
from pydantic import ValidationError

from contractguard.models import (
    Category,
    Finding,
    FixStatus,
    IndexedFile,
    Patch,
    Severity,
    VerificationResult,
    VerificationStrength,
)


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

class TestFinding:
    """Finding data-model tests."""

    def _make(self, **overrides) -> Finding:
        defaults = dict(
            id="SEC-001",
            category="security",
            severity="high",
            confidence=0.9,
            file="app.py",
            line=42,
            title="Hardcoded secret",
            evidence="SECRET_KEY = 'abc123'",
            suggested_fix="Move to environment variable",
        )
        defaults.update(overrides)
        return Finding(**defaults)

    def test_valid_finding(self):
        f = self._make()
        assert f.id == "SEC-001"
        assert f.category == "security"
        assert f.severity == "high"
        assert f.confidence == 0.9
        assert f.file == "app.py"
        assert f.line == 42

    def test_confidence_lower_bound(self):
        f = self._make(confidence=0.0)
        assert f.confidence == 0.0

    def test_confidence_upper_bound(self):
        f = self._make(confidence=1.0)
        assert f.confidence == 1.0

    def test_confidence_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            self._make(confidence=-0.1)

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError):
            self._make(confidence=1.01)

    def test_line_optional(self):
        f = self._make(line=None)
        assert f.line is None

    def test_suggested_fix_optional(self):
        f = self._make(suggested_fix=None)
        assert f.suggested_fix is None

    def test_invalid_category_rejected(self):
        with pytest.raises(ValidationError):
            self._make(category="unknown")

    def test_invalid_severity_rejected(self):
        with pytest.raises(ValidationError):
            self._make(severity="catastrophic")

    def test_all_valid_categories(self):
        for cat in ("security", "drift", "slop"):
            f = self._make(category=cat)
            assert f.category == cat

    def test_all_valid_severities(self):
        for sev in ("critical", "high", "medium", "low", "info"):
            f = self._make(severity=sev)
            assert f.severity == sev

    def test_serialises_to_dict(self):
        f = self._make()
        d = f.model_dump()
        assert d["id"] == "SEC-001"
        assert isinstance(d["confidence"], float)

    def test_round_trips_json(self):
        f = self._make()
        reloaded = Finding.model_validate_json(f.model_dump_json())
        assert reloaded.id == f.id
        assert reloaded.confidence == f.confidence


# ---------------------------------------------------------------------------
# Patch
# ---------------------------------------------------------------------------

class TestPatch:
    """Patch data-model tests."""

    def _make(self, **overrides) -> Patch:
        defaults = dict(
            finding_id="SEC-001",
            file="app.py",
            search="SECRET_KEY = 'abc123'",
            replace="SECRET_KEY = os.environ['SECRET_KEY']",
            description="Remove hardcoded secret",
        )
        defaults.update(overrides)
        return Patch(**defaults)

    def test_valid_patch(self):
        p = self._make()
        assert p.finding_id == "SEC-001"
        assert p.file == "app.py"

    def test_missing_field_rejected(self):
        with pytest.raises(ValidationError):
            Patch(finding_id="X", file="f.py", search="a")  # missing replace + description

    def test_round_trips_json(self):
        p = self._make()
        reloaded = Patch.model_validate_json(p.model_dump_json())
        assert reloaded.finding_id == p.finding_id


# ---------------------------------------------------------------------------
# VerificationResult
# ---------------------------------------------------------------------------

class TestVerificationResult:
    """VerificationResult data-model tests."""

    def _make_patch(self) -> Patch:
        return Patch(
            finding_id="SEC-001",
            file="app.py",
            search="old",
            replace="new",
            description="fix",
        )

    def _make(self, **overrides) -> VerificationResult:
        defaults = dict(
            finding_id="SEC-001",
            patch=self._make_patch(),
            status="VERIFIED",
            strength="TESTS_PASSED",
            verifier_used="pytest",
            baseline_passed=True,
            patch_passed=True,
            output="1 passed",
            error=None,
        )
        defaults.update(overrides)
        return VerificationResult(**defaults)

    def test_valid_result(self):
        r = self._make()
        assert r.status == "VERIFIED"
        assert r.strength == "TESTS_PASSED"

    def test_rolled_back_status(self):
        r = self._make(status="ROLLED_BACK", strength="SYNTAX_ONLY", patch_passed=False)
        assert r.status == "ROLLED_BACK"

    def test_no_verifier_strength(self):
        r = self._make(strength="NO_VERIFIER", verifier_used="none")
        assert r.strength == "NO_VERIFIER"

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            self._make(status="MAYBE")

    def test_invalid_strength_rejected(self):
        with pytest.raises(ValidationError):
            self._make(strength="VERY_STRONG")

    def test_error_field_optional(self):
        r = self._make(error=None)
        assert r.error is None

    def test_error_field_set(self):
        r = self._make(error="subprocess timeout")
        assert r.error == "subprocess timeout"

    def test_round_trips_json(self):
        r = self._make()
        reloaded = VerificationResult.model_validate_json(r.model_dump_json())
        assert reloaded.finding_id == r.finding_id


# ---------------------------------------------------------------------------
# IndexedFile
# ---------------------------------------------------------------------------

class TestIndexedFile:
    """IndexedFile data-model tests."""

    def test_basic(self):
        f = IndexedFile(path="src/app.py", content="print('hi')")
        assert f.path == "src/app.py"
        assert not f.is_contract
        assert not f.is_source

    def test_contract_flag(self):
        f = IndexedFile(path=".env.example", is_contract=True, content="DB_URL=")
        assert f.is_contract

    def test_source_flag(self):
        f = IndexedFile(path="main.py", is_source=True, content="x=1")
        assert f.is_source

    def test_language_optional(self):
        f = IndexedFile(path="Makefile", content="build:")
        assert f.language is None
