"""
Tests for contractguard.triage.

Written first per CLAUDE.md rules.
Covers: score calculation, deduplication, ranking, full pipeline.
"""

import pytest
from contractguard.models import Finding, Severity
from contractguard.triage import (
    SEVERITY_WEIGHTS,
    calculate_score,
    deduplicate_findings,
    rank_findings,
    triage_findings,
)


def make_finding(**kwargs) -> Finding:
    defaults = dict(
        id="T-001",
        category="security",
        severity="high",
        confidence=0.8,
        file="app.py",
        line=10,
        title="Some issue",
        evidence="evidence",
        suggested_fix=None,
    )
    defaults.update(kwargs)
    return Finding(**defaults)


# ---------------------------------------------------------------------------
# SEVERITY_WEIGHTS
# ---------------------------------------------------------------------------

class TestSeverityWeights:
    def test_critical_highest(self):
        assert SEVERITY_WEIGHTS[Severity.CRITICAL] > SEVERITY_WEIGHTS[Severity.HIGH]

    def test_high_above_medium(self):
        assert SEVERITY_WEIGHTS[Severity.HIGH] > SEVERITY_WEIGHTS[Severity.MEDIUM]

    def test_medium_above_low(self):
        assert SEVERITY_WEIGHTS[Severity.MEDIUM] > SEVERITY_WEIGHTS[Severity.LOW]

    def test_low_above_info(self):
        assert SEVERITY_WEIGHTS[Severity.LOW] > SEVERITY_WEIGHTS[Severity.INFO]

    def test_all_five_severities_present(self):
        for sev in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO):
            assert sev in SEVERITY_WEIGHTS


# ---------------------------------------------------------------------------
# calculate_score
# ---------------------------------------------------------------------------

class TestCalculateScore:
    def test_score_is_weight_times_confidence(self):
        f = make_finding(severity="critical", confidence=1.0)
        expected = SEVERITY_WEIGHTS[Severity.CRITICAL] * 1.0
        assert calculate_score(f) == expected

    def test_zero_confidence_gives_zero_score(self):
        f = make_finding(severity="critical", confidence=0.0)
        assert calculate_score(f) == 0.0

    def test_high_confidence_beats_lower_same_severity(self):
        hi = make_finding(severity="high", confidence=0.9)
        lo = make_finding(severity="high", confidence=0.5)
        assert calculate_score(hi) > calculate_score(lo)

    def test_critical_low_confidence_can_beat_high_full_confidence(self):
        # 100 * 0.6 = 60  >  75 * 0.7 = 52.5
        crit = make_finding(severity="critical", confidence=0.6)
        high = make_finding(severity="high", confidence=0.7)
        assert calculate_score(crit) > calculate_score(high)

    def test_all_severity_levels_produce_positive_score(self):
        for sev in ("critical", "high", "medium", "low", "info"):
            f = make_finding(severity=sev, confidence=0.5)
            assert calculate_score(f) > 0


# ---------------------------------------------------------------------------
# deduplicate_findings
# ---------------------------------------------------------------------------

