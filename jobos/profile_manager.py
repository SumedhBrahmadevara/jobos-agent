from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def validate_yaml_text(text: str) -> dict[str, Any]:
    """Parse YAML text and return the dict. Raise ValueError with a human-readable message on failure."""
    try:
        result = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(str(exc)) from exc
    if result is None:
        return {}
    if not isinstance(result, dict):
        raise ValueError(
            f"Expected a YAML mapping (dict) at the top level, got {type(result).__name__}. "
            "Check that the file starts with key: value pairs, not a list."
        )
    return result


def backup_file(path: Path, backups_dir: Path) -> Path:
    """Copy path into backups_dir with a timestamped name. Creates backups_dir if needed."""
    backups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backups_dir / f"{timestamp}_{path.name}"
    shutil.copy2(path, dest)
    return dest


def save_yaml_safe(path: Path, text: str, backups_dir: Path) -> tuple[dict[str, Any], Path | None]:
    """Validate text as YAML, backup the existing file if present, then write.

    Returns (parsed_dict, backup_path).
    Raises ValueError if YAML is invalid — the original file is NOT touched.
    """
    parsed = validate_yaml_text(text)
    backup_path: Path | None = None
    if path.exists():
        backup_path = backup_file(path, backups_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return parsed, backup_path
