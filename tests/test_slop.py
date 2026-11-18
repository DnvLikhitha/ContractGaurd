"""Tests for the slop auditor — orphaned files and unused dependencies.

Tests are written BEFORE implementation per CLAUDE.md rules.
All fixtures are inline snippets; no tmp_path repos needed.
"""

import pytest

from contractguard.auditors.slop import (
    build_python_import_graph,
    build_js_import_graph,
    has_dynamic_imports_python,
    has_dynamic_imports_js,
    is_whitelisted_entry_point,
    extract_manifest_entry_points,
    find_orphaned_files,
    parse_python_dependencies,
    parse_js_dependencies,
    check_unused_dependencies,
    audit_slop,
)
from contractguard.models import IndexedFile, ContractFiles, Category, Severity, Finding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _py_file(content: str, path: str = "app.py") -> IndexedFile:
    return IndexedFile(path=path, is_source=True, language="python", content=content)


def _js_file(content: str, path: str = "app.js") -> IndexedFile:
    return IndexedFile(path=path, is_source=True, language="javascript", content=content)


def _ts_file(content: str, path: str = "app.ts") -> IndexedFile:
    return IndexedFile(path=path, is_source=True, language="typescript", language_name="typescript", content=content)


def _manifest(path: str, content: str) -> IndexedFile:
    return IndexedFile(path=path, is_contract=True, language=None, content=content)


def _contract_with_manifests(*manifest_tuples: tuple[str, str]) -> ContractFiles:
    cf = ContractFiles()
    for path, content in manifest_tuples:
        cf.manifests.append(_manifest(path, content))
    return cf


# ---------------------------------------------------------------------------
# Python import graph extraction
# ---------------------------------------------------------------------------

class TestPythonImportGraph:
    def test_standard_import(self):
        files = [
            _py_file("import helper\nhelper.run()", path="main.py"),
            _py_file("def run(): pass", path="helper.py"),
        ]
        graph = build_python_import_graph(files)
        # main.py imports helper.py
        assert "helper.py" in graph.get("main.py", set()) or any("helper" in tgt for tgt in graph.get("main.py", set()))

    def test_from_import(self):
        files = [
            _py_file("from utils.db import get_db", path="main.py"),
            _py_file("def get_db(): pass", path="utils/db.py"),
        ]
        graph = build_python_import_graph(files)
        targets = graph.get("main.py", set())
        assert any("utils/db.py" in t or "utils.db" in t for t in targets)

    def test_relative_import_same_dir(self):
        files = [
            _py_file("from .worker import start", path="pkg/server.py"),
            _py_file("def start(): pass", path="pkg/worker.py"),
        ]
        graph = build_python_import_graph(files)
        targets = graph.get("pkg/server.py", set())
        assert any("pkg/worker.py" in t or "worker" in t for t in targets)

    def test_relative_import_parent_dir(self):
        files = [
            _py_file("from ..common import util", path="pkg/sub/nested.py"),
            _py_file("def util(): pass", path="pkg/common.py"),
        ]
        graph = build_python_import_graph(files)
        targets = graph.get("pkg/sub/nested.py", set())
        assert any("pkg/common.py" in t or "common" in t for t in targets)

    def test_syntax_error_handled_gracefully(self):
        files = [
            _py_file("this is not python code !@#$", path="bad.py"),
            _py_file("import helper", path="main.py"),
        ]
        graph = build_python_import_graph(files)
        assert isinstance(graph, dict)


# ---------------------------------------------------------------------------
# JS/TS import graph extraction
# ---------------------------------------------------------------------------

