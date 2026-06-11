"""
File Classifier — assign category, language, and processing strategy to each file.

Categories: source, test, documentation, configuration,
            dependency_manifest, build_deploy, data, binary, generated.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.models.internal import FileRecord

logger = logging.getLogger(__name__)

# ─── Language detection by extension ──────────────────────────────────────────

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    # Python
    ".py": "python", ".pyw": "python", ".pyi": "python",
    # JavaScript / TypeScript
    ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".mjs": "javascript", ".cjs": "javascript",
    # Web
    ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "scss", ".sass": "sass", ".less": "less",
    # Data / Config
    ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".ini": "ini", ".cfg": "ini",
    ".xml": "xml", ".xsl": "xml",
    ".env": "dotenv",
    # Shell
    ".sh": "bash", ".bash": "bash", ".zsh": "zsh",
    ".ps1": "powershell", ".psm1": "powershell",
    ".bat": "batch", ".cmd": "batch",
    # Go
    ".go": "go",
    # Rust
    ".rs": "rust",
    # Java / Kotlin
    ".java": "java", ".kt": "kotlin", ".kts": "kotlin",
    # C / C++
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cxx": "cpp", ".cc": "cpp",
    ".hpp": "cpp", ".hxx": "cpp", ".hh": "cpp",
    # C#
    ".cs": "csharp", ".csx": "csharp",
    # Ruby
    ".rb": "ruby", ".rake": "ruby", ".gemspec": "ruby",
    # PHP
    ".php": "php",
    # Swift
    ".swift": "swift",
    # Dart
    ".dart": "dart",
    # Lua
    ".lua": "lua",
    # R
    ".r": "r", ".R": "r",
    # SQL
    ".sql": "sql",
    # Markdown / Docs
    ".md": "markdown", ".mdx": "mdx", ".rst": "restructuredtext",
    ".txt": "text", ".text": "text",
    # Docker
    ".dockerfile": "dockerfile",
    # Protobuf
    ".proto": "protobuf",
    # GraphQL
    ".graphql": "graphql", ".gql": "graphql",
}

# Files identified by exact name
FILENAME_TO_LANGUAGE: dict[str, str] = {
    "Dockerfile": "dockerfile",
    "Makefile": "makefile",
    "Rakefile": "ruby",
    "Gemfile": "ruby",
    "Vagrantfile": "ruby",
    "Jenkinsfile": "groovy",
    "Procfile": "text",
    ".gitignore": "gitignore",
    ".dockerignore": "gitignore",
    ".editorconfig": "ini",
}

# ─── Category detection ──────────────────────────────────────────────────────

TEST_INDICATORS: set[str] = {
    "test", "tests", "spec", "specs",
    "__tests__", "__test__",
    "test_", "_test", ".test.", ".spec.",
}

DOCUMENTATION_EXTENSIONS: set[str] = {
    ".md", ".mdx", ".rst", ".txt", ".adoc", ".asciidoc",
}

DOCUMENTATION_NAMES: set[str] = {
    "readme", "changelog", "changes", "history",
    "contributing", "contributors", "authors",
    "license", "licence", "notice", "code_of_conduct",
    "architecture", "design", "todo", "roadmap",
    "security", "support", "funding",
}

CONFIG_EXTENSIONS: set[str] = {
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".env", ".properties",
}

CONFIG_NAMES: set[str] = {
    ".gitignore", ".gitattributes", ".editorconfig",
    ".prettierrc", ".eslintrc", ".babelrc",
    ".flake8", ".pylintrc", "mypy.ini", "setup.cfg",
    "tsconfig.json", "jsconfig.json", ".browserslistrc",
    "jest.config.js", "jest.config.ts", "vitest.config.ts",
    "webpack.config.js", "vite.config.ts", "vite.config.js",
    "next.config.js", "next.config.mjs", "nuxt.config.ts",
    "tailwind.config.js", "tailwind.config.ts",
    "postcss.config.js", ".postcssrc",
    "tox.ini", "pytest.ini", "pyproject.toml",
    "ruff.toml", ".ruff.toml",
}

DEPENDENCY_MANIFEST_NAMES: set[str] = {
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg",
    "Pipfile", "Pipfile.lock", "poetry.lock",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "go.mod", "go.sum",
    "Cargo.toml", "Cargo.lock",
    "pom.xml", "build.gradle", "build.gradle.kts",
    "settings.gradle", "settings.gradle.kts",
    "Gemfile", "Gemfile.lock",
    "composer.json", "composer.lock",
    "pubspec.yaml", "pubspec.lock",
    ".csproj", ".sln", ".fsproj", ".vbproj",
}

BUILD_DEPLOY_NAMES: set[str] = {
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "Makefile", "Rakefile", "Justfile", "Taskfile.yml",
    "Procfile", "Jenkinsfile", "Vagrantfile",
    ".travis.yml", ".circleci", "azure-pipelines.yml",
    "cloudbuild.yaml", "appveyor.yml",
    "vercel.json", "netlify.toml", "fly.toml",
    "render.yaml", "railway.json",
    "serverless.yml", "serverless.yaml",
    "sam.yaml", "template.yaml",
    "skaffold.yaml", "helmfile.yaml",
}

BUILD_DEPLOY_DIRS: set[str] = {
    ".github", ".circleci", ".gitlab",
}

DATA_EXTENSIONS: set[str] = {
    ".csv", ".tsv", ".jsonl", ".ndjson",
    ".parquet", ".avro", ".feather",
}

GENERATED_NAMES: set[str] = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Pipfile.lock", "poetry.lock", "Cargo.lock",
    "go.sum", "composer.lock", "Gemfile.lock", "pubspec.lock",
}


def _detect_language(path: Path) -> str | None:
    """Detect programming language from filename or extension."""
    name = path.name
    if name in FILENAME_TO_LANGUAGE:
        return FILENAME_TO_LANGUAGE[name]
    return EXTENSION_TO_LANGUAGE.get(path.suffix.lower())


def _detect_category(path: Path, project_root: Path) -> str:
    """Detect file category based on name, path, and extension."""
    name = path.name
    name_lower = name.lower()
    stem_lower = path.stem.lower()
    suffix_lower = path.suffix.lower()

    try:
        rel_parts = path.resolve().relative_to(project_root.resolve()).parts
    except ValueError:
        rel_parts = ()

    # Generated / lock files
    if name in GENERATED_NAMES:
        return "generated"

    # Dependency manifests
    if name in DEPENDENCY_MANIFEST_NAMES or suffix_lower in {".csproj", ".sln", ".fsproj", ".vbproj"}:
        return "dependency_manifest"

    # Build / deploy files
    if name in BUILD_DEPLOY_NAMES:
        return "build_deploy"
    for part in rel_parts:
        if part in BUILD_DEPLOY_DIRS:
            return "build_deploy"

    # Tests — check path parts and filename patterns
    for part in rel_parts:
        if part.lower() in TEST_INDICATORS:
            return "test"
    if any(indicator in name_lower for indicator in {"test_", "_test.", ".test.", ".spec.", "spec_", "_spec."}):
        return "test"
    if name_lower.startswith("test_") or name_lower.endswith("_test.py"):
        return "test"

    # Documentation
    if stem_lower in DOCUMENTATION_NAMES:
        return "documentation"
    if suffix_lower in DOCUMENTATION_EXTENSIONS:
        # Files in a docs/ directory are documentation
        for part in rel_parts:
            if part.lower() in {"docs", "doc", "documentation"}:
                return "documentation"
        # Top-level markdown files are often documentation
        if len(rel_parts) <= 2 and suffix_lower == ".md":
            return "documentation"

    # Config files
    if name in CONFIG_NAMES or name_lower.startswith("."):
        if suffix_lower in CONFIG_EXTENSIONS or name_lower in CONFIG_NAMES:
            return "configuration"

    # Data files
    if suffix_lower in DATA_EXTENSIONS:
        return "data"

    # Default: source code
    return "source"


def classify_file(path: Path, project_root: Path) -> FileRecord:
    """
    Classify a single file and return a FileRecord.

    Args:
        path: Absolute path to the file.
        project_root: Root directory of the project.

    Returns:
        A FileRecord with category, language, size, and status populated.
    """
    try:
        rel_path = path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        rel_path = path.name

    try:
        size = path.stat().st_size
    except OSError:
        size = 0

    language = _detect_language(path)
    category = _detect_category(path, project_root)

    logger.debug(
        "Classified file: %s -> language=%s, category=%s, size=%d bytes",
        rel_path,
        language,
        category,
        size,
    )

    return FileRecord(
        path=rel_path,
        absolute_path=str(path.resolve()),
        language=language,
        category=category,
        size_bytes=size,
        status="included",
        is_binary=False,  # Already filtered by ignore engine
        is_generated=category == "generated",
    )


def classify_skipped_file(path: Path, project_root: Path, reason: str) -> FileRecord:
    """Create a FileRecord for a skipped file."""
    try:
        rel_path = path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        rel_path = path.name

    try:
        size = path.stat().st_size
    except OSError:
        size = 0

    record = FileRecord(
        path=rel_path,
        absolute_path=str(path.resolve()),
        language=_detect_language(path),
        category="binary" if "binary" in reason else "generated" if "generated" in reason else "source",
        size_bytes=size,
        status="skipped",
        skip_reason=reason,
        is_binary="binary" in reason,
        is_generated="generated" in reason,
    )
    logger.debug(
        "Classified skipped file: %s -> reason=%s, category=%s",
        rel_path,
        reason,
        record.category,
    )
    return record
