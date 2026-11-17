"""Triage: ranks findings by severity x confidence, deduplicates."""

from collections import defaultdict
from contractguard.models import Finding, Category, Severity


# Severity weights for ranking
SEVERITY_WEIGHTS = {
    Severity.CRITICAL: 100,
    Severity.HIGH: 75,
    Severity.MEDIUM: 50,
    Severity.LOW: 25,
    Severity.INFO: 10,
}


def calculate_score(finding: Finding) -> float:
    """Calculate triage score = severity_weight * confidence."""
    weight = SEVERITY_WEIGHTS.get(finding.severity, 0)
    return weight * finding.confidence


def deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    """Deduplicate findings by (file, line, title) keeping highest confidence."""
    # Group by (file, line, title)
    groups = defaultdict(list)
    for f in findings:
        key = (f.file, f.line, f.title)
        groups[key].append(f)

    # Keep highest confidence from each group
    deduped = []
    for group in groups.values():
        best = max(group, key=lambda f: f.confidence)
        deduped.append(best)

    return deduped


def rank_findings(findings: list[Finding]) -> list[Finding]:
    """Rank findings by score (descending), then by severity, then by file."""
    # Calculate scores
    scored = [(calculate_score(f), f) for f in findings]
    # Sort: score desc, severity weight desc, file asc, line asc
    severity_order = {s: i for i, s in enumerate([
        Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO
    ])}
    scored.sort(key=lambda x: (-x[0], severity_order.get(x[1].severity, 99), x[1].file, x[1].line or 0))
    return [f for _, f in scored]


def triage_findings(findings: list[Finding]) -> list[Finding]:
    """Full triage pipeline: deduplicate then rank."""
    deduped = deduplicate_findings(findings)
    return rank_findings(deduped)