class TestJSImportGraph:
    def test_es_module_import_relative(self):
        files = [
            _js_file("import { helper } from './utils.js';", path="index.js"),
            _js_file("export const helper = 1;", path="utils.js"),
        ]
        graph = build_js_import_graph(files)
        targets = graph.get("index.js", set())
        assert any("utils.js" in t or "./utils" in t for t in targets)

    def test_commonjs_require(self):
        files = [
            _js_file("const utils = require('./utils');", path="index.js"),
            _js_file("module.exports = {};", path="utils.js"),
        ]
        graph = build_js_import_graph(files)
        targets = graph.get("index.js", set())
        assert any("utils" in t for t in targets)

    def test_ts_import_without_extension(self):
        files = [
            _js_file("import { config } from '../config';", path="src/server.ts"),
            _js_file("export const config = {};", path="config.ts"),
        ]
        graph = build_js_import_graph(files)
        targets = graph.get("src/server.ts", set())
        assert any("config" in t for t in targets)


# ---------------------------------------------------------------------------
# Dynamic import detection
# ---------------------------------------------------------------------------

class TestDynamicImports:
    def test_detects_importlib_python(self):
        code = "import importlib\nmod = importlib.import_module('dynamic_module')"
        assert has_dynamic_imports_python(code) is True

    def test_detects_dunder_import_python(self):
        code = "mod = __import__('dynamic_plugin')"
        assert has_dynamic_imports_python(code) is True

    def test_no_dynamic_imports_python(self):
        code = "import os\nfrom pathlib import Path"
        assert has_dynamic_imports_python(code) is False

    def test_detects_dynamic_require_js(self):
        code = "const plugin = require(pluginName);"
        assert has_dynamic_imports_js(code) is True

    def test_detects_dynamic_import_expression_js(self):
        code = "const mod = await import(`./plugins/${name}`);"
        assert has_dynamic_imports_js(code) is True

    def test_no_dynamic_imports_js(self):
        code = "import { foo } from './foo';\nconst bar = require('./bar');"
        assert has_dynamic_imports_js(code) is False


# ---------------------------------------------------------------------------
# Whitelist entry points
# ---------------------------------------------------------------------------

class TestWhitelistedEntryPoints:
    @pytest.mark.parametrize("path", [
        "main.py",
        "__main__.py",
        "__init__.py",
        "app.py",
        "index.js",
        "index.ts",
        "cli.py",
        "cli.js",
        "setup.py",
        "manage.py",
        "wsgi.py",
        "asgi.py",
        "conftest.py",
        "webpack.config.js",
        "vite.config.ts",
        "tests/test_something.py",
        "src/component.test.js",
        "src/util.spec.ts",
        "tests/helpers.py",
    ])
    def test_default_whitelisted_files(self, path):
        assert is_whitelisted_entry_point(path, set()) is True

    def test_non_whitelisted_internal_file(self):
        assert is_whitelisted_entry_point("services/payment_old.py", set()) is False
        assert is_whitelisted_entry_point("lib/unused_util.js", set()) is False

    def test_manifest_whitelisted_file(self):
        # Referenced in package.json or pyproject.toml
        manifest_entries = {"scripts/custom_runner.py", "bin/my_cli.js"}
        assert is_whitelisted_entry_point("scripts/custom_runner.py", manifest_entries) is True
        assert is_whitelisted_entry_point("bin/my_cli.js", manifest_entries) is True

    def test_extract_manifest_entry_points_package_json(self):
        pkg_json = """{
            "main": "dist/bundle.js",
            "bin": {
                "mytool": "./bin/tool.js"
            },
            "scripts": {
                "start": "node src/server.js",
                "build": "webpack --config build.config.js"
            }
        }"""
        cf = _contract_with_manifests(("package.json", pkg_json))
        entries = extract_manifest_entry_points(cf)
        assert any("dist/bundle.js" in e or "bundle.js" in e for e in entries)
        assert any("bin/tool.js" in e or "tool.js" in e for e in entries)
        assert any("src/server.js" in e or "server.js" in e for e in entries)

    def test_extract_manifest_entry_points_pyproject_toml(self):
        pyproject = """
[project.scripts]
contractguard = "contractguard.cli:main"
custom = "scripts.migrate:run"
"""
        cf = _contract_with_manifests(("pyproject.toml", pyproject))
        entries = extract_manifest_entry_points(cf)
        assert any("cli" in e for e in entries)
        assert any("migrate" in e for e in entries)


