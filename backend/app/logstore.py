"""Minecraft-server-style per-start log storage.

Each managed program writes to ``<MANAGER_DIR>/logs/<program>/latest.log``.
Before a program is (re)started, the current ``latest.log`` is gzip-archived to
``<program>/<YYYY-MM-DD_HHMMSS>.log.gz`` so every run keeps its own file instead
of one ever-growing log shared by all runs. Old archives are pruned down to the
newest ``MAX_ARCHIVES`` per program.

The same layout/rotation is mirrored in ``docker-entrypoint.sh`` (shell) so the
very first start after a container boot also gets a fresh ``latest.log`` before
supervisord opens it. Rotation here must only run while the program is stopped
(its log fd closed) to avoid racing supervisord's writer.
"""

import gzip
import os
import re
import shutil
from datetime import datetime

from . import config

# Archive name: 2026-06-04_142601.log.gz  (optional _N suffix on same-second collision)
_ARCHIVE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}(?:_\d+)?\.log\.gz$")
MAX_ARCHIVES = 20


def program_dir(program: str) -> str:
    return os.path.join(config.LOG_DIR, program)


def latest_path(program: str) -> str:
    return os.path.join(program_dir(program), "latest.log")


def ensure_dirs(programs) -> None:
    for prog in programs:
        os.makedirs(program_dir(prog), exist_ok=True)


def list_archives(program: str) -> list[dict]:
    """Newest-first list of gzip archives for a program."""
    directory = program_dir(program)
    if not os.path.isdir(directory):
        return []
    items = []
    for fn in os.listdir(directory):
        if not _ARCHIVE_RE.match(fn):
            continue
        try:
            st = os.stat(os.path.join(directory, fn))
        except OSError:
            continue
        items.append({"file": fn, "size": st.st_size, "mtime": int(st.st_mtime)})
    # Filenames are timestamp-sorted, so a reverse string sort is newest-first.
    items.sort(key=lambda x: x["file"], reverse=True)
    return items


def archive_path(program: str, fname: str) -> str | None:
    """Resolve an archive filename to an absolute path, or None if invalid.

    ``fname`` is validated against a strict regex (no path separators / ``..``),
    so joining it onto the program dir cannot escape it.
    """
    if not _ARCHIVE_RE.match(fname):
        return None
    path = os.path.join(program_dir(program), fname)
    return path if os.path.isfile(path) else None


def _prune(program: str) -> None:
    for item in list_archives(program)[MAX_ARCHIVES:]:
        try:
            os.remove(os.path.join(program_dir(program), item["file"]))
        except OSError:
            pass


def rotate(program: str) -> str | None:
    """Gzip-archive the current ``latest.log`` (if non-empty) and remove it so
    the next start writes a fresh file. Returns the archive filename or None.

    Only call while the program is stopped; supervisord recreates ``latest.log``
    (append mode) on the next start.
    """
    directory = program_dir(program)
    os.makedirs(directory, exist_ok=True)
    latest = latest_path(program)
    try:
        if not os.path.isfile(latest) or os.path.getsize(latest) == 0:
            return None
    except OSError:
        return None

    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    fname = f"{ts}.log.gz"
    dest = os.path.join(directory, fname)
    n = 1
    while os.path.exists(dest):
        fname = f"{ts}_{n}.log.gz"
        dest = os.path.join(directory, fname)
        n += 1

    try:
        with open(latest, "rb") as fin, gzip.open(dest, "wb") as fout:
            shutil.copyfileobj(fin, fout)
        os.remove(latest)
    except OSError:
        return None
    _prune(program)
    return fname
