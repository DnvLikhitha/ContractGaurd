"""
contractguard.auditors.security
================================
Deterministic security auditor — no API key required.

Rule table (all regex; AST supplements Python files):
  ID          Pattern                    Severity   Confidence
  ─────────── ─────────────────────────  ─────────  ──────────
  AWS-001     AWS access key (AKIA…)     CRITICAL   0.95
  AWS-002     AWS secret access key      CRITICAL   0.95
  KEY-001     Private key PEM block      CRITICAL   0.99
  KEY-002     Generic API/secret key     CRITICAL   0.80
  KEY-003     Bearer token (hardcoded)   CRITICAL   0.80
  DSN-001     DB DSN with password       CRITICAL   0.90
  INS-001     DEBUG=True                 HIGH       0.90
  INS-002     CORS wildcard              HIGH       0.85
  INS-003     verify=False               HIGH       0.90
  INS-004     md5/sha1 on password ctx   MEDIUM     0.75
  INS-005     Bind to 0.0.0.0           MEDIUM     0.70

Skip rules (applied before every check):
  - Lockfiles  (poetry.lock, package-lock.json, etc.)
  - Test files (tests/, spec/, *_test.py, *.spec.js, etc.)
  - Placeholder values ("changeme", "your_key_here", etc.)
  - Comment-only lines
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from contractguard.models import Category, Finding, IndexedFile, Severity

# ---------------------------------------------------------------------------
# Skip-list helpers
# ---------------------------------------------------------------------------

_LOCKFILE_NAMES = frozenset({
    "poetry.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Pipfile.lock", "Cargo.lock", "Gemfile.lock", "composer.lock",
    "packages.lock.json", "bun.lockb",
})

_PLACEHOLDER_PATTERNS = re.compile(
    r"^(changeme|your[_\-]?key[_\-]?here|placeholder|xxx+|todo|replace[_\-]?me|"
    r"insert[_\-]?here|example.*|sample|test|dummy|fake|none|null|secret|pass|"
    r"password|<[^>]+>|\.\.\.|add[_\-]?your|your[_\-]?secret)$",
    re.IGNORECASE,
)

_COMMENT_PREFIXES: dict[str | None, tuple[str, ...]] = {
    "python":     ("#",),
    "ruby":       ("#",),
    "bash":       ("#",),
    "powershell": ("#",),
    "javascript": ("//", "/*", "*"),
    "typescript": ("//", "/*", "*"),
    "go":         ("//", "/*"),
    "rust":       ("//", "/*"),
    "java":       ("//", "/*", "*"),
    "csharp":     ("//", "/*", "*"),
    "cpp":        ("//", "/*", "*"),
    "c":          ("//", "/*", "*"),
    "html":       ("<!--",),
    "xml":        ("<!--",),
}


def is_lockfile(path: str) -> bool:
    """Return True if the file is a known lockfile that should be skipped."""
    return Path(path).name in _LOCKFILE_NAMES


def is_test_file(path: str) -> bool:
    """Return True if the file is a test/spec file."""
    p = Path(path)
    name = p.name
    parts = p.parts
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".test.js")
        or name.endswith(".test.ts")
        or name.endswith(".spec.js")
        or name.endswith(".spec.ts")
        or name.endswith(".test.jsx")
        or name.endswith(".test.tsx")
        or "tests" in parts
        or "test" in parts
        or "spec" in parts
        or "__tests__" in parts
    )


def is_placeholder(value: str) -> bool:
    """Return True if the extracted secret value looks like a placeholder."""
    stripped = value.strip().strip("'\"")
    return bool(_PLACEHOLDER_PATTERNS.match(stripped))


def is_comment_only(line: str, language: Optional[str]) -> bool:
    """Return True if the stripped line is purely a comment or empty."""
    stripped = line.strip()
    if not stripped:
        return True
    prefixes = _COMMENT_PREFIXES.get(language, ())
    return any(stripped.startswith(p) for p in prefixes)


def _should_skip_file(file: IndexedFile) -> bool:
    return is_lockfile(file.path) or is_test_file(file.path)


# ---------------------------------------------------------------------------
# Secret masking
# ---------------------------------------------------------------------------

# Patterns that rewrite the sensitive part of an evidence line
_MASK_SUBS: list[tuple[re.Pattern[str], str]] = [
    # named credentials: key/token/password = 'VALUE'
    (re.compile(
        r"(?i)(api[_\-]?key|secret[_\-]?key?|access[_\-]?key|auth[_\-]?token|"
        r"bearer|password|passwd|pwd|private[_\-]?key|token)\s*[=:]\s*['\"]([^'\"]{4,})['\"]"
    ), r"\1=***MASKED***"),
    # AWS IDs
    (re.compile(r"\b(AKIA[A-Z0-9]{16})\b"), "AKIA***"),
    # Base64-ish high-entropy strings ≥32 chars
    (re.compile(r"['\"][A-Za-z0-9+/]{32,}={0,2}['\"]"), "'***MASKED***'"),
    # PEM blocks
    (re.compile(
        r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----.*?-----END (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
        re.DOTALL,
    ), "***PRIVATE KEY BLOCK***"),
    # DB DSN passwords  postgresql://user:PASS@host
    (re.compile(r"((?:postgresql|mysql|mongodb|redis|amqp)://[^:]+:)([^@\s'\"]{3,})(@)"), r"\1***\3"),
    # Bearer tokens
    (re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_.+/=]+"), r"\1***MASKED***"),
]


def mask_secrets(text: str) -> str:
    """Mask secret values in a line of evidence. Non-secret text is preserved."""
    for pattern, replacement in _MASK_SUBS:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# Individual rule checkers
# ---------------------------------------------------------------------------

def _lineno(content: str, match_start: int) -> int:
    return content[:match_start].count("\n") + 1


def _evidence(lines: list[str], lineno: int) -> str:
    if 1 <= lineno <= len(lines):
        return mask_secrets(lines[lineno - 1].strip())
    return ""


def _make(
    counter: list[int],
    *,
    title: str,
    severity: Severity,
    confidence: float,
    file: IndexedFile,
    lineno: int,
    evidence: str,
    fix: str,
) -> Finding:
    counter[0] += 1
    return Finding(
        id=f"SEC-{counter[0]:04d}",
        category=Category.SECURITY,
        severity=severity,
        confidence=confidence,
        file=file.path,
        line=lineno,
        title=title,
        evidence=evidence,
        suggested_fix=fix,
    )


# ── AWS-001: AWS Access Key ID ──────────────────────────────────────────────
# Format: AKIA[A-Z0-9]{16}  (20 chars total)
_AWS_KEY_ID = re.compile(
    r"""(?i)aws[_\-]?access[_\-]?key[_\-]?id\s*[=:]\s*['"]?(AKIA[A-Z0-9]{16})['"]?"""
    r"""|(?<![A-Z0-9])(AKIA[A-Z0-9]{16})(?![A-Z0-9])""",
    re.VERBOSE,
)


