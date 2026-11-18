"""Slop auditor: detects orphaned files and unused dependencies.

Rules:
  SLP-001  Orphaned source file never imported anywhere and not an entry point -> LOW 0.85 (0.60 if dynamic imports)
  SLP-002  Dependency declared in manifest but never imported in source code    -> LOW 0.80 (0.60 if dynamic imports)

Deterministic, offline, and requires no external API keys.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from contractguard.models import Category, ContractFiles, Finding, IndexedFile, Severity

# ---------------------------------------------------------------------------
# Mappings and Whitelists
# ---------------------------------------------------------------------------

COMMON_PYTHON_DEP_MAPPINGS: dict[str, set[str]] = {
    "pyyaml": {"yaml"},
    "scikit-learn": {"sklearn"},
    "pillow": {"PIL"},
    "beautifulsoup4": {"bs4"},
    "python-dateutil": {"dateutil"},
    "pydantic-settings": {"pydantic_settings"},
    "opencv-python": {"cv2"},
    "opencv-python-headless": {"cv2"},
    "protobuf": {"google.protobuf", "google"},
    "pyjwt": {"jwt"},
    "paho-mqtt": {"paho"},
    "psycopg2": {"psycopg2"},
    "psycopg2-binary": {"psycopg2"},
    "mysql-connector-python": {"mysql"},
    "python-dotenv": {"dotenv"},
    "attrs": {"attr", "attrs"},
    "setuptools": {"setuptools", "pkg_resources", "distutils"},
    "types-requests": {"requests"},
}

DEFAULT_ENTRY_POINTS = {
    "main", "__main__", "__init__", "app", "index", "cli", "setup",
    "manage", "wsgi", "asgi", "conftest", "server", "run", "worker",
}

ENTRY_POINT_DIRS = {"tests", "test", "__tests__", "spec", "specs", "scripts", "bin"}


# ---------------------------------------------------------------------------
# Dynamic import detection
# ---------------------------------------------------------------------------

_PY_DYNAMIC_CALLS = re.compile(
    r"""(?:\b__import__\s*\(|\bimportlib\.import_module\s*\()"""
)

_JS_DYNAMIC_REQUIRE = re.compile(
    r"""\brequire\s*\(\s*(?!['"`])"""
)

_JS_DYNAMIC_IMPORT = re.compile(
    r"""\bimport\s*\(\s*(?:`[^`]*\$\{[^}]+\}[^`]*`|(?!['"`]))"""
)


def has_dynamic_imports_python(content: str) -> bool:
    """Check if Python code uses dynamic imports (importlib, __import__)."""
    if _PY_DYNAMIC_CALLS.search(content):
        return True
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "__import__":
                    return True
                if isinstance(func, ast.Attribute) and func.attr == "import_module":
                    return True
    except SyntaxError:
        pass
    return False


def has_dynamic_imports_js(content: str) -> bool:
    """Check if JS/TS code uses dynamic imports or variable require calls."""
    return bool(_JS_DYNAMIC_REQUIRE.search(content) or _JS_DYNAMIC_IMPORT.search(content))


# ---------------------------------------------------------------------------
# Whitelist checks
# ---------------------------------------------------------------------------

def is_whitelisted_entry_point(path: str, manifest_entry_points: set[str]) -> bool:
    """Check if a file path is a whitelisted entry point."""
    norm_path = path.replace("\\", "/").lower()
    p = Path(norm_path)
    stem = p.stem.lower()
    name = p.name.lower()

    # 1. Check directories (tests, scripts, bin)
    parts = set(p.parts)
    if parts & ENTRY_POINT_DIRS:
        return True

    # 2. Check stem / name
    if stem in DEFAULT_ENTRY_POINTS or name in DEFAULT_ENTRY_POINTS:
        return True

    # 3. Check prefixes/suffixes for test and config files
    if stem.startswith("test_") or stem.endswith("_test"):
        return True
    if ".config" in name or name.endswith(".config.js") or name.endswith(".config.ts"):
        return True
    if ".test." in name or ".spec." in name:
        return True

    # 4. Check manifest entry points (from package.json or pyproject.toml)
    for entry in manifest_entry_points:
        clean_entry = entry.replace("\\", "/").lower()
        if clean_entry in norm_path or norm_path.endswith(clean_entry) or stem in clean_entry:
            return True

    return False


def extract_manifest_entry_points(contract_files: ContractFiles) -> set[str]:
    """Extract entry point paths and symbols declared in manifests."""
    entry_points: set[str] = set()

    for manifest in contract_files.manifests:
        name = Path(manifest.path).name.lower()
        content = manifest.content

        # package.json
        if name == "package.json":
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    for key in ("main", "module", "browser"):
                        val = data.get(key)
                        if isinstance(val, str):
                            entry_points.add(val.strip())
                    bin_val = data.get("bin")
                    if isinstance(bin_val, str):
                        entry_points.add(bin_val.strip())
                    elif isinstance(bin_val, dict):
                        for b_path in bin_val.values():
                            if isinstance(b_path, str):
                                entry_points.add(b_path.strip())
                    scripts = data.get("scripts", {})
                    if isinstance(scripts, dict):
                        for cmd in scripts.values():
                            if isinstance(cmd, str):
                                for token in cmd.split():
                                    if token.endswith((".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs")):
                                        entry_points.add(token.strip())
            except Exception:
                pass

        # pyproject.toml
        elif name == "pyproject.toml":
            for line in content.splitlines():
                if "=" in line and ("scripts" in line or ":" in line):
                    val = line.split("=", 1)[1].strip().strip('"\'')
                    if ":" in val:
                        mod = val.split(":", 1)[0].strip()
                        entry_points.add(mod)
                        entry_points.add(mod.split(".")[-1])

    return entry_points


# ---------------------------------------------------------------------------
# Python import graph extraction
# ---------------------------------------------------------------------------

def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def build_python_import_graph(source_files: list[IndexedFile]) -> dict[str, set[str]]:
    """Build import graph for Python files.

    Returns:
        dict mapping file path to set of imported file paths / module names.
    """
    graph: dict[str, set[str]] = {sf.path: set() for sf in source_files}

    # Index available files
    files_by_stem: dict[str, list[str]] = {}
    files_by_norm: set[str] = set()

    for sf in source_files:
        norm = _normalize_path(sf.path)
        files_by_norm.add(norm)
        stem = Path(norm).stem
        files_by_stem.setdefault(stem, []).append(sf.path)

    for sf in source_files:
        if sf.language != "python":
            continue
        try:
            tree = ast.parse(sf.content)
        except SyntaxError:
            continue

        src_norm = _normalize_path(sf.path)
        src_dir = str(Path(src_norm).parent)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name
                    top = mod.split(".")[0]
                    # Direct match with stem or file
                    if top in files_by_stem:
                        for target in files_by_stem[top]:
                            graph[sf.path].add(target)
                    else:
                        graph[sf.path].add(mod)

            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                level = node.level

                if level == 0:
                    top = mod.split(".")[0]
                    if top in files_by_stem:
                        for target in files_by_stem[top]:
                            graph[sf.path].add(target)
                    else:
                        # Check submodules
                        subpath = mod.replace(".", "/") + ".py"
                        matched = False
                        for candidate in files_by_norm:
                            if candidate.endswith(subpath) or candidate.endswith(f"{mod.replace('.', '/')}/__init__.py"):
                                graph[sf.path].add(candidate)
                                matched = True
                        if not matched:
                            graph[sf.path].add(mod)
                else:
                    # Relative import
                    curr = Path(src_norm).parent
                    for _ in range(level - 1):
                        curr = curr.parent
                    rel_mod = mod.replace(".", "/") if mod else ""
                    target_base = (curr / rel_mod).as_posix() if rel_mod else curr.as_posix()

                    for candidate in files_by_norm:
                        cand_posix = Path(candidate).as_posix()
                        if cand_posix.startswith(target_base) or Path(candidate).stem in mod:
                            graph[sf.path].add(candidate)

    return graph


# ---------------------------------------------------------------------------
# JS/TS import graph extraction
# ---------------------------------------------------------------------------

_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[\w*\s{},]+from\s+)?|export\s+(?:[\w*\s{},]+from\s+)?|require\s*\(\s*)['"]([^'"]+)['"]"""
)


def build_js_import_graph(source_files: list[IndexedFile]) -> dict[str, set[str]]:
    """Build import graph for JavaScript/TypeScript files."""
    graph: dict[str, set[str]] = {sf.path: set() for sf in source_files}

    files_by_norm = {_normalize_path(sf.path): sf.path for sf in source_files}
    files_by_stem = {Path(sf.path).stem: sf.path for sf in source_files}

    for sf in source_files:
        if sf.language not in ("javascript", "typescript"):
            continue

        src_dir = Path(_normalize_path(sf.path)).parent

        for line in sf.content.splitlines():
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*"):
                continue

            for m in _JS_IMPORT_RE.finditer(line):
                import_path = m.group(1).strip()

                if import_path.startswith("."):
                    resolved = (src_dir / import_path).resolve()
                    matched = False
                    for ext in ("", ".js", ".ts", ".jsx", ".tsx", "/index.js", "/index.ts"):
                        test_path = _normalize_path(str(src_dir / f"{import_path}{ext}"))
                        for norm_f, original_p in files_by_norm.items():
                            if norm_f.endswith(test_path.lstrip("./")) or Path(norm_f).stem == Path(import_path).stem:
                                graph[sf.path].add(original_p)
                                matched = True
                                break
                        if matched:
                            break
                    if not matched:
                        graph[sf.path].add(import_path)
                else:
                    graph[sf.path].add(import_path)

    return graph


# ---------------------------------------------------------------------------
# Orphan file detection
# ---------------------------------------------------------------------------

_id_seq = 0


def _next_id(prefix: str = "SLP") -> str:
    global _id_seq
    _id_seq += 1
    return f"{prefix}-{_id_seq:03d}"


def find_orphaned_files(
    source_files: list[IndexedFile],
    contract_files: ContractFiles,
) -> list[Finding]:
    """Find source files that are never imported anywhere and are not entry points."""
    if not source_files:
        return []

    manifest_entries = extract_manifest_entry_points(contract_files)

    # Check for dynamic imports across all source files
    has_dynamic = False
    for sf in source_files:
        if sf.language == "python" and has_dynamic_imports_python(sf.content):
            has_dynamic = True
            break
        elif sf.language in ("javascript", "typescript") and has_dynamic_imports_js(sf.content):
            has_dynamic = True
            break

    py_graph = build_python_import_graph(source_files)
    js_graph = build_js_import_graph(source_files)

    # Collect all imported targets
    imported_targets: set[str] = set()
    for targets in py_graph.values():
        imported_targets.update(targets)
    for targets in js_graph.values():
        imported_targets.update(targets)

    findings: list[Finding] = []

    for sf in source_files:
        path = sf.path
        norm_path = _normalize_path(path)
        stem = Path(norm_path).stem

        # 1. Skip whitelisted entry points
        if is_whitelisted_entry_point(path, manifest_entries):
            continue

        # 2. Check if imported by another file
        is_imported = False
        if path in imported_targets or norm_path in imported_targets:
            is_imported = True
        else:
            for tgt in imported_targets:
                if stem == tgt or norm_path.endswith(tgt) or tgt.endswith(norm_path):
                    is_imported = True
                    break

        if not is_imported:
            confidence = 0.60 if has_dynamic else 0.85
            findings.append(
                Finding(
                    id=_next_id("SLP"),
                    category=Category.SLOP,
                    severity=Severity.LOW,
                    confidence=confidence,
                    file=path,
                    line=None,
                    title=f"Orphaned file '{path}' is never imported",
                    evidence=f"No other file in the repository imports '{path}', and it is not a recognized entry point",
                    suggested_fix=f"Import '{path}' where needed or remove it if obsolete",
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Unused dependency detection
# ---------------------------------------------------------------------------

_REQ_SPEC_RE = re.compile(r"^([a-zA-Z0-9_.\-]+)")


def parse_python_dependencies(content: str) -> set[str]:
    """Parse dependency names from requirements.txt."""
    deps: set[str] = set()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r", "-i", "--extra-index-url", "--index-url", "-f")):
            continue
        m = _REQ_SPEC_RE.match(line)
        if m:
            dep_name = m.group(1).strip()
            deps.add(dep_name.lower())
    return deps


def parse_js_dependencies(content: str) -> set[str]:
    """Parse dependencies from package.json."""
    deps: set[str] = set()
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            dependencies = data.get("dependencies", {})
            if isinstance(dependencies, dict):
                for dep in dependencies.keys():
                    deps.add(dep.strip())
    except Exception:
        pass
    return deps


def _collect_imported_modules(source_files: list[IndexedFile]) -> tuple[set[str], set[str], bool]:
    """Collect imported module names for Python and JS, and check for dynamic imports."""
    py_modules: set[str] = set()
    js_modules: set[str] = set()
    has_dynamic = False

    for sf in source_files:
        if sf.language == "python":
            if has_dynamic_imports_python(sf.content):
                has_dynamic = True
            try:
                tree = ast.parse(sf.content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            py_modules.add(alias.name.split(".")[0].lower())
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            py_modules.add(node.module.split(".")[0].lower())
            except SyntaxError:
                pass

        elif sf.language in ("javascript", "typescript"):
            if has_dynamic_imports_js(sf.content):
                has_dynamic = True
            for line in sf.content.splitlines():
                for m in _JS_IMPORT_RE.finditer(line):
                    target = m.group(1).strip()
                    if not target.startswith("."):
                        if target.startswith("@"):
                            parts = target.split("/")
                            if len(parts) >= 2:
                                js_modules.add(f"{parts[0]}/{parts[1]}")
                            else:
                                js_modules.add(target)
                        else:
                            js_modules.add(target.split("/")[0])

    return py_modules, js_modules, has_dynamic


def check_unused_dependencies(
    source_files: list[IndexedFile],
    contract_files: ContractFiles,
) -> list[Finding]:
    """Check for dependencies declared in manifests but never imported in source files."""
    findings: list[Finding] = []

    py_imported, js_imported, has_dynamic = _collect_imported_modules(source_files)
    confidence = 0.60 if has_dynamic else 0.80

    for manifest in contract_files.manifests:
        name = Path(manifest.path).name.lower()

        # Python: requirements.txt
        if name.startswith("requirements") and name.endswith((".txt", ".in")):
            declared_deps = parse_python_dependencies(manifest.content)
            for dep in sorted(declared_deps):
                # Check directly, mapped, and normalized
                norm_dep = dep.replace("-", "_").lower()
                clean_dep = dep.lower()

                mapped_names = COMMON_PYTHON_DEP_MAPPINGS.get(clean_dep, set())

                is_used = (
                    clean_dep in py_imported
                    or norm_dep in py_imported
                    or any(m.lower() in py_imported for m in mapped_names)
                )

                if not is_used:
                    findings.append(
                        Finding(
                            id=_next_id("SLP"),
                            category=Category.SLOP,
                            severity=Severity.LOW,
                            confidence=confidence,
                            file=manifest.path,
                            line=None,
                            title=f"Unused dependency '{dep}' in {name}",
                            evidence=f"'{dep}' is declared in {manifest.path} but never imported in source files",
                            suggested_fix=f"Remove '{dep}' from {manifest.path} if it is not used",
                        )
                    )

        # JS: package.json
        elif name == "package.json":
            declared_deps = parse_js_dependencies(manifest.content)
            for dep in sorted(declared_deps):
                if dep not in js_imported:
                    findings.append(
                        Finding(
                            id=_next_id("SLP"),
                            category=Category.SLOP,
                            severity=Severity.LOW,
                            confidence=confidence,
                            file=manifest.path,
                            line=None,
                            title=f"Unused dependency '{dep}' in package.json",
                            evidence=f"'{dep}' is declared in package.json dependencies but never imported in source files",
                            suggested_fix=f"Remove '{dep}' from package.json if it is not used",
                        )
                    )

    return findings


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def audit_slop(
    source_files: list[IndexedFile],
    contract_files: ContractFiles | Any = None,
) -> list[Finding]:
    """Main entry point for slop auditor."""
    if contract_files is None or not isinstance(contract_files, ContractFiles):
        cf = ContractFiles()
    else:
        cf = contract_files

    findings: list[Finding] = []
    findings.extend(find_orphaned_files(source_files, cf))
    findings.extend(check_unused_dependencies(source_files, cf))
    return findings