# ---------------------------------------------------------------------------
# find_orphaned_files
# ---------------------------------------------------------------------------

class TestFindOrphanedFiles:
    def test_orphaned_python_file_detected(self):
        files = [
            _py_file("from utils import helper\nhelper()", path="main.py"),
            _py_file("def helper(): pass", path="utils.py"),
            _py_file("def dead_code(): pass", path="legacy_dead.py"),
        ]
        cf = ContractFiles()
        orphans = find_orphaned_files(files, cf)
        orphan_paths = [f.file for f in orphans]
        assert "legacy_dead.py" in orphan_paths
        assert "main.py" not in orphan_paths  # whitelisted entry point
        assert "utils.py" not in orphan_paths  # imported by main.py

    def test_orphaned_js_file_detected(self):
        files = [
            _js_file("import { active } from './active.js';", path="index.js"),
            _js_file("export const active = true;", path="active.js"),
            _js_file("export const unused = true;", path="components/OrphanComponent.js"),
        ]
        cf = ContractFiles()
        orphans = find_orphaned_files(files, cf)
        orphan_paths = [f.file for f in orphans]
        assert "components/OrphanComponent.js" in orphan_paths
        assert "index.js" not in orphan_paths
        assert "active.js" not in orphan_paths

    def test_orphan_finding_attributes(self):
        files = [
            _py_file("def dead(): pass", path="services/old_service.py"),
            _py_file("print('hello')", path="app.py"),
        ]
        cf = ContractFiles()
        orphans = find_orphaned_files(files, cf)
        assert len(orphans) == 1
        finding = orphans[0]
        assert finding.category == "slop"
        assert finding.severity == "low"
        assert finding.confidence == pytest.approx(0.85)
        assert finding.file == "services/old_service.py"
        assert "orphan" in finding.title.lower()

    def test_lower_confidence_when_dynamic_imports_present(self):
        files = [
            _py_file("import importlib\nmod = importlib.import_module('dyn')", path="app.py"),
            _py_file("def unknown(): pass", path="mystery.py"),
        ]
        cf = ContractFiles()
        orphans = find_orphaned_files(files, cf)
        mystery = [f for f in orphans if f.file == "mystery.py"]
        assert len(mystery) == 1
        # Confidence should be lowered due to dynamic imports
        assert mystery[0].confidence <= 0.65


# ---------------------------------------------------------------------------
# parse_python_dependencies
# ---------------------------------------------------------------------------

class TestParsePythonDependencies:
    def test_requirements_txt_simple(self):
        content = "requests==2.28.1\nflask>=2.0.0\npytest\n"
        deps = parse_python_dependencies(content)
        assert "requests" in deps
        assert "flask" in deps
        assert "pytest" in deps

    def test_requirements_txt_comments_and_flags(self):
        content = """
# Production requirements
-r base.txt
--extra-index-url https://example.com/pypi
requests==2.28.1  # for HTTP calls
pyyaml>=6.0; python_version >= '3.8'
gunicorn[gevent]~=20.1
"""
        deps = parse_python_dependencies(content)
        assert "requests" in deps
        assert "pyyaml" in deps
        assert "gunicorn" in deps
        assert "base.txt" not in deps

    def test_empty_requirements(self):
        assert parse_python_dependencies("") == set()


# ---------------------------------------------------------------------------
# parse_js_dependencies
# ---------------------------------------------------------------------------

