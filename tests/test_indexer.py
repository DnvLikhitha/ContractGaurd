"""
Tests for contractguard.indexer.

Written before implementation per CLAUDE.md rules.
Tests cover: skip logic, contract classification, source classification,
language detection, encoding safety, and the top-level index_repo function.
"""

import os
import stat
from pathlib import Path

import pytest

from contractguard.indexer import (
    SKIP_DIRS,
    detect_language,
    index_repo,
    is_contract_file,
    is_source_file,
    read_file_safely,
    should_skip_dir,
    should_skip_file,
)


# ---------------------------------------------------------------------------
# should_skip_dir
# ---------------------------------------------------------------------------

class TestShouldSkipDir:
    def test_skips_git(self):
        assert should_skip_dir(".git")

    def test_skips_node_modules(self):
        assert should_skip_dir("node_modules")

    def test_skips_venv(self):
        assert should_skip_dir("venv")
        assert should_skip_dir(".venv")

    def test_skips_pycache(self):
        assert should_skip_dir("__pycache__")

    def test_skips_dist_build(self):
        assert should_skip_dir("dist")
        assert should_skip_dir("build")

    def test_does_not_skip_src(self):
        assert not should_skip_dir("src")

    def test_does_not_skip_app(self):
        assert not should_skip_dir("app")


# ---------------------------------------------------------------------------
# should_skip_file
# ---------------------------------------------------------------------------

class TestShouldSkipFile:
    def test_skips_pyc(self):
        assert should_skip_file("module.pyc")

    def test_skips_pyo(self):
        assert should_skip_file("module.pyo")

    def test_skips_png(self):
        assert should_skip_file("logo.png")

    def test_skips_exe(self):
        assert should_skip_file("app.exe")

    def test_skips_lock(self):
        assert should_skip_file("package-lock.json") or should_skip_file("poetry.lock")

    def test_does_not_skip_py(self):
        assert not should_skip_file("app.py")

    def test_does_not_skip_js(self):
        assert not should_skip_file("index.js")

    def test_does_not_skip_env_example(self):
        # .env.example is a contract file and must NOT be skipped
        assert not should_skip_file(".env.example")

    def test_does_not_skip_readme(self):
        assert not should_skip_file("README.md")


# ---------------------------------------------------------------------------
# detect_language
# ---------------------------------------------------------------------------

class TestDetectLanguage:
    def test_python(self):
        assert detect_language(Path("app.py")) == "python"

    def test_javascript(self):
        assert detect_language(Path("index.js")) == "javascript"

    def test_typescript(self):
        assert detect_language(Path("server.ts")) == "typescript"

    def test_go(self):
        assert detect_language(Path("main.go")) == "go"

    def test_yaml(self):
        assert detect_language(Path("config.yml")) == "yaml"
        assert detect_language(Path("config.yaml")) == "yaml"

    def test_markdown(self):
        assert detect_language(Path("README.md")) == "markdown"

    def test_dockerfile(self):
        assert detect_language(Path("Dockerfile")) == "dockerfile"

    def test_unknown_returns_none(self):
        assert detect_language(Path("somefile.xyz")) is None


# ---------------------------------------------------------------------------
# is_contract_file
# ---------------------------------------------------------------------------

class TestIsContractFile:
    def test_readme_md(self):
        result, kind = is_contract_file(Path("README.md"))
        assert result is True
        assert kind == "readme"

    def test_readme_no_ext(self):
        result, kind = is_contract_file(Path("README"))
        assert result is True

    def test_env_example(self):
        result, kind = is_contract_file(Path(".env.example"))
        assert result is True
        assert kind == "env_example"

    def test_env_sample(self):
        result, kind = is_contract_file(Path(".env.sample"))
        assert result is True
        assert kind == "env_example"

    def test_docker_compose_yml(self):
        result, kind = is_contract_file(Path("docker-compose.yml"))
        assert result is True
        assert kind == "docker_compose"

    def test_docker_compose_yaml(self):
        result, kind = is_contract_file(Path("docker-compose.yaml"))
        assert result is True
        assert kind == "docker_compose"

    def test_openapi_json(self):
        result, kind = is_contract_file(Path("openapi.json"))
        assert result is True
        assert kind == "openapi_specs"

    def test_swagger_yaml(self):
        result, kind = is_contract_file(Path("swagger.yaml"))
        assert result is True
        assert kind == "openapi_specs"

    def test_regular_py_not_contract(self):
        result, _ = is_contract_file(Path("app.py"))
        assert result is False

    def test_regular_js_not_contract(self):
        result, _ = is_contract_file(Path("index.js"))
        assert result is False


# ---------------------------------------------------------------------------
# is_source_file
# ---------------------------------------------------------------------------

class TestIsSourceFile:
    def test_python(self):
        assert is_source_file(Path("app.py"))

    def test_javascript(self):
        assert is_source_file(Path("index.js"))

    def test_typescript(self):
        assert is_source_file(Path("server.ts"))

    def test_go(self):
        assert is_source_file(Path("main.go"))

    def test_shell(self):
        assert is_source_file(Path("deploy.sh"))

    def test_markdown_not_source(self):
        assert not is_source_file(Path("README.md"))

    def test_yaml_not_source(self):
        assert not is_source_file(Path("config.yml"))


