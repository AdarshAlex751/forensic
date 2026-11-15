"""Lets tests import the ingest pipeline as app.features.evidence.ingest (backend/ on sys.path)."""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
