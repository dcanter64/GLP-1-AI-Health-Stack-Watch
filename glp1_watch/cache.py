from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd


def _key_to_path(cache_dir: Path, prefix: str, cache_key: str, suffix: str) -> Path:
    digest = hashlib.md5(cache_key.encode("utf-8"), usedforsecurity=False).hexdigest()
    return cache_dir / f"{prefix}_{digest}.{suffix}"


def load_cached_dataframe(cache_dir: Path, prefix: str, cache_key: str, max_age_hours: int) -> pd.DataFrame | None:
    data_path = _key_to_path(cache_dir, prefix, cache_key, "csv")
    meta_path = _key_to_path(cache_dir, prefix, cache_key, "json")
    if not data_path.exists() or not meta_path.exists():
        return None

    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    created_at = datetime.fromisoformat(metadata["created_at"])
    if datetime.now(timezone.utc) - created_at > timedelta(hours=max_age_hours):
        return None

    header_rows = metadata.get("header_rows", 1)
    if header_rows == 2:
        return pd.read_csv(data_path, header=[0, 1], index_col=0, parse_dates=True)
    return pd.read_csv(data_path, index_col=0, parse_dates=True)


def save_cached_dataframe(
    cache_dir: Path,
    prefix: str,
    cache_key: str,
    df: pd.DataFrame,
    header_rows: int = 1,
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    data_path = _key_to_path(cache_dir, prefix, cache_key, "csv")
    meta_path = _key_to_path(cache_dir, prefix, cache_key, "json")
    df.to_csv(data_path)
    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "header_rows": header_rows,
    }
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
