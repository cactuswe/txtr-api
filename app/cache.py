from __future__ import annotations
import json
import os
import time
import hashlib
from dataclasses import dataclass
from typing import Any

@dataclass
class CacheEntry:
    etag: str
    fetched_at: float
    ttl: int
    payload: dict[str, Any]

def _hash_key(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _path(base_dir: str, key: str) -> str:
    return os.path.join(base_dir, f"{key}.json")

def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def get(base_dir: str, url: str) -> CacheEntry | None:
    ensure_dir(base_dir)
    fp = _path(base_dir, _hash_key(url))
    if not os.path.exists(fp):
        return None
    try:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        ttl = int(data.get("ttl", 0))
        fetched_at = float(data.get("fetched_at", 0))
        if ttl > 0 and (time.time() - fetched_at) > ttl:
            return None
        return CacheEntry(
            etag=str(data["etag"]),
            fetched_at=fetched_at,
            ttl=ttl,
            payload=data["payload"],
        )
    except Exception:
        return None

def set(base_dir: str, url: str, etag: str, payload: dict[str, Any], ttl: int) -> None:
    ensure_dir(base_dir)
    fp = _path(base_dir, _hash_key(url))
    blob = {
        "etag": etag,
        "fetched_at": time.time(),
        "ttl": int(ttl),
        "payload": payload,
    }
    tmp = fp + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(blob, f, ensure_ascii=False)
    os.replace(tmp, fp)

def size_bytes(base_dir: str) -> int:
    total = 0
    if not os.path.isdir(base_dir): 
        return 0
    for name in os.listdir(base_dir):
        fp = os.path.join(base_dir, name)
        if os.path.isfile(fp):
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total
