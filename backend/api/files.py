import io
import os
import shutil
import zipfile
from pathlib import Path
from backend.db.models import Session
from backend.db.database import getDb
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/api/v1/files", tags=["files"])

SANDBOX_ROOT = Path(os.environ.get("HOME", "/home/computeruse"))


async def getWorkspace(
    session_id: str | None,
    db: AsyncSession | None = None,
) -> Path:
    """Return the session user's home directory, or raise HTTP 400 if no session_id."""
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    if db:
        session = await db.get(Session, session_id)
        if session and session.home_dir:
            home = Path(session.home_dir)
            if home.is_dir():
                return home
    workspace = SANDBOX_ROOT / "workspaces" / session_id
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def resolveSafe(path_str: str, root: Path) -> Path:
    """Resolve a relative path within the given root, rejecting escapes."""
    resolved = (root / path_str).resolve()
    if not str(resolved).startswith(str(root.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")
    return resolved


@router.get("")
async def listDirectory(
    path: str = Query(".", description="Relative path within workspace"),
    session_id: str = Query(None, description="Session ID for workspace scoping"),
    db: AsyncSession = Depends(getDb),
):
    """List directory contents scoped to a session workspace."""
    root = await getWorkspace(session_id, db)
    target = resolveSafe(path, root)
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")
    entries = []
    try:
        for entry in sorted(target.iterdir()):
            if entry.name.startswith("."):
                continue
            try:
                stat = entry.stat()
                entries.append(
                    {
                        "name": entry.name,
                        "type": "dir" if entry.is_dir() else "file",
                        "size": stat.st_size if entry.is_file() else None,
                        "modified": stat.st_mtime,
                    }
                )
            except OSError:
                continue
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    return {"path": str(target.relative_to(root)), "entries": entries}


@router.get("/content")
async def readFile(
    path: str = Query(..., description="Relative path to file"),
    session_id: str = Query(None, description="Session ID for workspace scoping"),
    db: AsyncSession = Depends(getDb),
):
    """Read file content (text files up to 1 MB)."""
    root = await getWorkspace(session_id, db)
    target = resolveSafe(path, root)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if target.stat().st_size > 1_000_000:
        raise HTTPException(status_code=413, detail="File too large (>1 MB)")
    try:
        return {
            "path": str(target.relative_to(root)),
            "content": target.read_text(errors="replace"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def uploadFiles(
    files: List[UploadFile] = File(...),
    paths: List[str] = Form(default=[]),
    session_id: str = Query(None, description="Session ID for workspace scoping"),
    db: AsyncSession = Depends(getDb),
):
    """Upload one or more files to the session workspace, optionally preserving folder structure."""
    root = await getWorkspace(session_id, db)
    results = []
    for i, file in enumerate(files):
        if not file.filename:
            continue
        rel = paths[i] if i < len(paths) and paths[i] else None
        if rel:
            dest = resolveSafe(rel, root)
        else:
            dest = root / Path(file.filename).name
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(dest, "wb") as f:
                shutil.copyfileobj(file.file, f)
            results.append({"path": str(dest.relative_to(root)), "size": dest.stat().st_size})
        except Exception as e:
            results.append({"path": file.filename, "error": str(e)})
    return {"uploaded": results}


@router.delete("")
async def deleteItem(
    path: str = Query(..., description="Relative path to file or folder"),
    session_id: str = Query(None, description="Session ID for workspace scoping"),
    db: AsyncSession = Depends(getDb),
):
    """Delete a file or folder within the session workspace."""
    root = await getWorkspace(session_id, db)
    target = resolveSafe(path, root)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")
    if target == root:
        raise HTTPException(status_code=403, detail="Cannot delete workspace root")
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"deleted": str(target.relative_to(root))}


@router.get("/download")
async def downloadItem(
    path: str = Query(..., description="Relative path to file or folder"),
    session_id: str = Query(None, description="Session ID for workspace scoping"),
    db: AsyncSession = Depends(getDb),
):
    """Download a file directly or a folder as a zip archive."""
    root = await getWorkspace(session_id, db)
    target = resolveSafe(path, root)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")

    if target.is_file():
        def iterfile():
            with open(target, "rb") as f:
                yield from iter(lambda: f.read(65536), b"")
        return StreamingResponse(
            iterfile(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{target.name}"'},
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in target.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(target))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{target.name}.zip"'},
    )
