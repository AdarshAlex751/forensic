"""Loads the repo-root .env and exposes paths and USE_REAL_<SLICE> flags."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
CASE_ID = "1010F"


def use_real(slice_name: str) -> bool:
    return os.getenv(f"USE_REAL_{slice_name.upper()}", "false").strip().lower() == "true"
