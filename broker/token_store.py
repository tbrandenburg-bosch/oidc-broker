"""Local JSON-backed storage for GitHub OAuth refresh tokens, keyed by
GitHub user id (`actor_id`). File permissions are restricted to the owner.

This is PoC-grade storage only — see docs/INITIAL.md cleanup checklist for
mandatory deletion after the exercise.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from threading import Lock

_lock = Lock()


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load(store_path: str) -> dict:
    path = Path(store_path)
    if not path.exists():
        return {}
    with _lock:
        return json.loads(path.read_text() or "{}")


def save_refresh_token(store_path: str, actor_id: str, refresh_token: str) -> None:
    path = Path(store_path)
    _ensure_parent(path)
    with _lock:
        data = load(store_path)
        data[str(actor_id)] = {"refresh_token": refresh_token}
        path.write_text(json.dumps(data, indent=2))
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def get_refresh_token(store_path: str, actor_id: str) -> str | None:
    data = load(store_path)
    entry = data.get(str(actor_id))
    return entry.get("refresh_token") if entry else None