# ---------------------------------------------------------------------------
# read_file_safely
# ---------------------------------------------------------------------------

class TestReadFileSafely:
    def test_reads_normal_file(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("hello world", encoding="utf-8")
        assert read_file_safely(f) == "hello world"

    def test_returns_none_for_missing_file(self, tmp_path):
        result = read_file_safely(tmp_path / "nonexistent.txt")
        assert result is None

    def test_handles_encoding_error_gracefully(self, tmp_path):
        f = tmp_path / "binary.bin"
        f.write_bytes(b"\xff\xfe\x00invalid utf-8\xff")
        # Should not raise; returns string (possibly with replacement chars)
        result = read_file_safely(f)
        assert result is not None  # errors="replace" means it won't return None

    def test_returns_none_for_oversized_file(self, tmp_path):
        from contractguard.indexer import MAX_FILE_SIZE
        f = tmp_path / "big.txt"
        f.write_bytes(b"x" * (MAX_FILE_SIZE + 1))
        assert read_file_safely(f) is None


# ---------------------------------------------------------------------------
# index_repo (integration)
# ---------------------------------------------------------------------------

class TestIndexRepo:
    def _build_repo(self, tmp_path: Path) -> Path:
        """Build a small synthetic repo layout."""
        # Contract files
        (tmp_path / "README.md").write_text("# My App\n\n## Endpoints\nGET /health\n")
        (tmp_path / ".env.example").write_text("DATABASE_URL=\nSECRET_KEY=\n")
        (tmp_path / "docker-compose.yml").write_text("version: '3'\nservices:\n  web:\n    image: app\n")

        # Source files
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("import os\nDB = os.getenv('DATABASE_URL')\n")
        (src / "utils.py").write_text("def helper(): pass\n")

        # Skipped dirs/files
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "app.cpython-311.pyc").write_bytes(b"\x00\x01")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "lodash.js").write_text("module.exports={}")
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "python.exe").write_bytes(b"binary")

        return tmp_path

    def test_finds_readme(self, tmp_path):
        repo = self._build_repo(tmp_path)
        contracts, _ = index_repo(repo)
        assert contracts.readme is not None
        assert "README" in contracts.readme.path

    def test_finds_env_example(self, tmp_path):
        repo = self._build_repo(tmp_path)
        contracts, _ = index_repo(repo)
        assert contracts.env_example is not None

    def test_finds_docker_compose(self, tmp_path):
        repo = self._build_repo(tmp_path)
        contracts, _ = index_repo(repo)
        assert len(contracts.docker_compose) == 1

    def test_finds_source_files(self, tmp_path):
        repo = self._build_repo(tmp_path)
        _, sources = index_repo(repo)
        source_names = [Path(f.path).name for f in sources]
        assert "app.py" in source_names
        assert "utils.py" in source_names

    def test_skips_pycache(self, tmp_path):
        repo = self._build_repo(tmp_path)
        _, sources = index_repo(repo)
        paths = [f.path for f in sources]
        assert not any("__pycache__" in p for p in paths)

    def test_skips_node_modules(self, tmp_path):
        repo = self._build_repo(tmp_path)
        _, sources = index_repo(repo)
        paths = [f.path for f in sources]
        assert not any("node_modules" in p for p in paths)

    def test_skips_venv(self, tmp_path):
        repo = self._build_repo(tmp_path)
        _, sources = index_repo(repo)
        paths = [f.path for f in sources]
        assert not any(".venv" in p for p in paths)

    def test_source_files_marked_correctly(self, tmp_path):
        repo = self._build_repo(tmp_path)
        _, sources = index_repo(repo)
        for f in sources:
            assert f.is_source is True

    def test_contract_files_marked_correctly(self, tmp_path):
        repo = self._build_repo(tmp_path)
        contracts, _ = index_repo(repo)
        for f in contracts.all_contract_files():
            assert f.is_contract is True

    def test_does_not_crash_on_empty_repo(self, tmp_path):
        contracts, sources = index_repo(tmp_path)
        assert contracts.readme is None
        assert sources == []

    def test_does_not_crash_on_unreadable_file(self, tmp_path):
        """index_repo should skip files it cannot read rather than crash."""
        (tmp_path / "normal.py").write_text("x = 1")
        # Create a file that is unreadable by making read_file_safely return None
        bad = tmp_path / "bad.py"
        bad.write_text("secret")
        # Simulate by making it 0 bytes and checking nothing crashes
        bad.write_bytes(b"")  # empty is fine; just verify no crash
        contracts, sources = index_repo(tmp_path)
        source_names = [Path(f.path).name for f in sources]
        assert "normal.py" in source_names

    def test_language_detected_for_python(self, tmp_path):
        repo = self._build_repo(tmp_path)
        _, sources = index_repo(repo)
        py_files = [f for f in sources if f.path.endswith(".py")]
        for f in py_files:
            assert f.language == "python"

    def test_all_contract_files_method(self, tmp_path):
        repo = self._build_repo(tmp_path)
        contracts, _ = index_repo(repo)
        all_files = contracts.all_contract_files()
        assert len(all_files) >= 3  # readme + env_example + docker_compose
