"""Drift auditor: detects env-contract drift and README-to-code drift.

Rules:
  DRF-001  Env var used in code but absent from every contract file  → HIGH 0.85
  DRF-002  Env var declared in contract file but never used in code   → LOW  0.70

Contract files consulted: .env.example, docker-compose environment blocks.

Language support
  Python  : os.getenv("VAR"), os.environ["VAR"], os.environ.get("VAR")
  JS/TS   : process.env.VAR, process.env['VAR'], import.meta.env.VAR

The module is deterministic and requires no external tools or API keys.
"""

import ast
import re
from typing import Optional

import yaml

from contractguard.models import Category, ContractFiles, Finding, IndexedFile, Severity

# ---------------------------------------------------------------------------
# Regex patterns for JS/TS env-var extraction
# ---------------------------------------------------------------------------

# process.env.VAR  or  process.env['VAR']  or  process.env["VAR"]
_JS_PROCESS_ENV = re.compile(
    r"""process\.env\.([A-Z][A-Z0-9_]*)"""
    r"""|process\.env\[['"]([A-Z][A-Z0-9_]*)['"]\]""",
    re.VERBOSE,
)

# import.meta.env.VAR  or  import.meta.env['VAR']  or  import.meta.env["VAR"]
_JS_META_ENV = re.compile(
    r"""import\.meta\.env\.([A-Z][A-Z0-9_]*)"""
    r"""|import\.meta\.env\[['"]([A-Z][A-Z0-9_]*)['"]\]""",
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Python extraction — AST-based for accuracy, regex fallback
# ---------------------------------------------------------------------------

# Simple regex for Python reads (used only when AST parse fails)
_PY_GETENV = re.compile(
    r"""os\.(?:getenv|environ\.get)\(\s*['"]([A-Z][A-Z0-9_]*)['"]""",
)
_PY_ENVIRON_SUB = re.compile(
    r"""os\.environ\[\s*['"]([A-Z][A-Z0-9_]*)['"]\s*\]""",
)


def _extract_py_reads_via_ast(source: str) -> tuple[bool, set[str]]:
    """Walk the AST and find all *read* accesses to os.getenv / os.environ.

    Returns:
        (parse_ok, vars_found) — parse_ok is False only on SyntaxError.
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
            if isinstance(func, ast.Attribute):
                if func.attr in ("getenv", "get"):
                    # make sure the first arg is a string literal
                    if node.args and isinstance(node.args[0], ast.Constant):
                        name = node.args[0].value
                        if isinstance(name, str) and name.isupper():
                            vars_found.add(name)
                        elif isinstance(name, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
                            vars_found.add(name)
            self.generic_visit(node)

        def visit_Subscript(self, node: ast.Subscript) -> None:
            # os.environ["VAR"]  — only reads (not assignments)
            # An assignment like os.environ["X"] = val appears as a Store context
            if isinstance(node.ctx, ast.Load):
                val = node.value
                if (
                    isinstance(val, ast.Attribute)
                    and val.attr == "environ"
                    and isinstance(val.value, ast.Name)
                    and val.value.id == "os"
                ):
                    slice_node = node.slice
                    # Python 3.9+ uses the constant directly
                    if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
                        name = slice_node.value
                        if re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
                            vars_found.add(name)
            self.generic_visit(node)

    _Visitor().visit(tree)
    return vars_found


def extract_env_vars_from_python(content: str) -> set[str]:
    """Extract environment variable names from Python source code.

    Uses AST parsing for precise read-only detection; falls back to regex on
    parse errors (e.g. Python 2 syntax).

    Extraction targets:
      - os.getenv("VAR")
      - os.environ.get("VAR")
      - os.environ["VAR"]   (read access only — assignments are excluded)
    """
    result = _extract_py_reads_via_ast(content)
    if not result:
        # Fallback: simple regex (less precise but handles parse failures)
        for m in _PY_GETENV.finditer(content):
            # Exclude lines that start with # (comments)
            line_start = content.rfind("\n", 0, m.start()) + 1
            line = content[line_start : content.find("\n", m.start())]
            if not line.lstrip().startswith("#"):
                result.add(m.group(1))
        for m in _PY_ENVIRON_SUB.finditer(content):
            line_start = content.rfind("\n", 0, m.start()) + 1
            line = content[line_start : content.find("\n", m.start())]
            if not line.lstrip().startswith("#"):
                result.add(m.group(1))
    else:
        # AST succeeded; still run a cheap comment-line filter isn't needed
        # because AST naturally excludes comments
        pass
    return result


def extract_env_vars_from_js(content: str) -> set[str]:
    """Extract environment variable names from JavaScript/TypeScript source code.

    Extraction targets:
      - process.env.VAR
      - process.env['VAR'] / process.env["VAR"]
      - import.meta.env.VAR
      - import.meta.env['VAR'] / import.meta.env["VAR"]
    """
    result: set[str] = set()
    for m in _JS_PROCESS_ENV.finditer(content):
        name = m.group(1) or m.group(2)
        if name:
            result.add(name)
    for m in _JS_META_ENV.finditer(content):
        name = m.group(1) or m.group(2)
        if name:
            result.add(name)
    return result


def extract_env_vars_from_file(file: IndexedFile) -> set[str]:
    """Extract environment variables from a source file based on its language."""
    if file.language == "python":
        return extract_env_vars_from_python(file.content)
    if file.language in ("javascript", "typescript"):
        return extract_env_vars_from_js(file.content)
    # Other languages are not yet supported
    return set()


# ---------------------------------------------------------------------------
# Contract file parsers
# ---------------------------------------------------------------------------

# .env.example line: optional `export `, then KEY=...  (strip inline comments)
_ENV_LINE = re.compile(
    r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=",
)


def parse_env_example(content: str) -> set[str]:
    """Parse variable names from a .env / .env.example file.

    Rules:
      - Lines starting with # are comments and are skipped.
      - Blank lines are skipped.
      - `export KEY=value` prefix is handled.
      - Inline comments after the value are ignored (we only extract the key).
    """
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
    """Parse environment variables from a docker-compose YAML file.

    Supports both list style (- KEY=value) and map style (KEY: value) for the
    `environment` block under each service.  Multi-service files are handled.
    """
    if not content.strip():
        return set()

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError:
        return set()

    if not isinstance(data, dict):
        return set()

    result: set[str] = set()
    services = data.get("services", {}) or {}
    if not isinstance(services, dict):
        return result

    for service_cfg in services.values():
        if not isinstance(service_cfg, dict):
            continue
        env_block = service_cfg.get("environment")
        if env_block is None:
            continue

        if isinstance(env_block, list):
            # List style: "KEY=value" or just "KEY"
            for item in env_block:
                if isinstance(item, str):
                    key = item.split("=", 1)[0].strip()
                    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                        result.add(key)
        elif isinstance(env_block, dict):
            # Map style: KEY: value
            for key in env_block:
                if isinstance(key, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                    result.add(key)

    return result


# ---------------------------------------------------------------------------
# Drift detection logic
# ---------------------------------------------------------------------------

# Counter for unique finding IDs within a session
_finding_counter = 0


def _new_id() -> str:
    global _finding_counter
    _finding_counter += 1
    return f"DRF-{_finding_counter:03d}"


def _collect_documented_vars(contract_files: ContractFiles) -> set[str]:
    """Collect all env-var names from every contract file."""
    documented: set[str] = set()

    if contract_files.env_example:
        documented |= parse_env_example(contract_files.env_example.content)

    for dc_file in contract_files.docker_compose:
        documented |= parse_docker_compose_env(dc_file.content)

    return documented


def _collect_code_vars(source_files: list[IndexedFile]) -> set[str]:
    """Collect all env-var names read from source files."""
    used: set[str] = set()
    for f in source_files:
        used |= extract_env_vars_from_file(f)
    return used


def check_env_drift(
    source_files: list[IndexedFile],
    contract_files: ContractFiles,
) -> list[Finding]:
    """Check for environment variable drift between code and contract files.

    Returns:
      DRF-xxx  HIGH 0.85  — var used in code but NOT in any contract file
      DRF-xxx  LOW  0.70  — var in a contract file but NOT used in code
    """
    # If there are no contract files to compare against, we can't judge drift
    has_contract = (
        contract_files.env_example is not None
        or len(contract_files.docker_compose) > 0
    )
    if not has_contract:
        return []

    documented = _collect_documented_vars(contract_files)
    used_in_code = _collect_code_vars(source_files)

    findings: list[Finding] = []

    # Vars used in code but not documented anywhere
    for var in sorted(used_in_code - documented):
        findings.append(
            Finding(
                id=_new_id(),
                category=Category.DRIFT,
                severity=Severity.HIGH,
                confidence=0.85,
                file=".env.example",
                line=None,
                title=f"Env var {var!r} used in code but absent from contract files",
                evidence=f"{var} is referenced in source code but not declared in .env.example or docker-compose",
                suggested_fix=f"Add `{var}=<description>` to your .env.example file",
            )
        )

    # Vars documented but never used in code
    for var in sorted(documented - used_in_code):
        findings.append(
            Finding(
                id=_new_id(),
                category=Category.DRIFT,
                severity=Severity.LOW,
                confidence=0.70,
                file=".env.example",
                line=None,
                title=f"Env var {var!r} declared in contract but not used in code",
                evidence=f"{var} appears in .env.example or docker-compose but no code reads it",
                suggested_fix=f"Remove `{var}` from .env.example if it is no longer needed",
            )
        )

    return findings


def check_readme_drift(
    source_files: list[IndexedFile],
    contract_files: ContractFiles,
) -> list[Finding]:
    """Check for README-to-code drift (documented endpoints/commands missing in code).

    P1 feature — deferred to a future phase.  Returns an empty list for now.
    """
    # TODO: Extract HTTP endpoints from README (e.g. `GET /health`)
    # and verify they appear in source code.  Deferred to Phase 5+.
    return []


def audit_drift(
    source_files: list[IndexedFile],
    contract_files: ContractFiles,
) -> list[Finding]:
    """Main entry point for the drift auditor."""
    findings: list[Finding] = []
    findings.extend(check_env_drift(source_files, contract_files))
    findings.extend(check_readme_drift(source_files, contract_files))
    return findings
