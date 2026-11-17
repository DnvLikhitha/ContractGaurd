"""Pydantic models for ContractGuard findings, patches, and verification results."""

from enum import Enum
from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class Category(str, Enum):
    """Finding categories."""
    SECURITY = "security"
    DRIFT = "drift"
    SLOP = "slop"


class Severity(str, Enum):
    """Finding severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class VerificationStrength(str, Enum):
    """Strength of verification for a fix."""
    TESTS_PASSED = "TESTS_PASSED"
    SYNTAX_ONLY = "SYNTAX_ONLY"
    NO_VERIFIER = "NO_VERIFIER"


class FixStatus(str, Enum):
    """Status of a fix after verification."""
    VERIFIED = "VERIFIED"
    ROLLED_BACK = "ROLLED_BACK"
    SKIPPED = "SKIPPED"


class Finding(BaseModel):
    """A single finding from an auditor."""
    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(..., description="Unique identifier for this finding")
    category: Category = Field(..., description="Category of the finding")
    severity: Severity = Field(..., description="Severity level")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")
    file: str = Field(..., description="Relative path to the file")
    line: Optional[int] = Field(None, description="Line number (1-indexed), if applicable")
    title: str = Field(..., description="Brief title of the finding")
    evidence: str = Field(..., description="Code snippet or description supporting the finding")
    suggested_fix: Optional[str] = Field(None, description="Suggested fix description")


class Patch(BaseModel):
    """A patch to apply to fix a finding."""
    model_config = ConfigDict(use_enum_values=True)

    finding_id: str = Field(..., description="ID of the finding this patch addresses")
    file: str = Field(..., description="Relative path to the file to patch")
    search: str = Field(..., description="Exact string to search for (must match once)")
    replace: str = Field(..., description="String to replace with")
    description: str = Field(..., description="Human-readable description of the change")


class VerificationResult(BaseModel):
    """Result of verifying a patch in the sandbox."""
    model_config = ConfigDict(use_enum_values=True)

    finding_id: str = Field(..., description="ID of the finding that was patched")
    patch: Patch = Field(..., description="The patch that was applied")
    status: FixStatus = Field(..., description="Whether the patch was verified or rolled back")
    strength: VerificationStrength = Field(..., description="Strength of verification")
    verifier_used: str = Field(..., description="Name of verifier that ran (pytest, npm test, etc.)")
    baseline_passed: bool = Field(..., description="Whether baseline tests passed before patch")
    patch_passed: bool = Field(..., description="Whether tests passed after patch")
    output: str = Field(..., description="Verifier output (stdout/stderr)")
    error: Optional[str] = Field(None, description="Error message if verification failed unexpectedly")


class IndexedFile(BaseModel):
    """A file indexed from the repository."""
    model_config = ConfigDict(use_enum_values=True)

    path: str = Field(..., description="Relative path from repo root")
    is_contract: bool = Field(False, description="Whether this is a contract file")
    is_source: bool = Field(False, description="Whether this is a source file")
    language: Optional[str] = Field(None, description="Detected language (python, javascript, etc.)")
    content: str = Field(..., description="File content")


class ContractFiles(BaseModel):
    """Collection of contract files found in the repo."""
    readme: Optional[IndexedFile] = None
    env_example: Optional[IndexedFile] = None
    docker_compose: list[IndexedFile] = Field(default_factory=list)
    github_actions: list[IndexedFile] = Field(default_factory=list)
    manifests: list[IndexedFile] = Field(default_factory=list)
    config_files: list[IndexedFile] = Field(default_factory=list)
    openapi_specs: list[IndexedFile] = Field(default_factory=list)
    other: list[IndexedFile] = Field(default_factory=list)

    def all_contract_files(self) -> list[IndexedFile]:
        """Get all contract files as a flat list."""
        files = []
        if self.readme:
            files.append(self.readme)
        if self.env_example:
            files.append(self.env_example)
        files.extend(self.docker_compose)
        files.extend(self.github_actions)
        files.extend(self.manifests)
        files.extend(self.config_files)
        files.extend(self.openapi_specs)
        files.extend(self.other)
        return files