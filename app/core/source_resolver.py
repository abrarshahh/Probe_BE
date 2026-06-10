"""
Source Resolver — convert user input into a local workspace path.

Handles:
- Local directory paths (from extracted uploads).
- GitHub repository URLs (shallow clone via subprocess git).
- Branch, tag, and commit selection.
- Private repos via GitHub PAT.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Matches GitHub URLs in common formats
_GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


async def resolve_github(
    url: str,
    workspace_path: Path,
    branch: str = "main",
    github_token: str | None = None,
) -> Path:
    """
    Clone a GitHub repository into the workspace via shallow clone.

    Args:
        url: GitHub repository URL.
        workspace_path: Directory to clone into.
        branch: Branch, tag, or commit to checkout.
        github_token: PAT for private repos (injected into clone URL).

    Returns:
        Path to the cloned project root.

    Raises:
        ValueError: If the URL doesn't look like a GitHub repo.
        RuntimeError: If git clone fails.
    """
    match = _GITHUB_URL_RE.match(url.strip())
    if not match:
        raise ValueError(
            f"Invalid GitHub URL: {url}. "
            "Expected format: https://github.com/owner/repo"
        )

    owner = match.group("owner")
    repo = match.group("repo")

    # Build the clone URL — inject token for private repos
    if github_token:
        clone_url = f"https://{github_token}@github.com/{owner}/{repo}.git"
    else:
        clone_url = f"https://github.com/{owner}/{repo}.git"

    clone_dir = workspace_path / repo

    cmd = [
        "git", "clone",
        "--depth", "1",
        "--branch", branch,
        "--single-branch",
        clone_url,
        str(clone_dir),
    ]

    logger.info("Cloning %s/%s (branch=%s) into %s", owner, repo, branch, clone_dir)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode().strip()
        # Redact token from error messages
        if github_token:
            error_msg = error_msg.replace(github_token, "[REDACTED]")
        raise RuntimeError(f"Git clone failed (exit {process.returncode}): {error_msg}")

    logger.info("Clone complete: %s", clone_dir)
    return clone_dir


async def resolve_upload(
    zip_path: Path,
    workspace_path: Path,
) -> Path:
    """
    Extract an uploaded ZIP archive into the workspace.

    Args:
        zip_path: Path to the uploaded .zip file.
        workspace_path: Directory to extract into.

    Returns:
        Path to the extracted project root.

    Raises:
        ValueError: If the file is not a valid ZIP archive.
    """
    if not zipfile.is_zipfile(zip_path):
        raise ValueError(f"Not a valid ZIP archive: {zip_path}")

    extract_dir = workspace_path / "project"

    # Run extraction in a thread to avoid blocking the event loop
    def _extract() -> None:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Security: check for path traversal
            for member in zf.namelist():
                member_path = (extract_dir / member).resolve()
                if not str(member_path).startswith(str(extract_dir.resolve())):
                    raise ValueError(f"Zip path traversal detected: {member}")
            zf.extractall(extract_dir)

    await asyncio.to_thread(_extract)

    # If the zip contained a single top-level directory, use that as root
    children = list(extract_dir.iterdir())
    if len(children) == 1 and children[0].is_dir():
        return children[0]

    return extract_dir


async def resolve_local(local_path: Path) -> Path:
    """
    Validate and return a local directory path.

    Args:
        local_path: Path to an existing local project directory.

    Returns:
        The validated path.

    Raises:
        ValueError: If the path doesn't exist or isn't a directory.
    """
    resolved = local_path.resolve()
    if not resolved.exists():
        raise ValueError(f"Path does not exist: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"Path is not a directory: {resolved}")
    return resolved


async def resolve_source(
    source_type: str,
    workspace_path: Path,
    url: str | None = None,
    branch: str = "main",
    github_token: str | None = None,
    upload_path: Path | None = None,
) -> Path:
    """
    Resolve the project source into a local directory path.

    Args:
        source_type: "github_url" or "upload".
        workspace_path: Pre-created workspace directory.
        url: GitHub repo URL (required for github_url).
        branch: Branch/tag/commit to checkout.
        github_token: PAT for private repos.
        upload_path: Path to uploaded zip (required for upload).

    Returns:
        Path to the local project root.
    """
    if source_type == "github_url":
        if not url:
            raise ValueError("GitHub URL is required for source_type='github_url'")
        return await resolve_github(url, workspace_path, branch, github_token)

    elif source_type == "upload":
        if not upload_path:
            raise ValueError("Upload path is required for source_type='upload'")
        return await resolve_upload(upload_path, workspace_path)

    elif source_type == "local":
        if not url:
            raise ValueError("Local path (in url field) is required for source_type='local'")
        return Path(url)

    else:
        raise ValueError(f"Unknown source_type: {source_type}")