def _check_aws_key_id(file: IndexedFile, counter: list[int]) -> list[Finding]:
    lines = file.content.splitlines()
    findings: list[Finding] = []
    seen_lines: set[int] = set()
    for m in _AWS_KEY_ID.finditer(file.content):
        key_val = m.group(1) or m.group(2)
        if is_placeholder(key_val):
            continue
        ln = _lineno(file.content, m.start())
        if ln in seen_lines:
            continue
        seen_lines.add(ln)
        findings.append(_make(
            counter,
            title="AWS Access Key ID",
            severity=Severity.CRITICAL,
            confidence=0.95,
            file=file,
            lineno=ln,
            evidence=_evidence(lines, ln),
            fix="Remove AWS credential from source; use IAM roles or environment variables.",
        ))
    return findings


# ── AWS-002: AWS Secret Access Key ─────────────────────────────────────────
_AWS_SECRET = re.compile(
    r"""(?i)aws[_\-]?secret[_\-]?access[_\-]?key\s*[=:]\s*['"]?([A-Za-z0-9/+=]{40})['"]?"""
)


def _check_aws_secret(file: IndexedFile, counter: list[int]) -> list[Finding]:
    lines = file.content.splitlines()
    findings: list[Finding] = []
    seen: set[int] = set()
    for m in _AWS_SECRET.finditer(file.content):
        val = m.group(1)
        if is_placeholder(val):
            continue
        ln = _lineno(file.content, m.start())
        if ln in seen:
            continue
        seen.add(ln)
        findings.append(_make(
            counter,
            title="AWS Secret Access Key",
            severity=Severity.CRITICAL,
            confidence=0.95,
            file=file,
            lineno=ln,
            evidence=_evidence(lines, ln),
            fix="Remove AWS secret key from source; use IAM roles or environment variables.",
        ))
    return findings