class TestParseJSDependencies:
    def test_package_json_dependencies(self):
        content = """{
            "name": "myapp",
            "dependencies": {
                "express": "^4.18.2",
                "lodash": "^4.17.21",
                "@auth0/nextjs-auth0": "^3.0.0"
            },
            "devDependencies": {
                "jest": "^29.0.0",
                "typescript": "^5.0.0"
            }
        }"""
        deps = parse_js_dependencies(content)
        assert "express" in deps
        assert "lodash" in deps
        assert "@auth0/nextjs-auth0" in deps
        # devDependencies are ignored for runtime slop
        assert "jest" not in deps
        assert "typescript" not in deps

    def test_invalid_json_returns_empty(self):
        assert parse_js_dependencies("invalid json {{{") == set()


# ---------------------------------------------------------------------------
# check_unused_dependencies
# ---------------------------------------------------------------------------

class TestCheckUnusedDependencies:
    def test_unused_python_dependency_detected(self):
        reqs = "requests==2.28.0\nflask==2.0.0\nunused-pkg==1.0.0\n"
        files = [
            _py_file("import requests\nfrom flask import Flask", path="app.py"),
        ]
        cf = _contract_with_manifests(("requirements.txt", reqs))
        findings = check_unused_dependencies(files, cf)
        unused = [f for f in findings if "unused-pkg" in f.title]
        assert len(unused) == 1
        assert unused[0].category == "slop"
        assert unused[0].severity == "low"
        assert unused[0].confidence == pytest.approx(0.80)

    def test_common_python_name_mismatch_not_flagged(self):
        """pyyaml -> import yaml, scikit-learn -> import sklearn, pillow -> import PIL"""
        reqs = "pyyaml==6.0\nscikit-learn==1.3.0\npillow==10.0.0\n"
        files = [
            _py_file("import yaml\nimport sklearn\nfrom PIL import Image", path="app.py"),
        ]
        cf = _contract_with_manifests(("requirements.txt", reqs))
        findings = check_unused_dependencies(files, cf)
        assert len(findings) == 0

    def test_unused_js_dependency_detected(self):
        pkg_json = """{
            "dependencies": {
                "express": "^4.18.2",
                "unused-library": "^1.0.0"
            }
        }"""
        files = [
            _js_file("const express = require('express');", path="server.js"),
        ]
        cf = _contract_with_manifests(("package.json", pkg_json))
        findings = check_unused_dependencies(files, cf)
        unused = [f for f in findings if "unused-library" in f.title]
        assert len(unused) == 1
        assert unused[0].category == "slop"

    def test_js_scoped_and_subpath_import_recognized(self):
        pkg_json = """{
            "dependencies": {
                "lodash": "^4.17.21",
                "@auth0/nextjs-auth0": "^3.0.0"
            }
        }"""
        files = [
            _js_file("import get from 'lodash/get';\nimport { handleAuth } from '@auth0/nextjs-auth0';", path="app.js"),
        ]
        cf = _contract_with_manifests(("package.json", pkg_json))
        findings = check_unused_dependencies(files, cf)
        assert len(findings) == 0

    def test_dynamic_imports_lower_dependency_confidence(self):
        reqs = "mystery-pkg==1.0.0\n"
        files = [
            _py_file("import importlib\nimportlib.import_module('something')", path="app.py"),
        ]
        cf = _contract_with_manifests(("requirements.txt", reqs))
        findings = check_unused_dependencies(files, cf)
        unused = [f for f in findings if "mystery-pkg" in f.title]
        assert len(unused) == 1
        assert unused[0].confidence <= 0.65


# ---------------------------------------------------------------------------
# audit_slop (integration)
# ---------------------------------------------------------------------------

class TestAuditSlopIntegration:
    def test_returns_list_of_findings(self):
        reqs = "unused-dep==1.0\n"
        files = [
            _py_file("def dead(): pass", path="old.py"),
            _py_file("print('ok')", path="main.py"),
        ]
        cf = _contract_with_manifests(("requirements.txt", reqs))
        findings = audit_slop(files, cf)
        assert isinstance(findings, list)
        for item in findings:
            assert isinstance(item, Finding)
            assert item.category == "slop"

    def test_empty_repo_no_findings(self):
        assert audit_slop([], ContractFiles()) == []
