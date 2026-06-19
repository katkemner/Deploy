"""A tiny JSON-file persistence layer for the ManagerFit demo.

This is intentionally minimal — just enough to create shareable profile links
without standing up a database. Profiles are keyed by a short URL-safe token,
which doubles as the "shareable profile link" slug from the PRD.
"""

from __future__ import annotations

import json
import secrets
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

_LOCK = threading.Lock()


class Store:
    """File-backed store for manager and candidate profiles."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._write({"managers": {}, "candidates": {}})

    # -- low-level ---------------------------------------------------------- #
    def _read(self) -> Dict[str, Any]:
        with self.path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _write(self, data: Dict[str, Any]) -> None:
        # Write to a temp file then atomically replace, so a crash mid-write
        # can't corrupt the store.
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        tmp.replace(self.path)

    @staticmethod
    def _token() -> str:
        return secrets.token_urlsafe(6)

    # -- profiles ----------------------------------------------------------- #
    def save_manager(self, profile: Dict[str, Any]) -> str:
        return self._save("managers", profile)

    def save_candidate(self, profile: Dict[str, Any]) -> str:
        return self._save("candidates", profile)

    def _save(self, bucket: str, profile: Dict[str, Any]) -> str:
        with _LOCK:
            data = self._read()
            token = profile.get("id") or self._token()
            profile["id"] = token
            data[bucket][token] = profile
            self._write(data)
            return token

    def get_manager(self, token: str) -> Optional[Dict[str, Any]]:
        return self._read()["managers"].get(token)

    def get_candidate(self, token: str) -> Optional[Dict[str, Any]]:
        return self._read()["candidates"].get(token)

    def list_managers(self) -> List[Dict[str, Any]]:
        return list(self._read()["managers"].values())

    def list_candidates(self) -> List[Dict[str, Any]]:
        return list(self._read()["candidates"].values())
