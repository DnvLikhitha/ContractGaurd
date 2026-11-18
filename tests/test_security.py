"""
Tests for contractguard.auditors.security (Phase 3 rewrite).

Written BEFORE implementation per CLAUDE.md rules.
Each test uses a minimal inline fixture snippet so it documents
exactly what the rule catches and what it must not catch.

Fixture snippets are realistic but synthetic — no real credentials.
"""

from __future__ import annotations

import pytest
from contractguard.models import IndexedFile
from contractguard.auditors.security import (
    audit_security,
    is_lockfile,
    is_placeholder,
    is_test_file,
    mask_secrets,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def py_file(content: str, path: str = "app.py") -> IndexedFile:
    return IndexedFile(path=path, is_source=True, language="python", content=content)


def js_file(content: str, path: str = "index.js") -> IndexedFile:
    return IndexedFile(path=path, is_source=True, language="javascript", content=content)


def generic_file(content: str, path: str = "config.yml") -> IndexedFile:
    return IndexedFile(path=path, is_source=True, language="yaml", content=content)


def titles(findings) -> list[str]:
    return [f.title for f in findings]


def has_title(findings, fragment: str) -> bool:
    return any(fragment.lower() in t.lower() for t in titles(findings))


# ===========================================================================
# Helper function tests
# ===========================================================================

class TestIsLockfile:
    def test_poetry_lock(self):         assert is_lockfile("poetry.lock")
    def test_package_lock(self):        assert is_lockfile("package-lock.json")
    def test_yarn_lock(self):           assert is_lockfile("yarn.lock")
    def test_pipfile_lock(self):        assert is_lockfile("Pipfile.lock")
    def test_cargo_lock(self):          assert is_lockfile("Cargo.lock")
    def test_gemfile_lock(self):        assert is_lockfile("Gemfile.lock")
    def test_regular_py(self):          assert not is_lockfile("app.py")
    def test_requirements_txt(self):    assert not is_lockfile("requirements.txt")


class TestIsTestFile:
    def test_test_prefix(self):         assert is_test_file("tests/test_app.py")
    def test_test_suffix(self):         assert is_test_file("src/app_test.py")
    def test_spec_suffix_js(self):      assert is_test_file("app.spec.js")
    def test_test_suffix_js(self):      assert is_test_file("app.test.js")
    def test_tests_dir(self):           assert is_test_file("tests/something.py")
    def test_spec_dir(self):            assert is_test_file("spec/models.rb")
    def test_regular_app(self):         assert not is_test_file("src/app.py")
    def test_conftest(self):            assert not is_test_file("conftest.py")


class TestIsPlaceholder:
    def test_changeme(self):            assert is_placeholder("changeme")
    def test_your_key_here(self):       assert is_placeholder("your_key_here")
    def test_placeholder(self):         assert is_placeholder("placeholder")
    def test_xxx(self):                 assert is_placeholder("xxx")
    def test_todo(self):                assert is_placeholder("todo")
    def test_replace_me(self):          assert is_placeholder("replace_me")
    def test_example(self):             assert is_placeholder("example_value")
    def test_real_secret(self):         assert not is_placeholder("AKIAIOSFODNN7EXAMPLE1")
    def test_real_long_string(self):    assert not is_placeholder("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")


class TestMaskSecrets:
    def test_masks_api_key(self):
        line = "api_key = 'supersecretvalue123456789'"
        assert "supersecretvalue" not in mask_secrets(line)
        assert "MASKED" in mask_secrets(line)

    def test_masks_private_key_block(self):
        blob = "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----"
        assert "MIIe" not in mask_secrets(blob).upper()
        assert "MASKED" in mask_secrets(blob).upper() or "PRIVATE KEY" in mask_secrets(blob)

    def test_preserves_non_secret_text(self):
        line = "x = 1  # just a number"
        assert mask_secrets(line) == line

    def test_masks_bearer_token(self):
        line = 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.SomeSignature123456789'
        result = mask_secrets(line)
        assert "SomeSignature" not in result


# ===========================================================================
# AWS access key (CRITICAL, 0.95)
# ===========================================================================

class TestAWSAccessKey:
    REAL = 'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"'
    REAL2 = "aws_access_key_id = 'AKIAJSIE27AJDOFM1234'"
    PLACEHOLDER = 'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"'  # canonical AWS example

    def test_detects_aws_access_key(self):
        f = py_file(self.REAL)
        findings = audit_security([f])
        assert has_title(findings, "AWS Access Key"), titles(findings)

    def test_detects_aws_access_key_lowercase(self):
        f = py_file(self.REAL2)
        findings = audit_security([f])
        assert has_title(findings, "AWS Access Key"), titles(findings)

    def test_severity_is_critical(self):
        f = py_file(self.REAL)
        findings = [x for x in audit_security([f]) if "AWS Access Key" in x.title]
        assert findings, "No AWS finding"
        assert findings[0].severity == "critical"

    def test_confidence_is_high(self):
        f = py_file(self.REAL)
        findings = [x for x in audit_security([f]) if "AWS Access Key" in x.title]
        assert findings[0].confidence >= 0.9

    def test_evidence_is_masked(self):
        f = py_file(self.REAL)
        findings = [x for x in audit_security([f]) if "AWS Access Key" in x.title]
        assert "AKIAIOFS" not in findings[0].evidence

    def test_skipped_in_test_file(self):
        f = py_file(self.REAL, path="tests/test_config.py")
        findings = [x for x in audit_security([f]) if "AWS Access Key" in x.title]
        assert not findings

    def test_skipped_in_lockfile(self):
        f = IndexedFile(path="poetry.lock", is_source=True, language=None, content=self.REAL)
        findings = [x for x in audit_security([f]) if "AWS Access Key" in x.title]
        assert not findings


# ===========================================================================
# AWS secret access key (CRITICAL, 0.95)
# ===========================================================================

class TestAWSSecretKey:
    REAL = 'AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"'

    def test_detects_aws_secret_key(self):
        f = py_file(self.REAL)
        findings = audit_security([f])
        assert has_title(findings, "AWS Secret"), titles(findings)

    def test_severity_is_critical(self):
        f = py_file(self.REAL)
        findings = [x for x in audit_security([f]) if "AWS Secret" in x.title]
        assert findings[0].severity == "critical"

    def test_evidence_masked(self):
        f = py_file(self.REAL)
        findings = [x for x in audit_security([f]) if "AWS Secret" in x.title]
        assert "wJalrXUtn" not in findings[0].evidence


# ===========================================================================
# Private key block (CRITICAL, 0.99)
# ===========================================================================

class TestPrivateKeyBlock:
    RSA = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0Z3VS\n-----END RSA PRIVATE KEY-----"
    EC  = "-----BEGIN EC PRIVATE KEY-----\nMHQCAQEEIOJ\n-----END EC PRIVATE KEY-----"
    SSH = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXkt\n-----END OPENSSH PRIVATE KEY-----"

    def test_rsa_private_key(self):
        f = py_file(self.RSA)
        assert has_title(audit_security([f]), "Private Key"), titles(audit_security([f]))

    def test_ec_private_key(self):
        f = py_file(self.EC)
        assert has_title(audit_security([f]), "Private Key"), titles(audit_security([f]))

    def test_openssh_private_key(self):
        f = py_file(self.SSH)
        assert has_title(audit_security([f]), "Private Key"), titles(audit_security([f]))

    def test_severity_is_critical(self):
        f = py_file(self.RSA)
        findings = [x for x in audit_security([f]) if "Private Key" in x.title]
        assert findings[0].severity == "critical"

    def test_confidence_near_one(self):
        f = py_file(self.RSA)
        findings = [x for x in audit_security([f]) if "Private Key" in x.title]
        assert findings[0].confidence >= 0.95

    def test_evidence_masked(self):
        f = py_file(self.RSA)
        findings = [x for x in audit_security([f]) if "Private Key" in x.title]
        assert "MIIEowIBAAK" not in findings[0].evidence


# ===========================================================================
# Generic API key / bearer token (CRITICAL, 0.80)
# ===========================================================================

class TestGenericApiKey:
    API_KEY   = "api_key = 'sk-realDeadBeefFeed1234567890abcdef12345678'"
    BEARER    = 'headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"}'
    SAFE_ENV  = 'api_key = os.getenv("API_KEY")'          # reading from env — not a secret
    PLACEHOLDER_LINE = "api_key = 'changeme'"

    def test_detects_api_key(self):
        f = py_file(self.API_KEY)
        assert has_title(audit_security([f]), "API"), titles(audit_security([f]))

    def test_detects_bearer_token(self):
        f = py_file(self.BEARER)
        findings = audit_security([f])
        assert has_title(findings, "Bearer") or has_title(findings, "Token") or has_title(findings, "API"), titles(findings)

    def test_placeholder_not_flagged(self):
        f = py_file(self.PLACEHOLDER_LINE)
        findings = [x for x in audit_security([f]) if "API" in x.title]
        assert not findings, f"Should skip placeholder, got: {titles(findings)}"

    def test_env_var_read_not_flagged(self):
        # Reading an env var is NOT a hardcoded secret
        f = py_file(self.SAFE_ENV)
        # May still fire on other patterns but not on 'api_key = os.getenv(...)'
        findings = audit_security([f])
        # None of the findings should have evidence containing "os.getenv"
        for finding in findings:
            assert "os.getenv" not in finding.evidence or "MASKED" in finding.evidence

    def test_severity_is_critical(self):
        f = py_file(self.API_KEY)
        findings = [x for x in audit_security([f]) if "API" in x.title or "Secret" in x.title]
        if findings:
            assert findings[0].severity == "critical"


# ===========================================================================
# DB connection string with embedded password (CRITICAL, 0.90)
# ===========================================================================

class TestDbConnectionString:
    PG_DSN  = 'DATABASE_URL = "postgresql://admin:sup3rS3cr3t@db.example.com:5432/mydb"'
    MY_DSN  = 'conn = "mysql://root:hunter2@localhost/app"'
    SAFE    = 'DATABASE_URL = os.environ["DATABASE_URL"]'
    EMPTY   = 'DATABASE_URL = "postgresql://user:@localhost/db"'  # empty password

    def test_detects_pg_dsn(self):
        f = py_file(self.PG_DSN)
        assert has_title(audit_security([f]), "Connection") or has_title(audit_security([f]), "Password") or has_title(audit_security([f]), "Credential"), titles(audit_security([f]))

    def test_detects_mysql_dsn(self):
        f = py_file(self.MY_DSN)
        findings = audit_security([f])
        assert has_title(findings, "Connection") or has_title(findings, "Password") or has_title(findings, "Credential"), titles(findings)

    def test_evidence_masks_password(self):
        f = py_file(self.PG_DSN)
        findings = audit_security([f])
        for finding in findings:
            assert "sup3rS3cr3t" not in finding.evidence

    def test_severity_is_critical(self):
        f = py_file(self.PG_DSN)
        findings = audit_security([f])
        cred_findings = [x for x in findings if any(
            kw in x.title for kw in ("Connection", "Password", "Credential", "DSN")
        )]
        if cred_findings:
            assert cred_findings[0].severity == "critical"


# ===========================================================================
# DEBUG=True (HIGH, 0.90)
# ===========================================================================

class TestDebugTrue:
    DJANGO = "DEBUG = True"
    FLASK  = "app.debug = True"
    SAFE   = "DEBUG = False"
    ENV    = "DEBUG = os.getenv('DEBUG', 'False') == 'True'"

    def test_detects_debug_true(self):
        f = py_file(self.DJANGO)
        assert has_title(audit_security([f]), "DEBUG"), titles(audit_security([f]))

    def test_flask_debug_true(self):
        f = py_file(self.FLASK)
        findings = audit_security([f])
        assert has_title(findings, "DEBUG") or has_title(findings, "debug"), titles(findings)

    def test_severity_is_high(self):
        f = py_file(self.DJANGO)
        findings = [x for x in audit_security([f]) if "DEBUG" in x.title.upper() or "debug" in x.title]
        assert findings, "No DEBUG finding"
        assert findings[0].severity == "high"

    def test_confidence_at_least_0_85(self):
        f = py_file(self.DJANGO)
        findings = [x for x in audit_security([f]) if "DEBUG" in x.title.upper()]
        assert findings[0].confidence >= 0.85

    def test_debug_false_not_flagged(self):
        f = py_file(self.SAFE)
        findings = [x for x in audit_security([f]) if "DEBUG" in x.title.upper()]
        assert not findings, f"DEBUG=False should not be flagged, got: {titles(findings)}"

    def test_skipped_in_test_file(self):
        f = py_file(self.DJANGO, path="tests/test_settings.py")
        findings = [x for x in audit_security([f]) if "DEBUG" in x.title.upper()]
        assert not findings


# ===========================================================================
# CORS "*" (HIGH, 0.85)
# ===========================================================================

class TestCorsWildcard:
    FLASK_CORS  = 'CORS(app, origins="*")'
    FASTAPI     = 'allow_origins=["*"]'
    DJANGO_CORS = 'CORS_ALLOW_ALL_ORIGINS = True'
    HEADER      = 'response.headers["Access-Control-Allow-Origin"] = "*"'
    SAFE        = 'CORS(app, origins=["https://example.com"])'

    def test_detects_cors_wildcard(self):
        f = py_file(self.FLASK_CORS)
        assert has_title(audit_security([f]), "CORS"), titles(audit_security([f]))

    def test_detects_fastapi_allow_origins(self):
        f = py_file(self.FASTAPI)
        assert has_title(audit_security([f]), "CORS"), titles(audit_security([f]))

    def test_detects_cors_all_origins_true(self):
        f = py_file(self.DJANGO_CORS)
        assert has_title(audit_security([f]), "CORS"), titles(audit_security([f]))

    def test_detects_header_wildcard(self):
        f = py_file(self.HEADER)
        assert has_title(audit_security([f]), "CORS"), titles(audit_security([f]))

    def test_severity_is_high(self):
        f = py_file(self.FLASK_CORS)
        findings = [x for x in audit_security([f]) if "CORS" in x.title]
        assert findings[0].severity == "high"

    def test_specific_origin_not_flagged(self):
        f = py_file(self.SAFE)
        findings = [x for x in audit_security([f]) if "CORS" in x.title]
        assert not findings, f"Specific origin should be safe, got: {titles(findings)}"


# ===========================================================================
# verify=False (HIGH, 0.90)
# ===========================================================================

class TestVerifyFalse:
    REQUESTS  = "resp = requests.get(url, verify=False)"
    HTTPX     = "client = httpx.Client(verify=False)"
    SAFE      = "resp = requests.get(url, verify=True)"
    SAFE2     = "resp = requests.get(url, verify='/etc/ssl/certs/ca.crt')"

    def test_detects_verify_false(self):
        f = py_file(self.REQUESTS)
        assert has_title(audit_security([f]), "verify"), titles(audit_security([f]))

    def test_detects_httpx_verify_false(self):
        f = py_file(self.HTTPX)
        assert has_title(audit_security([f]), "verify"), titles(audit_security([f]))

    def test_severity_is_high(self):
        f = py_file(self.REQUESTS)
        findings = [x for x in audit_security([f]) if "verify" in x.title.lower()]
        assert findings[0].severity == "high"

    def test_verify_true_not_flagged(self):
        f = py_file(self.SAFE)
        findings = [x for x in audit_security([f]) if "verify" in x.title.lower()]
        assert not findings

    def test_verify_cert_path_not_flagged(self):
        f = py_file(self.SAFE2)
        findings = [x for x in audit_security([f]) if "verify" in x.title.lower()]
        assert not findings

    def test_skipped_in_test_file(self):
        f = py_file(self.REQUESTS, path="tests/test_client.py")
        findings = [x for x in audit_security([f]) if "verify" in x.title.lower()]
        assert not findings


# ===========================================================================
# MD5/SHA1 for passwords (MEDIUM, 0.75)
# ===========================================================================

class TestWeakHash:
    PY_MD5    = "hashed = hashlib.md5(password.encode()).hexdigest()"
    PY_SHA1   = "digest = hashlib.sha1(user_pass).hexdigest()"
    JS_MD5    = "const hash = md5(password);"
    SAFE_SHA256 = "hashed = hashlib.sha256(password.encode()).hexdigest()"
    CHECKSUM  = "file_md5 = hashlib.md5(open(path,'rb').read()).hexdigest()"  # MD5 for file integrity — lower concern

    def test_detects_md5_password(self):
        f = py_file(self.PY_MD5)
        findings = audit_security([f])
        assert has_title(findings, "hash") or has_title(findings, "MD5"), titles(findings)

    def test_detects_sha1_password(self):
        f = py_file(self.PY_SHA1)
        findings = audit_security([f])
        assert has_title(findings, "hash") or has_title(findings, "SHA"), titles(findings)

    def test_severity_is_medium(self):
        f = py_file(self.PY_MD5)
        findings = [x for x in audit_security([f])
                    if any(kw in x.title.upper() for kw in ("HASH", "MD5", "SHA1"))]
        if findings:
            assert findings[0].severity == "medium"

    def test_sha256_not_flagged(self):
        f = py_file(self.SAFE_SHA256)
        findings = [x for x in audit_security([f])
                    if any(kw in x.title.upper() for kw in ("HASH", "MD5", "SHA1"))]
        assert not findings, f"SHA-256 should be safe, got: {titles(findings)}"


# ===========================================================================
# 0.0.0.0 bind (MEDIUM, 0.70)
# ===========================================================================

class TestBind0000:
    FLASK  = 'app.run(host="0.0.0.0", port=5000)'
    UVICORN = "uvicorn.run(app, host='0.0.0.0', port=8000)"
    COMMENT = "# host = '0.0.0.0'  # dev only"
    SAFE   = 'app.run(host="127.0.0.1", port=5000)'
    DOCKER = "EXPOSE 0.0.0.0:8080:80"  # Dockerfile — still worth noting

    def test_detects_flask_bind(self):
        f = py_file(self.FLASK)
        assert has_title(audit_security([f]), "0.0.0.0"), titles(audit_security([f]))

    def test_detects_uvicorn_bind(self):
        f = py_file(self.UVICORN)
        assert has_title(audit_security([f]), "0.0.0.0"), titles(audit_security([f]))

    def test_severity_is_medium(self):
        f = py_file(self.FLASK)
        findings = [x for x in audit_security([f]) if "0.0.0.0" in x.title]
        assert findings[0].severity == "medium"

    def test_confidence_is_0_70(self):
        f = py_file(self.FLASK)
        findings = [x for x in audit_security([f]) if "0.0.0.0" in x.title]
        assert abs(findings[0].confidence - 0.70) < 0.05

    def test_localhost_not_flagged(self):
        f = py_file(self.SAFE)
        findings = [x for x in audit_security([f]) if "0.0.0.0" in x.title]
        assert not findings


# ===========================================================================
# Skipping rules (lockfile, test file, placeholder)
# ===========================================================================

class TestSkippingRules:
    SECRET = 'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"'

    def test_no_findings_from_lockfile(self):
        f = IndexedFile(path="package-lock.json", is_source=True,
                        language="json", content=self.SECRET)
        assert audit_security([f]) == []

    def test_no_findings_from_test_file(self):
        f = py_file(self.SECRET, path="tests/test_auth.py")
        assert audit_security([f]) == []

    def test_empty_file_no_crash(self):
        f = py_file("", path="empty.py")
        assert audit_security([f]) == []

    def test_multiple_issues_in_one_file(self):
        content = "\n".join([
            'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"',
            "DEBUG = True",
            'app.run(host="0.0.0.0")',
        ])
        f = py_file(content)
        findings = audit_security([f])
        assert len(findings) >= 3

    def test_all_findings_have_valid_model(self):
        content = "\n".join([
            'secret_key = "sk-realDeadBeefFeed1234567890abcdef12345678"',
            "DEBUG = True",
        ])
        f = py_file(content)
        for finding in audit_security([f]):
            assert 0.0 <= finding.confidence <= 1.0
            assert finding.severity in ("critical", "high", "medium", "low", "info")
            assert finding.category == "security"
            assert finding.file == "app.py"


# ===========================================================================
# audit_security returns Finding list (integration)
# ===========================================================================

class TestAuditSecurityIntegration:
    def test_returns_list(self):
        f = py_file("x = 1")
        result = audit_security([f])
        assert isinstance(result, list)

    def test_empty_source_list(self):
        assert audit_security([]) == []

    def test_findings_sorted_by_line(self):
        content = "\n".join([
            "x = 1",
            'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"',
            "y = 2",
            "DEBUG = True",
        ])
        f = py_file(content)
        findings = audit_security([f])
        # Lines should be monotonically non-decreasing (findings in file order before triage)
        lines = [x.line for x in findings if x.line is not None]
        assert lines == sorted(lines)

    def test_finding_ids_unique(self):
        content = "\n".join([
            'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"',
            "DEBUG = True",
            'app.run(host="0.0.0.0")',
        ])
        f = py_file(content)
        findings = audit_security([f])
        ids = [x.id for x in findings]
        assert len(ids) == len(set(ids)), "Duplicate finding IDs"
