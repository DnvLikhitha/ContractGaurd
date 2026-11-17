"""Security auditor: detects secrets, insecure defaults, and dangerous patterns."""

import ast
import re
from pathlib import Path
from typing import Optional

from contractguard.models import Finding, Category, Severity, IndexedFile


# Secret patterns (regex)
SECRET_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key|apikey)\s*[=:]\s*['\"][a-zA-Z0-9_-]{20,}['\"]"), "API Key"),
    (re.compile(r"(?i)(secret[_-]?key|secretkey)\s*[=:]\s*['\"][a-zA-Z0-9_-]{20,}['\"]"), "Secret Key"),
    (re.compile(r"(?i)(access[_-]?token|accesstoken)\s*[=:]\s*['\"][a-zA-Z0-9_-]{20,}['\"]"), "Access Token"),
    (re.compile(r"(?i)(auth[_-]?token|authtoken)\s*[=:]\s*['\"][a-zA-Z0-9_-]{20,}['\"]"), "Auth Token"),
    (re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*['\"][^'\"]{8,}['\"]"), "Password"),
    (re.compile(r"(?i)(private[_-]?key|privatekey)\s*[=:]\s*['\"][^'\"]{20,}['\"]"), "Private Key"),
    (re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"), "Private Key Block"),
    (re.compile(r"(?i)aws[_-]?access[_-]?key[_-]?id\s*[=:]\s*['\"][A-Z0-9]{20}['\"]"), "AWS Access Key ID"),
    (re.compile(r"(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*['\"][a-zA-Z0-9/+=]{40}['\"]"), "AWS Secret Access Key"),
    (re.compile(r"(?i)github[_-]?token\s*[=:]\s*['\"][a-zA-Z0-9_]{35,}['\"]"), "GitHub Token"),
    (re.compile(r"(?i)slack[_-]?token\s*[=:]\s*['\"][a-zA-Z0-9-]{20,}['\"]"), "Slack Token"),
    (re.compile(r"(?i)stripe[_-]?key\s*[=:]\s*['\"][a-zA-Z0-9]{20,}['\"]"), "Stripe Key"),
    # Generic high-entropy strings (potential secrets)
    (re.compile(r"['\"][a-zA-Z0-9+/]{40,}={0,2}['\"]"), "High-entropy string (possible secret)"),
]

# Insecure default patterns
INSECURE_PATTERNS = [
    # Python
    (re.compile(r"(?i)DEBUG\s*=\s*True"), "DEBUG=True in production", Severity.HIGH, 0.9),
    (re.compile(r"(?i)verify\s*=\s*False"), "SSL verify=False", Severity.HIGH, 0.95),
    (re.compile(r"(?i)check_hostname\s*=\s*False"), "SSL check_hostname=False", Severity.HIGH, 0.9),
    (re.compile(r"(?i)ssl_verify\s*=\s*False"), "SSL verify disabled", Severity.HIGH, 0.9),
    (re.compile(r"0\.0\.0\.0"), "Binding to 0.0.0.0 (all interfaces)", Severity.MEDIUM, 0.7),
    (re.compile(r"(?i)cors.*\*"), "CORS allows all origins (*)", Severity.HIGH, 0.8),
    (re.compile(r"(?i)allow_origin\s*[=:]\s*['\"]\*['\"]"), "CORS allow_origin=*", Severity.HIGH, 0.85),
    (re.compile(r"md5|sha1", re.IGNORECASE), "Weak hash algorithm (MD5/SHA1)", Severity.MEDIUM, 0.6),
    (re.compile(r"(?i)pickle\.loads?\s*\("), "Unsafe pickle deserialization", Severity.CRITICAL, 0.85),
    (re.compile(r"(?i)yaml\.load\s*\((?!.*Loader=)"), "Unsafe YAML load (no SafeLoader)", Severity.HIGH, 0.8),
    (re.compile(r"(?i)eval\s*\("), "Use of eval()", Severity.HIGH, 0.7),
    (re.compile(r"(?i)exec\s*\("), "Use of exec()", Severity.HIGH, 0.7),
    (re.compile(r"(?i)subprocess\.run\s*\(.*shell\s*=\s*True"), "subprocess with shell=True", Severity.HIGH, 0.75),
    (re.compile(r"(?i)os\.system\s*\("), "Use of os.system()", Severity.HIGH, 0.75),
    (re.compile(r"(?i)sql.*%.*s"), "Potential SQL injection (string formatting)", Severity.HIGH, 0.6),
    (re.compile(r"(?i)cursor\.execute\s*\(.*%"), "Potential SQL injection (cursor.execute)", Severity.HIGH, 0.65),

    # JavaScript/TypeScript
    (re.compile(r"(?i)process\.env\.NODE_ENV\s*!==\s*['\"]production['\"]"), "Debug mode check", Severity.MEDIUM, 0.6),
    (re.compile(r"(?i)console\.log"), "Console.log in production code", Severity.LOW, 0.4),
    (re.compile(r"eval\s*\("), "Use of eval()", Severity.HIGH, 0.8),
    (re.compile(r"Function\s*\("), "Use of Function constructor", Severity.HIGH, 0.75),
    (re.compile(r"innerHTML\s*="), "innerHTML assignment (XSS risk)", Severity.MEDIUM, 0.6),
    (re.compile(r"dangerouslySetInnerHTML"), "React dangerouslySetInnerHTML", Severity.MEDIUM, 0.7),

    # Generic
    (re.compile(r"(?i)TODO.*secret|FIXME.*secret|XXX.*secret"), "Secret in TODO/FIXME comment", Severity.MEDIUM, 0.5),
]


