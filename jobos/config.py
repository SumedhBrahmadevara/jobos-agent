from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
OUTPUTS_DIR = ROOT_DIR / "outputs"
APPLICATIONS_DIR = OUTPUTS_DIR / "applications"

load_dotenv(ROOT_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
JOBOS_MODEL = os.getenv("JOBOS_MODEL", "gpt-5.5")
JOBOS_OFFLINE_MODE = os.getenv("JOBOS_OFFLINE_MODE", "false").lower() in {"1", "true", "yes"}


def ensure_dirs() -> None:
    OUTPUTS_DIR.mkdir(exist_ok=True)
    APPLICATIONS_DIR.mkdir(exist_ok=True)
