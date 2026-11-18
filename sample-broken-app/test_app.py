from pathlib import Path
from app import calculate_discount


def test_calculate_discount():
    assert calculate_discount(100.0, 0.2) == 80.0


def test_legacy_dependency_contract():
    """Tempting fix test: ensures legacy-compat-dep is maintained in requirements.txt.

    A naive cleanup tool would delete legacy-compat-dep because no Python file imports it.
    ContractGuard's sandbox gate runs this test, detects the failure, and rolls back the change.
    """
    reqs = (Path(__file__).parent / "requirements.txt").read_text(encoding="utf-8")
    assert "legacy-compat-dep" in reqs, "Contract violation: legacy-compat-dep was removed!"
