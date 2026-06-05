"""
Dependency Analyzer — parse dependency manifests.

MVP support:
- Python: requirements.txt, pyproject.toml
- JavaScript/TypeScript: package.json
- Go: go.mod
- Rust: Cargo.toml
- Docker: Dockerfile
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from app.models.internal import DependencyInfo

logger = logging.getLogger(__name__)


def _parse_requirements_txt(path: Path) -> DependencyInfo:
    """Parse a requirements.txt file."""
    runtime: list[str] = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            line = line.strip()
            # Skip comments, empty lines, and options
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            # Remove inline comments
            if " #" in line:
                line = line[:line.index(" #")].strip()
            runtime.append(line)
    except OSError as e:
        logger.warning("Failed to read %s: %s", path, e)

    return DependencyInfo(
        manifest_file=path.name,
        runtime=runtime,
    )


def _parse_pyproject_toml(path: Path) -> DependencyInfo:
    """Parse a pyproject.toml file for dependencies and project metadata."""
    runtime: list[str] = []
    dev: list[str] = []
    build_tools: list[str] = []
    scripts: dict[str, str] = {}
    frameworks: list[str] = []

    try:
        # Use a simple TOML parser approach — read the file and extract key sections
        # We avoid importing tomllib to keep compat, but Python 3.11+ has it
        import tomllib
        content = path.read_bytes()
        data = tomllib.loads(content.decode("utf-8"))

        # Project dependencies
        project = data.get("project", {})
        runtime = project.get("dependencies", [])

        # Optional dependencies (often include dev deps)
        optional_deps = project.get("optional-dependencies", {})
        for group_name, deps in optional_deps.items():
            if group_name in {"dev", "test", "testing", "development", "lint"}:
                dev.extend(deps)

        # Build system
        build_sys = data.get("build-system", {})
        build_tools = build_sys.get("requires", [])

        # Scripts
        project_scripts = project.get("scripts", {})
        scripts = {k: str(v) for k, v in project_scripts.items()}

        # Framework detection from dependencies
        all_deps = " ".join(runtime).lower()
        if "fastapi" in all_deps:
            frameworks.append("FastAPI")
        if "django" in all_deps:
            frameworks.append("Django")
        if "flask" in all_deps:
            frameworks.append("Flask")
        if "starlette" in all_deps:
            frameworks.append("Starlette")

    except Exception as e:
        logger.warning("Failed to parse %s: %s", path, e)

    return DependencyInfo(
        manifest_file=path.name,
        runtime=runtime,
        dev=dev,
        build_tools=build_tools,
        scripts=scripts,
        framework_guesses=frameworks,
    )


def _parse_package_json(path: Path) -> DependencyInfo:
    """Parse a package.json file."""
    runtime: list[str] = []
    dev: list[str] = []
    scripts: dict[str, str] = {}
    frameworks: list[str] = []

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(content)

        # Dependencies
        deps = data.get("dependencies", {})
        runtime = [f"{k}@{v}" for k, v in deps.items()]

        dev_deps = data.get("devDependencies", {})
        dev = [f"{k}@{v}" for k, v in dev_deps.items()]

        # Scripts
        scripts = data.get("scripts", {})

        # Framework detection
        all_dep_names = set(deps.keys())
        if "react" in all_dep_names:
            frameworks.append("React")
        if "next" in all_dep_names:
            frameworks.append("Next.js")
        if "vue" in all_dep_names:
            frameworks.append("Vue")
        if "nuxt" in all_dep_names:
            frameworks.append("Nuxt")
        if "express" in all_dep_names:
            frameworks.append("Express")
        if "fastify" in all_dep_names:
            frameworks.append("Fastify")
        if "angular" in all_dep_names or "@angular/core" in all_dep_names:
            frameworks.append("Angular")
        if "svelte" in all_dep_names:
            frameworks.append("Svelte")

    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to parse %s: %s", path, e)

    return DependencyInfo(
        manifest_file=path.name,
        runtime=runtime,
        dev=dev,
        scripts=scripts,
        framework_guesses=frameworks,
    )


def _parse_go_mod(path: Path) -> DependencyInfo:
    """Parse a go.mod file."""
    runtime: list[str] = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        in_require = False
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("require ("):
                in_require = True
                continue
            if in_require and line == ")":
                in_require = False
                continue
            if in_require and line:
                # Lines like: github.com/gin-gonic/gin v1.9.1
                parts = line.split()
                if len(parts) >= 2 and not parts[0].startswith("//"):
                    runtime.append(f"{parts[0]} {parts[1]}")
            elif line.startswith("require "):
                # Single-line require
                parts = line.split()
                if len(parts) >= 3:
                    runtime.append(f"{parts[1]} {parts[2]}")
    except OSError as e:
        logger.warning("Failed to read %s: %s", path, e)

    frameworks: list[str] = []
    dep_str = " ".join(runtime).lower()
    if "gin-gonic" in dep_str:
        frameworks.append("Gin")
    if "gorilla/mux" in dep_str:
        frameworks.append("Gorilla")
    if "echo" in dep_str:
        frameworks.append("Echo")

    return DependencyInfo(
        manifest_file=path.name,
        runtime=runtime,
        framework_guesses=frameworks,
    )


def _parse_cargo_toml(path: Path) -> DependencyInfo:
    """Parse a Cargo.toml file."""
    runtime: list[str] = []
    dev: list[str] = []

    try:
        import tomllib
        content = path.read_bytes()
        data = tomllib.loads(content.decode("utf-8"))

        # [dependencies]
        deps = data.get("dependencies", {})
        for name, spec in deps.items():
            if isinstance(spec, str):
                runtime.append(f"{name} = {spec}")
            elif isinstance(spec, dict):
                version = spec.get("version", "*")
                runtime.append(f"{name} = {version}")

        # [dev-dependencies]
        dev_deps = data.get("dev-dependencies", {})
        for name, spec in dev_deps.items():
            if isinstance(spec, str):
                dev.append(f"{name} = {spec}")
            elif isinstance(spec, dict):
                version = spec.get("version", "*")
                dev.append(f"{name} = {version}")

    except Exception as e:
        logger.warning("Failed to parse %s: %s", path, e)

    frameworks: list[str] = []
    dep_names = " ".join(runtime).lower()
    if "actix" in dep_names:
        frameworks.append("Actix")
    if "axum" in dep_names:
        frameworks.append("Axum")
    if "rocket" in dep_names:
        frameworks.append("Rocket")
    if "tokio" in dep_names:
        frameworks.append("Tokio")

    return DependencyInfo(
        manifest_file=path.name,
        runtime=runtime,
        dev=dev,
        framework_guesses=frameworks,
    )


def _parse_dockerfile(path: Path) -> DependencyInfo:
    """Extract base image and key info from a Dockerfile."""
    build_tools: list[str] = []
    frameworks: list[str] = []

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            line = line.strip()
            if line.upper().startswith("FROM "):
                image = line.split()[1] if len(line.split()) > 1 else ""
                build_tools.append(f"base:{image}")
    except OSError as e:
        logger.warning("Failed to read %s: %s", path, e)

    return DependencyInfo(
        manifest_file=path.name,
        build_tools=build_tools,
        framework_guesses=frameworks,
    )


# ─── Manifest discovery ─────────────────────────────────────────────────────

_MANIFEST_PARSERS: dict[str, callable] = {
    "requirements.txt": _parse_requirements_txt,
    "pyproject.toml": _parse_pyproject_toml,
    "package.json": _parse_package_json,
    "go.mod": _parse_go_mod,
    "Cargo.toml": _parse_cargo_toml,
    "Dockerfile": _parse_dockerfile,
}


def analyze_dependencies(project_root: Path) -> list[DependencyInfo]:
    """
    Scan for dependency manifests and extract dependency information.

    Looks in the project root (and one level of subdirectories for monorepos)
    for known manifest files and parses them.

    Args:
        project_root: Root directory of the project.

    Returns:
        A list of DependencyInfo objects, one per manifest found.
    """
    results: list[DependencyInfo] = []

    # Scan root directory
    for manifest_name, parser in _MANIFEST_PARSERS.items():
        manifest_path = project_root / manifest_name
        if manifest_path.is_file():
            logger.info("Found manifest: %s", manifest_path)
            info = parser(manifest_path)
            results.append(info)

    # Also check for requirements*.txt variants (requirements-dev.txt, etc.)
    for req_file in project_root.glob("requirements*.txt"):
        if req_file.name != "requirements.txt":  # Already handled above
            logger.info("Found manifest: %s", req_file)
            results.append(_parse_requirements_txt(req_file))

    # Check for docker-compose variants
    for dc_name in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
        dc_path = project_root / dc_name
        if dc_path.is_file() and dc_name != "Dockerfile":
            results.append(DependencyInfo(
                manifest_file=dc_name,
                build_tools=[f"docker-compose:{dc_name}"],
            ))

    logger.info("Found %d dependency manifests", len(results))
    return results
