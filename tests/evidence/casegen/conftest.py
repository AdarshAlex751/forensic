"""Lets tests import the generator as app.features.evidence.casegen (backend/ on sys.path)."""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