def mask_secrets(text: str) -> str:
    """Mask potential secrets in evidence text."""
    # Mask API keys, tokens, passwords
    text = re.sub(r"(?i)(api[_-]?key|secret|token|password|key)\s*[=:]\s*['\"][^'\"]+['\"]", r"\1=***MASKED***", text)
    text = re.sub(r"['\"][a-zA-Z0-9+/]{32,}={0,2}['\"]", "'***MASKED***'", text)
    text = re.sub(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----.*?-----END (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "***PRIVATE KEY***", text, flags=re.DOTALL)
    return text


def check_secrets(file: IndexedFile, findings: list[Finding], finding_id_counter: list[int]) -> None:
    """Check for hardcoded secrets in a file."""
    content = file.content
    lines = content.splitlines()

    for pattern, secret_type in SECRET_PATTERNS:
        for match in pattern.finditer(content):
            # Find line number
            line_no = content[:match.start()].count('\n') + 1
            evidence = lines[line_no - 1].strip() if line_no <= len(lines) else match.group()
            evidence = mask_secrets(evidence)

            finding_id_counter[0] += 1
            findings.append(Finding(
                id=f"SEC-{finding_id_counter[0]:04d}",
                category=Category.SECURITY,
                severity=Severity.CRITICAL,
                confidence=0.85,
                file=file.path,
                line=line_no,
                title=f"Hardcoded {secret_type}",
                evidence=evidence,
                suggested_fix=f"Move {secret_type.lower()} to environment variable or secret manager",
            ))


def check_insecure_defaults(file: IndexedFile, findings: list[Finding], finding_id_counter: list[int]) -> None:
    """Check for insecure default configurations."""
    content = file.content
    lines = content.splitlines()

    for pattern, title, severity, confidence in INSECURE_PATTERNS:
        for match in pattern.finditer(content):
            line_no = content[:match.start()].count('\n') + 1
            evidence = lines[line_no - 1].strip() if line_no <= len(lines) else match.group()
            evidence = mask_secrets(evidence)

            # Skip if it's in a test file or comment-only line
            if is_test_file(file.path) or is_comment_only(evidence, file.language):
                continue

            finding_id_counter[0] += 1
            findings.append(Finding(
                id=f"SEC-{finding_id_counter[0]:04d}",
                category=Category.SECURITY,
                severity=severity,
                confidence=confidence,
                file=file.path,
                line=line_no,
                title=title,
                evidence=evidence,
                suggested_fix=get_security_fix_suggestion(title, file.language),
            ))


def check_python_ast(file: IndexedFile, findings: list[Finding], finding_id_counter: list[int]) -> None:
    """AST-based checks for Python files."""
    if file.language != "python":
        return

    try:
        tree = ast.parse(file.content)
    except SyntaxError:
        return

    for node in ast.walk(tree):
        # Check for pickle usage
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in ("loads", "load") and isinstance(node.func.value, ast.Name):
                    if node.func.value.id == "pickle":
                        finding_id_counter[0] += 1
                        findings.append(Finding(
                            id=f"SEC-{finding_id_counter[0]:04d}",
                            category=Category.SECURITY,
                            severity=Severity.CRITICAL,
                            confidence=0.9,
                            file=file.path,
                            line=node.lineno,
                            title="Unsafe pickle deserialization",
                            evidence=mask_secrets(ast.get_source_segment(file.content, node) or ""),
                            suggested_fix="Use json or a safe serialization format instead of pickle",
                        ))

            # Check for yaml.load without SafeLoader
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "load" and isinstance(node.func.value, ast.Name):
                    if node.func.value.id == "yaml":
                        # Check if SafeLoader is used
                        has_safe_loader = any(
                            kw.arg == "Loader" and isinstance(kw.value, ast.Name) and kw.value.id == "SafeLoader"
                            for kw in node.keywords
                        )
                        if not has_safe_loader:
                            finding_id_counter[0] += 1
                            findings.append(Finding(
                                id=f"SEC-{finding_id_counter[0]:04d}",
                                category=Category.SECURITY,
                                severity=Severity.HIGH,
                                confidence=0.8,
                                file=file.path,
                                line=node.lineno,
                                title="Unsafe YAML load (no SafeLoader)",
                                evidence=mask_secrets(ast.get_source_segment(file.content, node) or ""),
                                suggested_fix="Use yaml.safe_load() or yaml.load(..., Loader=yaml.SafeLoader)",
                            ))

        # Check for eval/exec calls
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("eval", "exec"):
                finding_id_counter[0] += 1
                findings.append(Finding(
                    id=f"SEC-{finding_id_counter[0]:04d}",
                    category=Category.SECURITY,
                    severity=Severity.HIGH,
                    confidence=0.85,
                    file=file.path,
                    line=node.lineno,
                    title=f"Use of {node.func.id}()",
                    evidence=mask_secrets(ast.get_source_segment(file.content, node) or ""),
                    suggested_fix=f"Avoid {node.func.id}(); use safer alternatives",
                ))


def is_test_file(filepath: str) -> bool:
    """Check if a file is a test file."""
    name = Path(filepath).name
    return (
        name.startswith("test_") or
        name.endswith("_test.py") or
        name.endswith(".test.js") or
        name.endswith(".test.ts") or
        name.endswith(".spec.js") or
        name.endswith(".spec.ts") or
        "test" in Path(filepath).parts or
        "spec" in Path(filepath).parts
    )


def is_comment_only(line: str, language: Optional[str]) -> bool:
    """Check if a line is only a comment."""
    stripped = line.strip()
    if not stripped:
        return True

    if language == "python":
        return stripped.startswith("#")
    elif language in ("javascript", "typescript", "go", "rust", "java", "csharp", "cpp", "c"):
        return stripped.startswith("//") or stripped.startswith("/*")
    elif language in ("ruby", "perl", "bash", "powershell"):
        return stripped.startswith("#")
    elif language in ("html", "xml"):
        return stripped.startswith("<!--")
    return False


def get_security_fix_suggestion(title: str, language: Optional[str]) -> str:
    """Get a suggested fix for a security issue."""
    fixes = {
        "DEBUG=True in production": "Set DEBUG=False in production; use environment variable",
        "SSL verify=False": "Enable SSL verification; use proper certificates",
        "SSL check_hostname=False": "Enable hostname verification",
        "SSL verify disabled": "Enable SSL verification",
        "Binding to 0.0.0.0 (all interfaces)": "Bind to specific interface (e.g., 127.0.0.1) or use env var",
        "CORS allows all origins (*)": "Restrict CORS to specific trusted origins",
        "CORS allow_origin=*": "Set allow_origin to specific domains",
        "Weak hash algorithm (MD5/SHA1)": "Use SHA-256 or stronger (bcrypt/scrypt/argon2 for passwords)",
        "Unsafe pickle deserialization": "Use json or a safe serialization format",
        "Unsafe YAML load (no SafeLoader)": "Use yaml.safe_load() or yaml.load(..., Loader=yaml.SafeLoader)",
        "Use of eval()": "Avoid eval(); use ast.literal_eval() or safer alternatives",
        "Use of exec()": "Avoid exec(); refactor to use safer patterns",
        "subprocess with shell=True": "Use shell=False and pass args as list",
        "Use of os.system()": "Use subprocess.run() with shell=False",
        "Potential SQL injection (string formatting)": "Use parameterized queries",
        "Potential SQL injection (cursor.execute)": "Use parameterized queries with placeholders",
        "Debug mode check": "Remove or guard debug code",
        "Console.log in production code": "Remove console.log or use proper logging",
        "Use of eval()": "Avoid eval(); use JSON.parse() or safer alternatives",
        "Use of Function constructor": "Avoid Function constructor; use safer patterns",
        "innerHTML assignment (XSS risk)": "Use textContent or safe DOM APIs",
        "React dangerouslySetInnerHTML": "Sanitize content before using dangerouslySetInnerHTML",
        "Secret in TODO/FIXME comment": "Remove secret from comment; use proper secret management",
    }
    return fixes.get(title, "Review and fix the security issue")


def audit_security(source_files: list[IndexedFile]) -> list[Finding]:
    """Main entry point for security auditor."""
    findings = []
    finding_id_counter = [0]

    for file in source_files:
        check_secrets(file, findings, finding_id_counter)
        check_insecure_defaults(file, findings, finding_id_counter)
        check_python_ast(file, findings, finding_id_counter)

    return findings