from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, ConfigDict
import json
import threading
from typing import Literal

from .matterport import get_model
from .providers import ProviderError
from .vexcel import get_aerial, aerial_bounds
from .config import get_config, load_mapping, model_id, ROOM_IDS, SCENE_DIR
from .evaluator import get_evaluation
from .tools import walk_time

router = APIRouter(prefix="/api/scene", tags=["scene"])
_mapping_lock = threading.Lock()


class Position(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    x: float
    y: float
    z: float


class Sweep(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    position: Position
    neighbors: list[str] = Field(default_factory=list, max_length=1000)
    enabled: bool = True
    alignmentType: Literal["aligned", "unaligned"] = "aligned"
    placementType: Literal["auto", "manual", "unplaced"] = "auto"


class ViewRotation(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    x: float = Field(ge=-90, le=90)
    y: float = Field(ge=-360, le=360)


class RoomMapping(BaseModel):
    model_id: str
    room_id: str
    view_rotation: ViewRotation | None = None
    sweep: Sweep
    sweeps: list[Sweep] = Field(min_length=1, max_length=10000)


@router.get("/config")
def config() -> dict:
    return get_config()


@router.get("/evaluation")
def evaluation() -> dict:
    return get_evaluation()


@router.get("/walk")
def walk(room_a: str, room_b: str) -> dict:
    try:
        return walk_time(room_a, room_b)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/mapping")
def save_mapping(body: RoomMapping) -> dict:
    if body.model_id != model_id() or body.room_id not in (*ROOM_IDS, "corridor-219"):
        raise HTTPException(422, "Unknown model or case room.")
    by_id = {sweep.id: sweep for sweep in body.sweeps}
    if len(by_id) != len(body.sweeps) or body.sweep.id not in by_id:
        raise HTTPException(422, "Sweep collection must contain unique IDs and the selected position.")
    selected = by_id[body.sweep.id]
    if selected.position != body.sweep.position or not selected.enabled or selected.alignmentType != "aligned" or selected.placementType == "unplaced":
        raise HTTPException(422, "Choose an enabled, aligned position from this scan.")
    with _mapping_lock:
        value = load_mapping() or {"model_id": body.model_id, "rooms": {}}
        value["rooms"][body.room_id] = selected.model_dump()
        if body.view_rotation is not None:
            value["rooms"][body.room_id]["view_rotation"] = body.view_rotation.model_dump()
        value["sweeps"] = [sweep.model_dump() for sweep in body.sweeps]
        value["status"] = "operator_mapped"
        SCENE_DIR.mkdir(parents=True, exist_ok=True)
        path = SCENE_DIR / "mapping.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        temporary.replace(path)
    return get_config()


@router.get("/health")
def health() -> dict[str, str]:
    return {"slice": "scene", "status": "ok", "spatial_tools": "demo"}


@router.get("/model")
def model() -> dict:
    try:
        return get_model()
    except ProviderError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None


@router.get("/aerial")
def aerial() -> Response:
    try:
        location = get_model().get("geolocation") or {}
        try:
            latitude, longitude = float(location["lat"]), float(location["long"])
        except (KeyError, ValueError, TypeError):
            raise ProviderError("The selected model has no usable map coordinates.", 422) from None
        content, content_type = get_aerial(latitude, longitude)
        return Response(content=content, media_type=content_type,
                        headers={"Cache-Control": "private, max-age=300"})
    except ProviderError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None


@router.get("/aerial/bounds")
def aerial_metadata() -> dict:
    try:
        location = get_model().get("geolocation") or {}
        try:
            lat, lng = float(location["lat"]), float(location["long"])
        except (KeyError, ValueError, TypeError):
            raise ProviderError("The selected model has no usable map coordinates.", 422) from None
        return {"center": {"lat": lat, "lng": lng}, "bounds": aerial_bounds(lat, lng)}
    except ProviderError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