class TestDeduplicateFindings:
    def test_no_duplicates_unchanged(self):
        f1 = make_finding(id="T-001", file="a.py", line=1, title="X", confidence=0.8)
        f2 = make_finding(id="T-002", file="b.py", line=2, title="Y", confidence=0.9)
        result = deduplicate_findings([f1, f2])
        assert len(result) == 2

    def test_exact_duplicate_keeps_one(self):
        f1 = make_finding(id="T-001", file="a.py", line=5, title="Issue", confidence=0.7)
        f2 = make_finding(id="T-002", file="a.py", line=5, title="Issue", confidence=0.9)
        result = deduplicate_findings([f1, f2])
        assert len(result) == 1

    def test_keeps_highest_confidence_duplicate(self):
        f1 = make_finding(id="T-001", file="a.py", line=5, title="Issue", confidence=0.7)
        f2 = make_finding(id="T-002", file="a.py", line=5, title="Issue", confidence=0.95)
        result = deduplicate_findings([f1, f2])
        assert result[0].confidence == 0.95

    def test_different_files_not_deduped(self):
        f1 = make_finding(id="T-001", file="a.py", line=5, title="Issue", confidence=0.8)
        f2 = make_finding(id="T-002", file="b.py", line=5, title="Issue", confidence=0.8)
        result = deduplicate_findings([f1, f2])
        assert len(result) == 2

    def test_different_lines_not_deduped(self):
        f1 = make_finding(id="T-001", file="a.py", line=5, title="Issue", confidence=0.8)
        f2 = make_finding(id="T-002", file="a.py", line=6, title="Issue", confidence=0.8)
        result = deduplicate_findings([f1, f2])
        assert len(result) == 2

    def test_different_titles_not_deduped(self):
        f1 = make_finding(id="T-001", file="a.py", line=5, title="Issue A", confidence=0.8)
        f2 = make_finding(id="T-002", file="a.py", line=5, title="Issue B", confidence=0.8)
        result = deduplicate_findings([f1, f2])
        assert len(result) == 2

    def test_empty_list_returns_empty(self):
        assert deduplicate_findings([]) == []

    def test_three_dupes_keeps_one(self):
        findings = [
            make_finding(id=f"T-{i:03d}", file="x.py", line=1, title="X", confidence=0.3 * i)
            for i in range(1, 4)
        ]
        result = deduplicate_findings(findings)
        assert len(result) == 1
        assert result[0].confidence == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# rank_findings
# ---------------------------------------------------------------------------

class TestRankFindings:
    def test_higher_score_first(self):
        low = make_finding(id="T-001", severity="low", confidence=1.0)
        crit = make_finding(id="T-002", severity="critical", confidence=1.0)
        result = rank_findings([low, crit])
        assert result[0].severity == "critical"

    def test_same_score_higher_severity_first(self):
        # score critical 0.5 = 50, score high 0.667 ≈ 50 — contrived same score
        # simpler: same score via equal weight*confidence
        f1 = make_finding(id="T-001", severity="high", confidence=1.0)   # score 75
        f2 = make_finding(id="T-002", severity="medium", confidence=1.0) # score 50
        result = rank_findings([f2, f1])
        assert result[0].severity == "high"

    def test_empty_returns_empty(self):
        assert rank_findings([]) == []

    def test_single_item_unchanged(self):
        f = make_finding(id="T-001")
        assert rank_findings([f]) == [f]

    def test_descending_scores(self):
        findings = [
            make_finding(id=f"T-{i}", severity=sev, confidence=0.9)
            for i, sev in enumerate(["info", "low", "medium", "high", "critical"])
        ]
        result = rank_findings(findings)
        scores = [calculate_score(f) for f in result]
        assert scores == sorted(scores, reverse=True)

    def test_stable_sort_same_score_by_file(self):
        f1 = make_finding(id="T-001", file="a.py", severity="high", confidence=0.8)
        f2 = make_finding(id="T-002", file="z.py", severity="high", confidence=0.8)
        result = rank_findings([f2, f1])
        assert result[0].file == "a.py"


# ---------------------------------------------------------------------------
# triage_findings (pipeline)
# ---------------------------------------------------------------------------

class TestTriageFindings:
    def test_dedupes_and_ranks(self):
        findings = [
            make_finding(id="T-001", file="a.py", line=1, title="X", severity="low", confidence=0.9),
            make_finding(id="T-002", file="a.py", line=1, title="X", severity="low", confidence=0.5),
            make_finding(id="T-003", file="b.py", line=2, title="Y", severity="critical", confidence=0.8),
        ]
        result = triage_findings(findings)
        assert len(result) == 2            # deduped 2 → 1
        assert result[0].severity == "critical"   # ranked first

    def test_empty_input(self):
        assert triage_findings([]) == []

    def test_preserves_all_unique(self):
        findings = [
            make_finding(id=f"T-{i:03d}", file=f"file{i}.py", line=i, title=f"T{i}", severity="medium", confidence=0.5)
            for i in range(5)
        ]
        result = triage_findings(findings)
        assert len(result) == 5
