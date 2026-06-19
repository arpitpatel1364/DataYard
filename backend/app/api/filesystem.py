"""
FILESYSTEM BROWSE API

Provides a safe, auth-gated server-side directory browser so the frontend
can navigate the server filesystem without relying on the OS file manager.
Only directories are returned (not files) to keep the surface minimal and
suited for dataset-path selection.
"""
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.rbac import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/fs", tags=["Filesystem"])

# Disallow browsing outside these safe roots to prevent path traversal.
# If empty, any absolute path is allowed (fine for a self-hosted internal tool).
_SAFE_ROOTS: list[Path] = []


def _is_safe(path: Path) -> bool:
    if not _SAFE_ROOTS:
        return True
    return any(path == r or r in path.parents for r in _SAFE_ROOTS)


@router.get("/browse")
def browse_directory(
    path: Optional[str] = Query(None, description="Absolute path to list. Defaults to filesystem roots."),
    user: User = Depends(get_current_user),
):
    """
    List the immediate children of *path* that are directories.
    Returns:
      - current  : the resolved path that was listed
      - parent   : parent path (null at fs root)
      - dirs     : list of {name, path, accessible} objects
    """
    # Determine starting path
    if path:
        target = Path(path).resolve()
    else:
        # Default: list filesystem roots
        # On Linux, just start at /
        target = Path("/")

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {target}")

    if not target.is_dir():
        # If a file was given, go up to its parent
        target = target.parent

    if not _is_safe(target):
        raise HTTPException(status_code=403, detail="Access outside allowed roots is not permitted.")

    # Build listing
    dirs = []
    try:
        entries = sorted(target.iterdir(), key=lambda p: p.name.lower())
        for entry in entries:
            if not entry.is_dir():
                continue
            # Check if we can read it
            accessible = os.access(entry, os.R_OK | os.X_OK)
            dirs.append({
                "name": entry.name,
                "path": str(entry),
                "accessible": accessible,
            })
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {target}")

    parent = str(target.parent) if target != target.parent else None

    return {
        "current": str(target),
        "parent": parent,
        "dirs": dirs,
    }
