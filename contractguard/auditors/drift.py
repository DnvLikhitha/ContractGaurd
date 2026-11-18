"""Drift auditor: detects env-contract drift and README-to-code drift.

Rules:
  DRF-001  Env var used in code but absent from contract files (env/compose) -> HIGH 0.85
  DRF-002  Env var declared in contract file but never used in code          -> LOW  0.70
  DRF-003  Documented endpoint in README not found in code                  -> MEDIUM 0.80
  DRF-004  Documented CLI command in README not found in code               -> MEDIUM 0.75

Deterministic, offline, and requires no external API keys.
"""

from __future__ import annotations

import ast
import re
from typing import Any

import yaml

from contractguard.models import Category, ContractFiles, Finding, IndexedFile, Severity

# ---------------------------------------------------------------------------
# Common development tools to ignore when parsing README CLI commands
# ---------------------------------------------------------------------------
COMMON_DEV_TOOLS = {
    "git", "pip", "npm", "pnpm", "yarn", "pytest", "cd", "ls", "mkdir",
    "rm", "cp", "mv", "docker", "docker-compose", "make", "curl", "source",
    "export", "chmod", "cat", "echo", "python", "python3", "node", "npx",
    "venv", "virtualenv", "touch", "grep", "find", "sed", "awk", "ruff",
    "black", "flake8", "mypy", "poetry", "pipenv", "cargo", "go",
}

# ---------------------------------------------------------------------------
# Regex patterns for env-var extraction
# ---------------------------------------------------------------------------

# JS/TS: process.env.VAR or process.env['VAR'] or process.env["VAR"]
_JS_PROCESS_ENV = re.compile(
    r"""process\.env\.([A-Z][A-Z0-9_]*)"""
    r"""|process\.env\[['"]([A-Z][A-Z0-9_]*)['"]\]""",
)

# JS/TS: import.meta.env.VAR or import.meta.env['VAR'] or import.meta.env["VAR"]
_JS_META_ENV = re.compile(
    r"""import\.meta\.env\.([A-Z][A-Z0-9_]*)"""
    r"""|import\.meta\.env\[['"]([A-Z][A-Z0-9_]*)['"]\]""",
)

# Go: os.Getenv("VAR") or os.LookupEnv("VAR")
_GO_ENV = re.compile(
    r"""os\.(?:Getenv|LookupEnv)\(\s*["']([A-Z][A-Z0-9_]*)["']\s*\)"""
)

# Generic regex fallback for Python when AST parsing fails
_PY_GETENV = re.compile(
    r"""os\.(?:getenv|environ\.get)\(\s*['"]([A-Z][A-Z0-9_]*)['"]""",
)
_PY_ENVIRON_SUB = re.compile(
    r"""os\.environ\[\s*['"]([A-Z][A-Z0-9_]*)['"]\s*\]""",
)


# ---------------------------------------------------------------------------
# Python extraction — AST-based
# ---------------------------------------------------------------------------

