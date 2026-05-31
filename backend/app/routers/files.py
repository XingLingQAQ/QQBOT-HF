"""File manager scoped strictly to ``/data`` (DATA_DIR).

Every path is resolved through :func:`utils.safe_join`, which rejects traversal
and symlink escapes, so no request can touch the filesystem outside ``/data``.
"""

import os
import shutil
from typing import List

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import auth, config, utils

router = APIRouter(
    prefix="/files", tags=["files"], dependencies=[Depends(auth.require_auth)]
)


class WriteBody(BaseModel):
    path: str
    content: str


class PathBody(BaseModel):
    path: str


class RenameBody(BaseModel):
    src: str
    dst: str


@router.get("/list")
def list_dir(path: str = ""):
    target = utils.safe_join(config.DATA_DIR, path)
    if not os.path.isdir(target):
        raise HTTPException(status_code=404, detail="directory not found")
    items = []
    for name in sorted(os.listdir(target)):
        full = os.path.join(target, name)
        try:
            st = os.stat(full)
        except OSError:
            continue
        is_dir = os.path.isdir(full)
        items.append(
            {
                "name": name,
                "type": "dir" if is_dir else "file",
                "size": 0 if is_dir else st.st_size,
                "mtime": int(st.st_mtime),
            }
        )
    # Directories first, then files; both alphabetical.
    items.sort(key=lambda it: (it["type"] != "dir", it["name"].lower()))
    rel = os.path.relpath(target, os.path.realpath(config.DATA_DIR))
    return {"path": "" if rel == "." else rel, "items": items}


@router.get("/read")
def read_file(path: str):
    target = utils.safe_join(config.DATA_DIR, path)
    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="file not found")
    if os.path.getsize(target) > config.MAX_TEXT_FILE_SIZE:
        raise HTTPException(status_code=400, detail="file too large")
    try:
        with open(target, "r", encoding="utf-8") as fh:
            content = fh.read()
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="binary file not editable")
    return {"path": path, "content": content}


@router.put("/write")
async def write_file(body: WriteBody):
    target = utils.safe_join(config.DATA_DIR, body.path)
    if os.path.isdir(target):
        raise HTTPException(status_code=400, detail="path is a directory")
    if len(body.content.encode("utf-8")) > config.MAX_TEXT_FILE_SIZE:
        raise HTTPException(status_code=400, detail="content too large")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    async with aiofiles.open(target, "w", encoding="utf-8") as fh:
        await fh.write(body.content)
    return {"ok": True}


@router.post("/upload")
async def upload_files(
    path: str = Form(""), files: List[UploadFile] = File(...)
):
    if len(files) > config.MAX_UPLOAD_FILES:
        raise HTTPException(status_code=400, detail="too many files")
    target_dir = utils.safe_join(config.DATA_DIR, path)
    if not os.path.isdir(target_dir):
        raise HTTPException(status_code=404, detail="directory not found")
    os.makedirs(target_dir, exist_ok=True)
    uploaded = []
    for f in files:
        filename = os.path.basename(f.filename or "")
        if not filename:
            continue
        dest = utils.safe_join(target_dir, filename)
        written = 0
        async with aiofiles.open(dest, "wb") as out:
            while chunk := await f.read(1024 * 1024):
                written += len(chunk)
                if written > config.MAX_UPLOAD_FILE_SIZE:
                    try:
                        os.remove(dest)
                    except FileNotFoundError:
                        pass
                    raise HTTPException(status_code=400, detail=f"file too large: {filename}")
                await out.write(chunk)
        uploaded.append(filename)
    return {"ok": True, "uploaded": uploaded}


@router.get("/download")
def download_file(path: str):
    target = utils.safe_join(config.DATA_DIR, path)
    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(
        target,
        media_type="application/octet-stream",
        filename=os.path.basename(target),
    )


@router.post("/mkdir")
def make_dir(body: PathBody):
    target = utils.safe_join(config.DATA_DIR, body.path)
    if target == os.path.realpath(config.DATA_DIR):
        raise HTTPException(status_code=400, detail="cannot create data root")
    if os.path.exists(target):
        raise HTTPException(status_code=400, detail="path already exists")
    os.makedirs(target, exist_ok=True)
    return {"ok": True}


@router.post("/rename")
def rename(body: RenameBody):
    src = utils.safe_join(config.DATA_DIR, body.src)
    dst = utils.safe_join(config.DATA_DIR, body.dst)
    if src == os.path.realpath(config.DATA_DIR) or dst == os.path.realpath(config.DATA_DIR):
        raise HTTPException(status_code=400, detail="cannot rename data root")
    if not os.path.exists(src):
        raise HTTPException(status_code=404, detail="source not found")
    if os.path.exists(dst):
        raise HTTPException(status_code=400, detail="destination already exists")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.replace(src, dst)
    return {"ok": True}


@router.delete("/delete")
def delete(body: PathBody):
    target = utils.safe_join(config.DATA_DIR, body.path)
    if target == os.path.realpath(config.DATA_DIR):
        raise HTTPException(status_code=400, detail="cannot delete data root")
    if not os.path.exists(target):
        raise HTTPException(status_code=404, detail="path not found")
    if os.path.isdir(target):
        shutil.rmtree(target)
    else:
        os.remove(target)
    return {"ok": True}