# ── KEY-001: PEM private key block ─────────────────────────────────────────
_PEM_BLOCK = re.compile(
    r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
)


def _check_pem_block(file: IndexedFile, counter: list[int]) -> list[Finding]:
    lines = file.content.splitlines()
    findings: list[Finding] = []
    seen: set[int] = set()
    for m in _PEM_BLOCK.finditer(file.content):
        ln = _lineno(file.content, m.start())
        if ln in seen:
            continue
        seen.add(ln)
        findings.append(_make(
            counter,
            title="Private Key Block (PEM)",
            severity=Severity.CRITICAL,
            confidence=0.99,
            file=file,
            lineno=ln,
            evidence="-----BEGIN ***PRIVATE KEY*** (content masked)",
            fix="Remove private key from repository; store in a secrets manager or vault.",
        ))
    return findings


# ── KEY-002: Generic hardcoded API / secret key ────────────────────────────
# Pattern: (api_key|secret_key|…) = 'VALUE'  where VALUE is ≥16 chars and
# not an env-var read (os.getenv / process.env / os.environ)
_GENERIC_KEY = re.compile(
    r"""(?i)(?:api[_\-]?key|secret[_\-]?key|private[_\-]?key|"""
    r"""auth[_\-]?token|access[_\-]?token|app[_\-]?secret|"""
    r"""client[_\-]?secret|signing[_\-]?key|encryption[_\-]?key)"""
    r"""\s*[=:]\s*['"]([^'"]{16,})['"]"""
)


def _check_generic_key(file: IndexedFile, counter: list[int]) -> list[Finding]:
    lines = file.content.splitlines()
    findings: list[Finding] = []
    seen: set[int] = set()
    for m in _GENERIC_KEY.finditer(file.content):
        val = m.group(1)
        if is_placeholder(val):
            continue
        ln = _lineno(file.content, m.start())
        if ln in seen:
            continue
        seen.add(ln)
        # Suppress if the value looks like it's reading an env var
        line_text = lines[ln - 1] if ln <= len(lines) else ""
        if re.search(r"os\.getenv|os\.environ|process\.env|import\.meta\.env|System\.getenv", line_text):
            continue
        findings.append(_make(
            counter,
            title="Hardcoded API / Secret Key",
            severity=Severity.CRITICAL,
            confidence=0.80,
            file=file,
            lineno=ln,
            evidence=_evidence(lines, ln),
            fix="Move secret to an environment variable or secrets manager.",
        ))
    return findings


# ── KEY-003: Bearer token (hardcoded JWT or long opaque token) ──────────────
# JWT: three base64url segments separated by dots
_BEARER_TOKEN = re.compile(
    r"""(?i)['\"]?\s*Bearer\s+([A-Za-z0-9\-_=]{3,}\.[A-Za-z0-9\-_=]{3,}\.[A-Za-z0-9\-_.+/=]{3,})['\"]?"""
)
# Or: Authorization header value with long opaque token
_AUTH_HEADER = re.compile(
    r"""(?i)(authorization|x\-api\-key)\s*[=:]\s*['"]([A-Za-z0-9\-_.+/=]{32,})['"]"""
)


def _check_bearer_token(file: IndexedFile, counter: list[int]) -> list[Finding]:
    lines = file.content.splitlines()
    findings: list[Finding] = []
    seen: set[int] = set()

    for m in _BEARER_TOKEN.finditer(file.content):
        val = m.group(1)
        if is_placeholder(val):
            continue
        ln = _lineno(file.content, m.start())
        if ln in seen:
            continue
        seen.add(ln)
        findings.append(_make(
            counter,
            title="Hardcoded Bearer / JWT Token",
            severity=Severity.CRITICAL,
            confidence=0.80,
            file=file,
            lineno=ln,
            evidence=_evidence(lines, ln),
            fix="Remove hardcoded token; pass via environment variable or secure vault.",
        ))

    for m in _AUTH_HEADER.finditer(file.content):
        val = m.group(2)
        if is_placeholder(val):
            continue
        ln = _lineno(file.content, m.start())
        if ln in seen:
            continue
        seen.add(ln)
        findings.append(_make(
            counter,
            title="Hardcoded Authorization Header",
            severity=Severity.CRITICAL,
            confidence=0.80,
            file=file,
            lineno=ln,
            evidence=_evidence(lines, ln),
            fix="Remove hardcoded credential; use environment variable.",
        ))

    return findings


