"""Repository indexer: walks the repo, classifies contract vs source files."""

import os
import re
from pathlib import Path
from typing import Optional

from contractguard.models import ContractFiles, IndexedFile


# Patterns to skip
SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "venv",
    ".venv",
    "env",
    ".env",
    "dist",
    "build",
    ".next",
    ".vercel",
    "target",
    "vendor",
    "bower_components",
    ".idea",
    ".vscode",
    ".vs",
}

SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib",
    ".class", ".jar", ".war", ".ear",
    ".exe", ".bin", ".o", ".a", ".lib",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ttf", ".woff", ".woff2", ".eot",
    ".map", ".min.js", ".min.css",
    ".lock",  # lock files handled separately
}

# Contract file patterns
CONTRACT_PATTERNS = {
    "readme": [re.compile(r"^README(\.(md|rst|txt))?$", re.IGNORECASE)],
    "env_example": [re.compile(r"^\.env(\.example|\.sample|\.template)?$", re.IGNORECASE)],
    "docker_compose": [
        re.compile(r"^docker-compose\.(yml|yaml)$", re.IGNORECASE),
        re.compile(r"^compose\.(yml|yaml)$", re.IGNORECASE),
    ],
    "github_actions": [re.compile(r"^\.github/workflows/.*\.(yml|yaml)$", re.IGNORECASE)],
    "config_files": [
        re.compile(r"^\.env(\..*)?$", re.IGNORECASE),
        re.compile(r"^config\.(yml|yaml|json|toml|ini)$", re.IGNORECASE),
        re.compile(r"^settings\.(yml|yaml|json|toml|ini)$", re.IGNORECASE),
        re.compile(r"^\.?[a-z-]+\.config\.(js|ts|json)$", re.IGNORECASE),
    ],
    "openapi_specs": [
        re.compile(r"^(openapi|swagger)\.(json|yaml|yml)$", re.IGNORECASE),
        re.compile(r"^api\.(json|yaml|yml)$", re.IGNORECASE),
    ],
}

# Language detection by extension
LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".scala": "scala",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".swift": "swift",
    ".r": "r",
    ".m": "matlab",
    ".pl": "perl",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".fish": "fish",
    ".ps1": "powershell",
    ".sql": "sql",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".vue": "vue",
    ".svelte": "svelte",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".xml": "xml",
    ".md": "markdown",
    ".rst": "rst",
    ".txt": "text",
    ".dockerfile": "dockerfile",
    "Dockerfile": "dockerfile",
    ".gitignore": "gitignore",
    ".gitattributes": "gitattributes",
}

# Source file patterns (code that can contain bugs/secrets)
SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java",
    ".kt", ".scala", ".rb", ".php", ".cs", ".cpp", ".cc", ".cxx",
    ".c", ".h", ".hpp", ".swift", ".r", ".m", ".pl", ".sh", ".bash",
    ".zsh", ".fish", ".ps1", ".sql",
}

# Max file size to read (1MB)
MAX_FILE_SIZE = 1024 * 1024


def should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped."""
    return dirname in SKIP_DIRS or dirname.startswith(".")


def should_skip_file(filename: str) -> bool:
    """Check if a file should be skipped."""
    # Skip hidden files (except known contract files)
    if filename.startswith(".") and not any(
        p.match(filename) for patterns in CONTRACT_PATTERNS.values() for p in patterns
    ):
        return True

    # Skip by extension
    ext = Path(filename).suffix.lower()
    if ext in SKIP_EXTENSIONS:
        return True

    return False


def detect_language(filepath: Path) -> Optional[str]:
    """Detect the language of a file by its extension."""
    name = filepath.name
    suffix = filepath.suffix.lower()

    # Check exact name first (e.g., Dockerfile)
    if name in LANGUAGE_EXTENSIONS:
        return LANGUAGE_EXTENSIONS[name]

    # Check extension
    return LANGUAGE_EXTENSIONS.get(suffix)


def is_contract_file(filepath: Path) -> tuple[bool, Optional[str]]:
    """Check if a file is a contract file and return its type."""
    rel_path = str(filepath)
    name = filepath.name

    for contract_type, patterns in CONTRACT_PATTERNS.items():
        for pattern in patterns:
            if pattern.match(name) or pattern.match(rel_path):
                return True, contract_type

    return False, None


def is_source_file(filepath: Path) -> bool:
    """Check if a file is a source code file."""
    ext = filepath.suffix.lower()
    return ext in SOURCE_EXTENSIONS


def read_file_safely(filepath: Path) -> Optional[str]:
    """Read a file safely with size limit and encoding handling."""
    try:
        if filepath.stat().st_size > MAX_FILE_SIZE:
            return None
        return filepath.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return None


def index_repo(repo_path: Path) -> tuple[ContractFiles, list[IndexedFile]]:
    """
    Walk the repository and classify files.

    Returns:
        Tuple of (ContractFiles, list of source IndexedFiles)
    """
    contract_files = ContractFiles()
    source_files = []

    repo_path = repo_path.resolve()

    for root, dirs, files in os.walk(repo_path):
        # Filter out skip directories
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]

        root_path = Path(root)

        for filename in files:
            if should_skip_file(filename):
                continue

            filepath = root_path / filename
            rel_path = filepath.relative_to(repo_path)
            rel_str = str(rel_path)

            content = read_file_safely(filepath)
            if content is None:
                continue

            language = detect_language(filepath)
            is_contract, contract_type = is_contract_file(filepath)
            is_src = is_source_file(filepath)

            indexed = IndexedFile(
                path=rel_str,
                is_contract=is_contract,
                is_source=is_src,
                language=language,
                content=content,
            )

            if is_contract and contract_type:
                # Add to appropriate contract file list
                if contract_type == "readme":
                    contract_files.readme = indexed
                elif contract_type == "env_example":
                    contract_files.env_example = indexed
                elif contract_type == "docker_compose":
                    contract_files.docker_compose.append(indexed)
                elif contract_type == "github_actions":
                    contract_files.github_actions.append(indexed)
                elif contract_type == "config_files":
                    contract_files.config_files.append(indexed)
                elif contract_type == "openapi_specs":
                    contract_files.openapi_specs.append(indexed)
                else:
                    contract_files.other.append(indexed)

            if is_src:
                source_files.append(indexed)

    return contract_files, source_files