def _extract_py_reads_via_ast(source: str) -> tuple[bool, set[str]]:
    """Walk AST and find read accesses to os.getenv / os.environ.

    Returns:
        (success, vars_found): success is False only if a SyntaxError occurred.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False, set()

    vars_found: set[str] = set()

    class _Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            # os.getenv("VAR") or os.environ.get("VAR")
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in ("getenv", "get"):
                if node.args and isinstance(node.args[0], ast.Constant):
                    val = node.args[0].value
                    if isinstance(val, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", val):
                        vars_found.add(val)
            self.generic_visit(node)

        def visit_Subscript(self, node: ast.Subscript) -> None:
            # os.environ["VAR"] — only reads (ast.Load context)
            if isinstance(node.ctx, ast.Load):
                val = node.value
                if (
                    isinstance(val, ast.Attribute)
                    and val.attr == "environ"
                    and isinstance(val.value, ast.Name)
                    and val.value.id == "os"
                ):
                    slice_node = node.slice
                    if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
                        key = slice_node.value
                        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                            vars_found.add(key)
            self.generic_visit(node)

    _Visitor().visit(tree)
    return True, vars_found


def extract_env_vars_from_python(content: str) -> set[str]:
    """Extract environment variable names read in Python source code."""
    parsed, vars_found = _extract_py_reads_via_ast(content)
    if parsed:
        return vars_found

    # Regex fallback on syntax error
    result: set[str] = set()
    for m in _PY_GETENV.finditer(content):
        line_start = content.rfind("\n", 0, m.start()) + 1
        line = content[line_start:content.find("\n", m.start()) if "\n" in content[m.start():] else len(content)]
        if not line.lstrip().startswith("#"):
            result.add(m.group(1))

    for m in _PY_ENVIRON_SUB.finditer(content):
        line_start = content.rfind("\n", 0, m.start()) + 1
        line = content[line_start:content.find("\n", m.start()) if "\n" in content[m.start():] else len(content)]
        if not line.lstrip().startswith("#"):
            # Check if this line is an assignment: os.environ["VAR"] = ...
            after_match = line[line.find(m.group(0)) + len(m.group(0)):].strip()
            if not after_match.startswith("="):
                result.add(m.group(1))

    return result


def extract_env_vars_from_js(content: str) -> set[str]:
    """Extract environment variable names from JavaScript/TypeScript code."""
    result: set[str] = set()
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            continue

        for m in _JS_PROCESS_ENV.finditer(line):
            name = m.group(1) or m.group(2)
            if name:
                result.add(name)

        for m in _JS_META_ENV.finditer(line):
            name = m.group(1) or m.group(2)
            if name:
                result.add(name)

    return result


def extract_env_vars_from_go(content: str) -> set[str]:
    """Extract environment variable names from Go code."""
    result: set[str] = set()
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        for m in _GO_ENV.finditer(line):
            name = m.group(1)
            if name:
                result.add(name)
    return result


def extract_env_vars_from_file(file: IndexedFile) -> set[str]:
    """Extract environment variables from a source file based on language."""
    if file.language == "python":
        return extract_env_vars_from_python(file.content)
    if file.language in ("javascript", "typescript"):
        return extract_env_vars_from_js(file.content)
    if file.language == "go":
        return extract_env_vars_from_go(file.content)

    # Generic fallback
    res = set()
    res |= extract_env_vars_from_python(file.content)
    res |= extract_env_vars_from_js(file.content)
    res |= extract_env_vars_from_go(file.content)
    return res


# ---------------------------------------------------------------------------
# Contract parsing: .env.example and docker-compose.yml
# ---------------------------------------------------------------------------

_ENV_LINE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def parse_env_example(content: str) -> set[str]:
    """Parse variable names from .env.example / .env template."""
    result: set[str] = set()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _ENV_LINE.match(stripped)
        if m:
            result.add(m.group(1))
    return result


def parse_docker_compose_env(content: str) -> set[str]:
    """Parse environment variables declared in docker-compose.yml."""
    if not content.strip():
        return set()

    try:
        data = yaml.safe_load(content)
    except Exception:
        return set()

    if not isinstance(data, dict):
        return set()

    result: set[str] = set()
    services = data.get("services", {})
    if not isinstance(services, dict):
        return result

    for service_cfg in services.values():
        if not isinstance(service_cfg, dict):
            continue
        env_block = service_cfg.get("environment")
        if env_block is None:
            continue

        if isinstance(env_block, list):
            for item in env_block:
                if isinstance(item, str):
                    key = item.split("=", 1)[0].strip()
                    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                        result.add(key)
        elif isinstance(env_block, dict):
            for key in env_block:
                if isinstance(key, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                    result.add(key)

    return result


# ---------------------------------------------------------------------------
# P0: Env drift detection
# ---------------------------------------------------------------------------

_id_seq = 0


def _next_id(prefix: str = "DRF") -> str:
    global _id_seq
    _id_seq += 1
    return f"{prefix}-{_id_seq:03d}"


def check_env_drift(
    source_files: list[IndexedFile],
    contract_files: ContractFiles,
) -> list[Finding]:
    """Check for environment variable drift between source code and contract files."""
    has_contract = (
        contract_files.env_example is not None
        or len(contract_files.docker_compose) > 0
    )
    if not has_contract:
        return []

    # 1. Collect contract vars
    documented_vars: set[str] = set()
    primary_contract_file = ".env.example"

    if contract_files.env_example:
        primary_contract_file = contract_files.env_example.path
        documented_vars |= parse_env_example(contract_files.env_example.content)

    for compose_f in contract_files.docker_compose:
        if not contract_files.env_example:
            primary_contract_file = compose_f.path
        documented_vars |= parse_docker_compose_env(compose_f.content)

    # 2. Collect source vars and track their file references
    used_in_code: set[str] = set()
    var_locations: dict[str, list[str]] = {}

    for f in source_files:
        f_vars = extract_env_vars_from_file(f)
        for var in f_vars:
            used_in_code.add(var)
            var_locations.setdefault(var, []).append(f.path)

    findings: list[Finding] = []

    # 3. Missing in contract (code uses it, contract doesn't have it) -> HIGH
    for var in sorted(used_in_code - documented_vars):
        locs = var_locations.get(var, [])
        evidence_loc = f" in {', '.join(locs)}" if locs else ""
        findings.append(
            Finding(
                id=_next_id("DRF"),
                category=Category.DRIFT,
                severity=Severity.HIGH,
                confidence=0.85,
                file=locs[0] if locs else primary_contract_file,
                line=None,
                title=f"Env var '{var}' used in code but absent from contract files",
                evidence=f"{var} is referenced in source code{evidence_loc} but not declared in .env.example or docker-compose",
                suggested_fix=f"Add '{var}=<description>' to {primary_contract_file}",
            )
        )

    # 4. Unused in code (contract has it, code doesn't use it) -> LOW
    for var in sorted(documented_vars - used_in_code):
        findings.append(
            Finding(
                id=_next_id("DRF"),
                category=Category.DRIFT,
                severity=Severity.LOW,
                confidence=0.70,
                file=primary_contract_file,
                line=None,
                title=f"Env var '{var}' declared in contract but not used in code",
                evidence=f"{var} appears in {primary_contract_file} but no code reads it",
                suggested_fix=f"Remove '{var}' from {primary_contract_file} if it is no longer needed",
            )
        )

    return findings


# ---------------------------------------------------------------------------
# P1: README extraction & drift detection
# ---------------------------------------------------------------------------

_HTTP_METHODS = r"(?:GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)"

# Pattern for endpoints: GET /api/v1/users, `POST /login`, | GET | /status |
_README_ENDPOINT_RE = re.compile(
    r"""(?i)(?:^|[\s`|])(""" + _HTTP_METHODS + r""")\s*[:|]?\s*([/][a-zA-Z0-9_\-\./{}:<>]+)"""
)


def extract_endpoints_from_readme(content: str) -> list[dict[str, str]]:
    """Extract documented HTTP endpoints from README text."""
    endpoints: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for line in content.splitlines():
        # Skip external URLs (e.g., https://example.com/api)
        if "http://" in line or "https://" in line:
            # If the line contains an external url, ignore URL parts
            line = re.sub(r"https?://[^\s`]+", "", line)

        for m in _README_ENDPOINT_RE.finditer(line):
            method = m.group(1).upper()
            raw_path = m.group(2).strip()

            # Clean trailing punctuation
            path = raw_path.rstrip(".,;`|")
            if not path.startswith("/"):
                continue

            key = (method, path)
            if key not in seen:
                seen.add(key)
                endpoints.append({
                    "method": method,
                    "path": path,
                    "raw": f"{method} {path}",
                })

    return endpoints


def extract_commands_from_readme(content: str) -> list[dict[str, str]]:
    """Extract CLI commands and subcommands documented in README."""
    commands: list[dict[str, str]] = []
    seen: set[str] = set()

    in_code_block = False
    code_block_lang = ""

    for line in content.splitlines():
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code_block:
                in_code_block = False
                code_block_lang = ""
            else:
                in_code_block = True
                code_block_lang = stripped[3:].strip().lower()
            continue

        if not in_code_block and not stripped.startswith("$"):
            continue

        # Skip comment lines
        if stripped.startswith("#"):
            continue

        cmd_line = stripped
        if cmd_line.startswith("$ ") or cmd_line.startswith("> "):
            cmd_line = cmd_line[2:].strip()

        # Parse command tokens
        parts = cmd_line.split()
        if not parts:
            continue

        # Case 1: python -m <module> <command>
        if len(parts) >= 4 and parts[0] in ("python", "python3") and parts[1] == "-m":
            subcmd = parts[3].strip()
            if subcmd and not subcmd.startswith("-") and not subcmd.startswith("<"):
                if subcmd not in seen:
                    seen.add(subcmd)
                    commands.append({"command": subcmd, "raw": cmd_line})
            continue

        # Case 2: <app_name> <subcommand>
        first_token = parts[0].lower().lstrip("./")
        if first_token in COMMON_DEV_TOOLS:
            continue

        # If it's a tool invocation like `myapp serve` or `contractguard audit <path>`
        if len(parts) >= 2:
            subcmd = parts[1].strip()
            # If subcmd is not a flag or placeholder
            if subcmd and not subcmd.startswith("-") and not subcmd.startswith("<"):
                if subcmd not in seen:
                    seen.add(subcmd)
                    commands.append({"command": subcmd, "raw": cmd_line})
        elif len(parts) == 1:
            cmd = parts[0].strip()
            if cmd and not cmd.startswith("-") and not cmd.startswith("<"):
                if cmd not in seen:
                    seen.add(cmd)
                    commands.append({"command": cmd, "raw": cmd_line})

    return commands


def check_readme_drift(
    source_files: list[IndexedFile],
    contract_files: ContractFiles,
) -> list[Finding]:
    """Check for README-to-code drift (documented endpoints / CLI commands missing in code)."""
    if not contract_files.readme:
        return []

    readme_content = contract_files.readme.content
    readme_path = contract_files.readme.path

    findings: list[Finding] = []

    # 1. Check endpoints
    endpoints = extract_endpoints_from_readme(readme_content)
    for ep in endpoints:
        path = ep["path"]
        method = ep["method"]

        # Base path without placeholders: /api/v1/users/{id} -> /api/v1/users
        base_path = re.sub(r"/{[^{}]+}|/:[a-zA-Z0-9_]+|/<[^<>]+>", "", path)
        if not base_path:
            base_path = path

        # Check if base_path or full path appears in any source file
        path_found = False
        for sf in source_files:
            if path in sf.content or base_path in sf.content:
                path_found = True
                break

        if not path_found:
            findings.append(
                Finding(
                    id=_next_id("DRF"),
                    category=Category.DRIFT,
                    severity=Severity.MEDIUM,
                    confidence=0.80,
                    file=readme_path,
                    line=None,
                    title=f"Documented endpoint '{method} {path}' not found in code",
                    evidence=f"Endpoint '{method} {path}' is documented in {readme_path} but no matching route or path was found in source files",
                    suggested_fix=f"Implement the '{method} {path}' endpoint or update {readme_path}",
                )
            )

    # 2. Check CLI commands
    commands = extract_commands_from_readme(readme_content)
    for cmd_info in commands:
        cmd = cmd_info["command"]

        # Search for cmd symbol in source files
        # Look for word boundary or function/command definition
        cmd_found = False
        pattern = re.compile(rf"\b{re.escape(cmd)}\b")
        for sf in source_files:
            if pattern.search(sf.content):
                cmd_found = True
                break

        if not cmd_found:
            findings.append(
                Finding(
                    id=_next_id("DRF"),
                    category=Category.DRIFT,
                    severity=Severity.MEDIUM,
                    confidence=0.75,
                    file=readme_path,
                    line=None,
                    title=f"Documented command '{cmd}' not found in code",
                    evidence=f"Command '{cmd}' is documented in {readme_path} but no matching command or symbol was found in source files",
                    suggested_fix=f"Implement command '{cmd}' or remove it from {readme_path}",
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def audit_drift(
    source_files: list[IndexedFile],
    contract_files: ContractFiles,
) -> list[Finding]:
    """Main entry point for drift auditor."""
    findings: list[Finding] = []
    findings.extend(check_env_drift(source_files, contract_files))
    findings.extend(check_readme_drift(source_files, contract_files))
    return findings