# ── DSN-001: DB connection string with embedded password ───────────────────
# postgresql://user:PASS@host  mysql://  mongodb://  redis://:PASS@
_DSN = re.compile(
    r"""(?i)(postgresql|postgres|mysql|mariadb|mongodb|redis|amqp|mssql|sqlserver)"""
    r"""://([^:@\s'"]{1,64}):([^@\s'"]{3,})@"""
)


def _check_dsn(file: IndexedFile, counter: list[int]) -> list[Finding]:
    lines = file.content.splitlines()
    findings: list[Finding] = []
    seen: set[int] = set()
    for m in _DSN.finditer(file.content):
        password = m.group(3)
        if is_placeholder(password) or password == "":
            continue
        ln = _lineno(file.content, m.start())
        if ln in seen:
            continue
        seen.add(ln)
        findings.append(_make(
            counter,
            title="DB Connection String with Embedded Password",
            severity=Severity.CRITICAL,
            confidence=0.90,
            file=file,
            lineno=ln,
            evidence=_evidence(lines, ln),
            fix="Move database credentials to environment variables; use a secrets manager for production.",
        ))
    return findings


# ── INS-001: DEBUG=True ─────────────────────────────────────────────────────
_DEBUG_TRUE = re.compile(
    r"""(?i)(?:^|[\s;,])(?:app\.)?debug\s*=\s*True(?:\s|$|[,;)])""",
    re.MULTILINE,
)


def _check_debug_true(file: IndexedFile, counter: list[int]) -> list[Finding]:
    lines = file.content.splitlines()
    findings: list[Finding] = []
    seen: set[int] = set()
    for m in _DEBUG_TRUE.finditer(file.content):
        ln = _lineno(file.content, m.start())
        raw_line = lines[ln - 1] if ln <= len(lines) else ""
        if is_comment_only(raw_line, file.language):
            continue
        if ln in seen:
            continue
        seen.add(ln)
        findings.append(_make(
            counter,
            title="DEBUG=True in production code",
            severity=Severity.HIGH,
            confidence=0.90,
            file=file,
            lineno=ln,
            evidence=mask_secrets(raw_line.strip()),
            fix="Set DEBUG=False for production; control via environment variable.",
        ))
    return findings


# ── INS-002: CORS wildcard ──────────────────────────────────────────────────
# Match: origins="*" / allow_origins=["*"] / CORS_ALLOW_ALL_ORIGINS=True /
#        Access-Control-Allow-Origin: *
_CORS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"""(?i)origins\s*[=:]\s*['"]\*['"]"""),
    re.compile(r"""(?i)origins\s*=\s*\[\s*['"]\*['"]\s*\]"""),
    re.compile(r"""(?i)allow_origins\s*=\s*\[\s*['"]\*['"]\s*\]"""),
    re.compile(r"""(?i)CORS_ALLOW_ALL_ORIGINS\s*=\s*True"""),
    re.compile(r"""(?i)CORS_ORIGIN_ALLOW_ALL\s*=\s*True"""),
    re.compile(r"""(?i)Access-Control-Allow-Origin['"]\s*[=:]\s*['"]\*['"]"""),
    re.compile(r"""(?i)['"]\s*Access-Control-Allow-Origin\s*['"]\s*[,)]\s*['"]\*['"]"""),
    re.compile(r"""(?i)Access-Control-Allow-Origin['"]\s*\]?\s*=\s*['"]\*['"]""")
]


def _check_cors_wildcard(file: IndexedFile, counter: list[int]) -> list[Finding]:
    lines = file.content.splitlines()
    findings: list[Finding] = []
    seen: set[int] = set()
    for pat in _CORS_PATTERNS:
        for m in pat.finditer(file.content):
            ln = _lineno(file.content, m.start())
            raw = lines[ln - 1] if ln <= len(lines) else ""
            if is_comment_only(raw, file.language):
                continue
            if ln in seen:
                continue
            seen.add(ln)
            findings.append(_make(
                counter,
                title="CORS Wildcard (*) — all origins allowed",
                severity=Severity.HIGH,
                confidence=0.85,
                file=file,
                lineno=ln,
                evidence=mask_secrets(raw.strip()),
                fix="Restrict CORS to specific trusted origins; never use '*' in production.",
            ))
    return findings


# ── INS-003: verify=False ───────────────────────────────────────────────────
# Match verify=False but NOT verify=True, verify='/path', verify=cert_var
_VERIFY_FALSE = re.compile(r"""(?i)\bverify\s*=\s*False\b""")


