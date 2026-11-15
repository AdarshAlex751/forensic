"""Publish scene configuration, never manufacture evidence or verification."""
import json
from .config import SCENE_DIR, get_config
from .evaluator import get_evaluation


def run(case_id: str) -> None:
    if case_id != "1010F":
        raise ValueError("Unknown scene case")
    config = get_config()
    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("rooms", "devices"):
        (SCENE_DIR / f"{name}.json").write_text(json.dumps(config[name], indent=2), encoding="utf-8")
    (SCENE_DIR / "eval.json").write_text(json.dumps(get_evaluation(), indent=2), encoding="utf-8")
