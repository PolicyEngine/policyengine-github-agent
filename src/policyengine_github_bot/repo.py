"""Repository cloning and checkout utilities."""

import subprocess
import tempfile
from pathlib import Path

import logfire


async def clone_repo(
    repo_url: str,
    target_dir: Path | str,
    ref: str | None = None,
    depth: int = 20,
    token: str | None = None,
) -> Path:
    """Clone a repository with shallow history.

    Args:
        repo_url: HTTPS URL of the repository (e.g. https://github.com/org/repo)
        target_dir: Directory to clone into
        ref: Branch, tag, or commit to checkout (optional)
        depth: Number of commits to fetch (default 20 for speed)
        token: GitHub token for private repos (optional)

    Returns:
        Path to the cloned repository
    """
    target = Path(target_dir)
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    repo_path = target / repo_name

    # Insert token into URL for auth if provided
    if token and repo_url.startswith("https://"):
        repo_url = repo_url.replace("https://", f"https://x-access-token:{token}@")

    # Clone with shallow depth
    cmd = ["git", "clone", "--depth", str(depth)]
    if ref:
        cmd.extend(["--branch", ref])
    cmd.extend([repo_url, str(repo_path)])

    logfire.info(f"[repo] Cloning {repo_name} (depth={depth})")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logfire.error(f"[repo] Clone failed: {result.stderr}")
        raise RuntimeError(f"Failed to clone repository: {result.stderr}")

    logfire.info(f"[repo] Cloned to {repo_path}")
    return repo_path


def get_temp_repo_dir() -> tempfile.TemporaryDirectory:
    """Create a temporary directory for repo operations.

    Returns a context manager that cleans up on exit.
    """
    return tempfile.TemporaryDirectory(prefix="policyengine-bot-")