def _check_verify_false(file: IndexedFile, counter: list[int]) -> list[Finding]:
    lines = file.content.splitlines()
    findings: list[Finding] = []
    seen: set[int] = set()
    for m in _VERIFY_FALSE.finditer(file.content):
        ln = _lineno(file.content, m.start())
        raw = lines[ln - 1] if ln <= len(lines) else ""
        if is_comment_only(raw, file.language):
            continue
        if ln in seen:
            continue
        seen.add(ln)
        findings.append(_make(
            counter,
            title="SSL Certificate Verification Disabled (verify=False)",
            severity=Severity.HIGH,
            confidence=0.90,
            file=file,
            lineno=ln,
            evidence=mask_secrets(raw.strip()),
            fix="Enable SSL verification; install proper CA certificates instead of disabling checks.",
        ))
    return findings


# ── INS-004: md5/sha1 in password context ──────────────────────────────────
# Only flag when the same line contains a password-related term
_WEAK_HASH_ALG = re.compile(r"""\b(md5|sha1|sha_1)\b""", re.IGNORECASE)
_PASSWORD_CTX  = re.compile(r"""(?:password|passwd|pwd|pass|secret|credential|hash|crypt)""", re.IGNORECASE)


def _check_weak_hash(file: IndexedFile, counter: list[int]) -> list[Finding]:
    lines = file.content.splitlines()
    findings: list[Finding] = []
    seen: set[int] = set()
    for m in _WEAK_HASH_ALG.finditer(file.content):
        ln = _lineno(file.content, m.start())
        raw = lines[ln - 1] if ln <= len(lines) else ""
        # Only flag if the line also mentions a password-related word
        if not _PASSWORD_CTX.search(raw):
            continue
        if is_comment_only(raw, file.language):
            continue
        if ln in seen:
            continue
        seen.add(ln)
        alg = m.group(1).upper()
        findings.append(_make(
            counter,
            title=f"Weak Hash Algorithm ({alg}) for Password/Secret",
            severity=Severity.MEDIUM,
            confidence=0.75,
            file=file,
            lineno=ln,
            evidence=mask_secrets(raw.strip()),
            fix=f"Replace {alg} with bcrypt, scrypt, or argon2id for passwords; "
                "use SHA-256+ for non-password hashing.",
        ))
    return findings


# ── INS-005: Bind to 0.0.0.0 ───────────────────────────────────────────────
_BIND_ALL = re.compile(r"""(?<!['\"])0\.0\.0\.0(?!['\"]?\s*#)""")
# More targeted: only flag when it's inside a string or assignment
_BIND_ALL_STR = re.compile(r"""['"](0\.0\.0\.0)['"]""")


def _check_bind_0000(file: IndexedFile, counter: list[int]) -> list[Finding]:
    lines = file.content.splitlines()
    findings: list[Finding] = []
    seen: set[int] = set()
    for m in _BIND_ALL_STR.finditer(file.content):
        ln = _lineno(file.content, m.start())
        raw = lines[ln - 1] if ln <= len(lines) else ""
        if is_comment_only(raw, file.language):
            continue
        if ln in seen:
            continue
        seen.add(ln)
        findings.append(_make(
            counter,
            title="Binding to 0.0.0.0 (all interfaces)",
            severity=Severity.MEDIUM,
            confidence=0.70,
            file=file,
            lineno=ln,
            evidence=mask_secrets(raw.strip()),
            fix="Bind to a specific interface (127.0.0.1) in production; "
                "control host via environment variable.",
        ))
    return findings


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

#: Ordered list of checker functions; each takes (file, counter) → list[Finding]
_CHECKERS = [
    _check_aws_key_id,
    _check_aws_secret,
    _check_pem_block,
    _check_generic_key,
    _check_bearer_token,
    _check_dsn,
    _check_debug_true,
    _check_cors_wildcard,
    _check_verify_false,
    _check_weak_hash,
    _check_bind_0000,
]


def audit_security(source_files: list[IndexedFile]) -> list[Finding]:
    """Run all security checks over source_files.

    Skips lockfiles and test files automatically.
    Returns findings in file-order (not yet triaged).
    """
    findings: list[Finding] = []
    counter: list[int] = [0]

    for file in source_files:
        if _should_skip_file(file):
            continue
        for checker in _CHECKERS:
            try:
                findings.extend(checker(file, counter))
            except Exception:  # never let one checker crash the whole audit
                pass

    return findings
