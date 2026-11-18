"""Tests for the drift auditor — env-contract drift and README-to-code drift.

Tests are written BEFORE implementation per CLAUDE.md rules.
All fixtures are inline snippets; no tmp_path repos needed.
"""

import pytest

from contractguard.auditors.drift import (
    extract_env_vars_from_python,
    extract_env_vars_from_js,
    extract_env_vars_from_go,
    extract_env_vars_from_file,
    parse_env_example,
    parse_docker_compose_env,
    check_env_drift,
    extract_endpoints_from_readme,
    extract_commands_from_readme,
    check_readme_drift,
    audit_drift,
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
    return IndexedFile(path=path, is_source=True, language="typescript", content=content)


def _go_file(content: str, path: str = "main.go") -> IndexedFile:
    return IndexedFile(path=path, is_source=True, language="go", content=content)


def _env_example_file(content: str) -> IndexedFile:
    return IndexedFile(path=".env.example", is_contract=True, language=None, content=content)


def _compose_file(content: str) -> IndexedFile:
    return IndexedFile(path="docker-compose.yml", is_contract=True, language="yaml", content=content)


def _readme_file(content: str) -> IndexedFile:
    return IndexedFile(path="README.md", is_contract=True, language="markdown", content=content)


def _contract(
    env_example: str | None = None,
    compose: str | None = None,
    readme: str | None = None,
) -> ContractFiles:
    cf = ContractFiles()
    if env_example is not None:
        cf.env_example = _env_example_file(env_example)
    if compose is not None:
        cf.docker_compose.append(_compose_file(compose))
    if readme is not None:
        cf.readme = _readme_file(readme)
    return cf


# ---------------------------------------------------------------------------
# P0: extract_env_vars_from_python
# ---------------------------------------------------------------------------

class TestExtractEnvVarsPython:
    def test_os_getenv_double_quotes(self):
        code = 'x = os.getenv("DATABASE_URL")'
        assert "DATABASE_URL" in extract_env_vars_from_python(code)

    def test_os_getenv_single_quotes(self):
        code = "x = os.getenv('SECRET_KEY')"
        assert "SECRET_KEY" in extract_env_vars_from_python(code)

    def test_os_getenv_with_default(self):
        code = 'x = os.getenv("PORT", "8080")'
        assert "PORT" in extract_env_vars_from_python(code)

    def test_os_environ_subscript(self):
        code = 'x = os.environ["API_KEY"]'
        assert "API_KEY" in extract_env_vars_from_python(code)

    def test_os_environ_get(self):
        code = 'x = os.environ.get("AWS_REGION")'
        assert "AWS_REGION" in extract_env_vars_from_python(code)

    def test_os_environ_get_with_default(self):
        code = 'x = os.environ.get("LOG_LEVEL", "INFO")'
        assert "LOG_LEVEL" in extract_env_vars_from_python(code)

    def test_multiple_vars_in_file(self):
        code = (
            'db = os.getenv("DATABASE_URL")\n'
            'secret = os.environ["SECRET_KEY"]\n'
            'region = os.environ.get("AWS_REGION")\n'
        )
        result = extract_env_vars_from_python(code)
        assert "DATABASE_URL" in result
        assert "SECRET_KEY" in result
        assert "AWS_REGION" in result

    def test_returns_set(self):
        code = 'x = os.getenv("FOO")\ny = os.getenv("FOO")'
        result = extract_env_vars_from_python(code)
        assert isinstance(result, set)
        assert result == {"FOO"}

    def test_no_vars_returns_empty(self):
        code = "x = 42\nprint('hello')"
        assert extract_env_vars_from_python(code) == set()

    def test_comment_line_ignored(self):
        code = '# os.getenv("COMMENT_VAR")\nx = os.getenv("REAL_VAR")'
        result = extract_env_vars_from_python(code)
        assert "REAL_VAR" in result
        assert "COMMENT_VAR" not in result

    def test_environ_set_not_extracted(self):
        code = 'os.environ["SET_VAR"] = "value"'
        result = extract_env_vars_from_python(code)
        assert "SET_VAR" not in result


# ---------------------------------------------------------------------------
# P0: extract_env_vars_from_js
# ---------------------------------------------------------------------------

class TestExtractEnvVarsJS:
    def test_process_env_dot(self):
        code = "const db = process.env.DATABASE_URL;"
        assert "DATABASE_URL" in extract_env_vars_from_js(code)

    def test_process_env_bracket(self):
        code = "const key = process.env['API_KEY'];"
        assert "API_KEY" in extract_env_vars_from_js(code)

    def test_process_env_bracket_double(self):
        code = 'const key = process.env["SECRET"];'
        assert "SECRET" in extract_env_vars_from_js(code)

    def test_import_meta_env(self):
        code = "const url = import.meta.env.VITE_API_URL;"
        assert "VITE_API_URL" in extract_env_vars_from_js(code)

    def test_import_meta_env_bracket(self):
        code = "const url = import.meta.env['REACT_APP_URL'];"
        assert "REACT_APP_URL" in extract_env_vars_from_js(code)

    def test_multiple_vars(self):
        code = (
            "const a = process.env.PORT;\n"
            "const b = process.env.SECRET_KEY;\n"
        )
        result = extract_env_vars_from_js(code)
        assert "PORT" in result
        assert "SECRET_KEY" in result

    def test_returns_set(self):
        code = "process.env.FOO; process.env.FOO;"
        result = extract_env_vars_from_js(code)
        assert isinstance(result, set)
        assert result == {"FOO"}

    def test_no_vars_returns_empty(self):
        code = "const x = 42;"
        assert extract_env_vars_from_js(code) == set()


# ---------------------------------------------------------------------------
# P0: extract_env_vars_from_go
# ---------------------------------------------------------------------------

class TestExtractEnvVarsGo:
    def test_os_getenv(self):
        code = 'port := os.Getenv("PORT")'
        assert "PORT" in extract_env_vars_from_go(code)

    def test_os_lookupenv(self):
        code = 'val, ok := os.LookupEnv("DATABASE_URL")'
        assert "DATABASE_URL" in extract_env_vars_from_go(code)

    def test_multiple_go_vars(self):
        code = (
            'p := os.Getenv("PORT")\n'
            's := os.Getenv("SECRET_KEY")\n'
        )
        result = extract_env_vars_from_go(code)
        assert "PORT" in result
        assert "SECRET_KEY" in result

    def test_comment_line_ignored(self):
        code = '// os.Getenv("COMMENT_VAR")\np := os.Getenv("REAL_VAR")'
        result = extract_env_vars_from_go(code)
        assert "REAL_VAR" in result
        assert "COMMENT_VAR" not in result


# ---------------------------------------------------------------------------
# P0: extract_env_vars_from_file (dispatch)
# ---------------------------------------------------------------------------

class TestExtractEnvVarsFromFile:
    def test_dispatches_python(self):
        f = _py_file('x = os.getenv("MY_PY_VAR")')
        assert "MY_PY_VAR" in extract_env_vars_from_file(f)

    def test_dispatches_javascript(self):
        f = _js_file("const x = process.env.MY_JS_VAR;")
        assert "MY_JS_VAR" in extract_env_vars_from_file(f)

    def test_dispatches_typescript(self):
        f = _ts_file("const x = process.env.MY_TS_VAR;")
        assert "MY_TS_VAR" in extract_env_vars_from_file(f)

    def test_dispatches_go(self):
        f = _go_file('p := os.Getenv("MY_GO_VAR")')
        assert "MY_GO_VAR" in extract_env_vars_from_file(f)

    def test_unknown_language_fallback_regex(self):
        f = IndexedFile(path="file.rs", is_source=True, language="rust", content='std::env::var("RUST_VAR")')
        # Even if not specialized, should not raise error
        res = extract_env_vars_from_file(f)
        assert isinstance(res, set)


# ---------------------------------------------------------------------------
# P0: parse_env_example
# ---------------------------------------------------------------------------

class TestParseEnvExample:
    def test_simple_key_value(self):
        content = "DATABASE_URL=postgres://localhost/db\n"
        assert "DATABASE_URL" in parse_env_example(content)

    def test_key_no_value(self):
        content = "SECRET_KEY=\n"
        assert "SECRET_KEY" in parse_env_example(content)

    def test_key_with_comment_value(self):
        content = "API_KEY=your_key_here  # replace this\n"
        assert "API_KEY" in parse_env_example(content)

    def test_comment_lines_skipped(self):
        content = "# This is a comment\nREAL_VAR=value\n"
        result = parse_env_example(content)
        assert "REAL_VAR" in result
        assert "This is a comment" not in result

    def test_blank_lines_skipped(self):
        content = "\n\nFOO=bar\n\n"
        result = parse_env_example(content)
        assert "FOO" in result

    def test_multiple_vars(self):
        content = "DB_HOST=localhost\nDB_PORT=5432\nDB_NAME=myapp\n"
        result = parse_env_example(content)
        assert result == {"DB_HOST", "DB_PORT", "DB_NAME"}

    def test_returns_set(self):
        content = "FOO=1\nFOO=2\n"
        assert isinstance(parse_env_example(content), set)

    def test_empty_content(self):
        assert parse_env_example("") == set()

    def test_quoted_value(self):
        content = 'MY_SECRET="something complex"\n'
        assert "MY_SECRET" in parse_env_example(content)

    def test_export_prefix(self):
        content = "export AWS_REGION=us-east-1\n"
        result = parse_env_example(content)
        assert "AWS_REGION" in result


# ---------------------------------------------------------------------------
# P0: parse_docker_compose_env
# ---------------------------------------------------------------------------

class TestParseDockerComposeEnv:
    COMPOSE_LIST_STYLE = """\
version: "3"
services:
  app:
    environment:
      - DATABASE_URL=postgres://localhost/db
      - SECRET_KEY=
      - PORT=8080
"""

    COMPOSE_MAP_STYLE = """\
version: "3"
services:
  app:
    environment:
      DATABASE_URL: postgres://localhost/db
      SECRET_KEY:
      PORT: "8080"
"""

    COMPOSE_MULTI_SERVICE = """\
version: "3"
services:
  web:
    environment:
      - WEB_VAR=1
  worker:
    environment:
      - WORKER_VAR=2
"""

    def test_list_style_vars(self):
        result = parse_docker_compose_env(self.COMPOSE_LIST_STYLE)
        assert "DATABASE_URL" in result
        assert "SECRET_KEY" in result
        assert "PORT" in result

    def test_map_style_vars(self):
        result = parse_docker_compose_env(self.COMPOSE_MAP_STYLE)
        assert "DATABASE_URL" in result
        assert "SECRET_KEY" in result
        assert "PORT" in result

    def test_multi_service(self):
        result = parse_docker_compose_env(self.COMPOSE_MULTI_SERVICE)
        assert "WEB_VAR" in result
        assert "WORKER_VAR" in result

    def test_returns_set(self):
        assert isinstance(parse_docker_compose_env(self.COMPOSE_LIST_STYLE), set)

    def test_empty_content(self):
        assert parse_docker_compose_env("") == set()

    def test_no_environment_key(self):
        content = "version: '3'\nservices:\n  app:\n    image: nginx\n"
        assert parse_docker_compose_env(content) == set()

    def test_invalid_yaml_returns_empty(self):
        assert parse_docker_compose_env("{{{{ not valid yaml") == set()


# ---------------------------------------------------------------------------
# P0: check_env_drift (diff both directions)
# ---------------------------------------------------------------------------

class TestCheckEnvDrift:
    def test_missing_in_env_example_is_high_severity(self):
        """Var used in code but absent from .env.example -> HIGH drift finding."""
        source = [_py_file('x = os.getenv("MISSING_VAR")')]
        contract = _contract(env_example="DOCUMENTED_VAR=\n")
        findings = check_env_drift(source, contract)
        missing = [f for f in findings if "MISSING_VAR" in f.title]
        assert len(missing) == 1
        assert missing[0].severity == "high"
        assert missing[0].confidence == pytest.approx(0.85)
        assert missing[0].category == "drift"

    def test_undocumented_var_finding_id_prefix(self):
        source = [_py_file('x = os.getenv("UNDOC_VAR")')]
        contract = _contract(env_example="")
        findings = check_env_drift(source, contract)
        undoc = [f for f in findings if "UNDOC_VAR" in f.title]
        assert len(undoc) == 1
        assert undoc[0].id.startswith("DRF-")

    def test_unused_in_env_example_is_low_severity(self):
        """Var in .env.example but never used in code -> LOW severity."""
        source = [_py_file("x = 42")]
        contract = _contract(env_example="ORPHAN_VAR=\n")
        findings = check_env_drift(source, contract)
        orphan = [f for f in findings if "ORPHAN_VAR" in f.title]
        assert len(orphan) == 1
        assert orphan[0].severity == "low"
        assert orphan[0].confidence == pytest.approx(0.70)
        assert orphan[0].category == "drift"

    def test_documented_and_used_produces_no_finding(self):
        source = [_py_file('x = os.getenv("GOOD_VAR")')]
        contract = _contract(env_example="GOOD_VAR=\n")
        findings = check_env_drift(source, contract)
        assert not any("GOOD_VAR" in f.title for f in findings)

    def test_no_contract_files_no_findings(self):
        source = [_py_file('x = os.getenv("SOME_VAR")')]
        contract = ContractFiles()
        findings = check_env_drift(source, contract)
        assert findings == []

    def test_docker_compose_vars_count_as_documented(self):
        source = [_py_file('x = os.getenv("COMPOSE_VAR")')]
        contract = _contract(
            env_example="OTHER_VAR=\n",
            compose="version: '3'\nservices:\n  app:\n    environment:\n      - COMPOSE_VAR=x\n",
        )
        findings = check_env_drift(source, contract)
        assert not any("COMPOSE_VAR" in f.title for f in findings)

    def test_multiple_source_files_aggregated(self):
        source = [
            _py_file('x = os.getenv("VAR_A")', "a.py"),
            _js_file("const y = process.env.VAR_B;", "b.js"),
            _go_file('z := os.Getenv("VAR_C")', "main.go"),
        ]
        contract = _contract(env_example="")
        findings = check_env_drift(source, contract)
        titles = [f.title for f in findings]
        assert any("VAR_A" in t for t in titles)
        assert any("VAR_B" in t for t in titles)
        assert any("VAR_C" in t for t in titles)

    def test_evidence_contains_var_name(self):
        source = [_py_file('x = os.getenv("EVIDENCE_VAR")')]
        contract = _contract(env_example="")
        findings = check_env_drift(source, contract)
        ev = [f for f in findings if "EVIDENCE_VAR" in f.title]
        assert len(ev) == 1
        assert "EVIDENCE_VAR" in ev[0].evidence


# ---------------------------------------------------------------------------
# P1: extract_endpoints_from_readme & extract_commands_from_readme
# ---------------------------------------------------------------------------

class TestReadmeExtraction:
    def test_extract_endpoints_http_methods(self):
        readme = """
# API Documentation
- GET /api/v1/users - List users
- POST /api/v1/users - Create user
- DELETE /api/v1/users/{id} - Delete user
- PUT /settings - Update settings
- PATCH /profile - Update profile
"""
        endpoints = extract_endpoints_from_readme(readme)
        paths = [ep["path"] for ep in endpoints]
        assert "/api/v1/users" in paths
        assert "/settings" in paths
        assert "/profile" in paths

    def test_extract_endpoints_backticks(self):
        readme = "Call `GET /health` to check status."
        endpoints = extract_endpoints_from_readme(readme)
        assert any(ep["path"] == "/health" and ep["method"] == "GET" for ep in endpoints)

    def test_extract_endpoints_table(self):
        readme = """
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | /status  | Server ping |
| POST   | /login   | Auth route  |
"""
        endpoints = extract_endpoints_from_readme(readme)
        paths = [ep["path"] for ep in endpoints]
        assert "/status" in paths
        assert "/login" in paths

    def test_ignores_external_urls(self):
        readme = "Visit https://example.com/api/users for docs."
        endpoints = extract_endpoints_from_readme(readme)
        assert len(endpoints) == 0

    def test_extract_commands_code_blocks(self):
        readme = """
```bash
python -m contractguard audit <path>
python -m contractguard heal <path>
```
"""
        commands = extract_commands_from_readme(readme)
        subcmds = [c["command"] for c in commands]
        assert "audit" in subcmds or "contractguard audit" in subcmds or any("audit" in c["command"] for c in commands)

    def test_extract_commands_dollar_prompt(self):
        readme = """
Run the CLI:
```sh
$ myapp serve --port 8080
$ myapp worker
```
"""
        commands = extract_commands_from_readme(readme)
        assert any("serve" in c["command"] for c in commands)
        assert any("worker" in c["command"] for c in commands)

    def test_ignores_common_dev_tools(self):
        readme = """
```bash
git clone https://github.com/repo/app.git
cd app
pip install -r requirements.txt
npm install
pytest
```
"""
        commands = extract_commands_from_readme(readme)
        cmd_names = [c["command"].lower() for c in commands]
        # Should not flag git, pip, npm, pytest, cd as custom commands
        for cmd in cmd_names:
            assert not any(tool in cmd.split() for tool in ["git", "pip", "npm", "pytest", "cd"])


# ---------------------------------------------------------------------------
# P1: check_readme_drift (endpoints & CLI commands)
# ---------------------------------------------------------------------------

class TestCheckReadmeDrift:
    def test_missing_endpoint_produces_drift_finding(self):
        readme = """
# API
GET /api/v1/missing_endpoint
"""
        source = [_py_file('@app.get("/health")\ndef health(): return "ok"')]
        contract = _contract(readme=readme)
        findings = check_readme_drift(source, contract)
        missing = [f for f in findings if "/api/v1/missing_endpoint" in f.title or "/api/v1/missing_endpoint" in f.evidence]
        assert len(missing) == 1
        assert missing[0].category == "drift"
        assert missing[0].severity == "medium"
        assert missing[0].confidence == pytest.approx(0.80)

    def test_present_endpoint_produces_no_drift(self):
        readme = """
# API
GET /api/v1/users
"""
        source = [_py_file('@app.get("/api/v1/users")\ndef get_users(): return []')]
        contract = _contract(readme=readme)
        findings = check_readme_drift(source, contract)
        assert not any("/api/v1/users" in f.title or "/api/v1/users" in f.evidence for f in findings)

    def test_missing_cli_command_produces_drift_finding(self):
        readme = """
## Commands
```bash
myapp nonexistent-command
```
"""
        source = [_py_file('def existing_command(): pass')]
        contract = _contract(readme=readme)
        findings = check_readme_drift(source, contract)
        missing = [f for f in findings if "nonexistent-command" in f.title or "nonexistent-command" in f.evidence]
        assert len(missing) == 1
        assert missing[0].category == "drift"
        assert missing[0].severity == "medium"
        assert missing[0].confidence == pytest.approx(0.75)

    def test_present_cli_command_produces_no_drift(self):
        readme = """
## Commands
```bash
myapp audit
```
"""
        source = [_py_file('@cli.command()\ndef audit(): pass')]
        contract = _contract(readme=readme)
        findings = check_readme_drift(source, contract)
        assert not any("audit" in f.title for f in findings)

    def test_no_readme_returns_empty(self):
        source = [_py_file('x = 1')]
        contract = ContractFiles()
        assert check_readme_drift(source, contract) == []


# ---------------------------------------------------------------------------
# audit_drift (integration)
# ---------------------------------------------------------------------------

class TestAuditDriftIntegration:
    def test_returns_list_of_findings(self):
        source = [_py_file('x = os.getenv("UNDOC")')]
        contract = _contract(env_example="ORPHAN=\n", readme="GET /undocumented")
        result = audit_drift(source, contract)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, Finding)
            assert item.category == "drift"

    def test_combines_env_and_readme_drift(self):
        source = [_py_file('x = os.getenv("MY_VAR")')]
        readme = "GET /missing_route"
        contract = _contract(env_example="", readme=readme)
        result = audit_drift(source, contract)
        titles = [f.title for f in result]
        assert any("MY_VAR" in t for t in titles)
        assert any("/missing_route" in t for t in titles)

    def test_empty_contract_and_sources(self):
        result = audit_drift([], ContractFiles())
        assert result == []
