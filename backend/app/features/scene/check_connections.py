"""Read-only provider smoke check. Run from the repo root; never prints keys."""

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend"))

from app.features.scene.matterport import get_model
from app.features.scene.providers import ProviderError
from app.features.scene.vexcel import get_aerial


def main() -> int:
    # Minimal loader for this standalone check; the app uses shared/config.py.
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
    try:
        model = get_model()
        print(f"Matterport OK: {model['id']} - {model['name']}", flush=True)
        location = model.get("geolocation") or {}
        if not location:
            print("Aerial check unavailable: model has no map coordinates.")
            return 1
        image, kind = get_aerial(float(location["lat"]), float(location["long"]))
        print(f"Vexcel OK: {kind}, {len(image)} bytes", flush=True)
        return 0
    except (ProviderError, KeyError, ValueError) as exc:
        # ProviderError messages are sanitized at the provider boundary.
        print(str(exc) if isinstance(exc, ProviderError) else "Model coordinates were invalid.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
