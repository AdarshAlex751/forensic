"""Small, server-side aerial extract using the hackathon REST API 2.0 guide."""

import math
import os
import time

import httpx

from .providers import ProviderError

API = "https://api.vexcelgroup.com/v2"
LAYERS = "urban,urban-r,wide-area,urban-g"


def aerial_bounds(latitude: float, longitude: float) -> dict:
    if not (math.isfinite(latitude) and math.isfinite(longitude)
            and -85 < latitude < 85 and -180 <= longitude <= 180):
        raise ProviderError("The model has invalid coordinates for aerial imagery.", 422)
    # A 160 m square gives the building some surrounding context. This is an
    # area of interest, not a claimed parcel boundary or detected footprint.
    dlat = 80 / 111_320
    dlon = 80 / (111_320 * math.cos(math.radians(latitude)))
    w, e = longitude - dlon, longitude + dlon
    s, n = latitude - dlat, latitude + dlat
    return {"west": w, "east": e, "south": s, "north": n}


def aerial_request(latitude: float, longitude: float) -> dict:
    bounds = aerial_bounds(latitude, longitude)
    w, e, s, n = (bounds[key] for key in ("west", "east", "south", "north"))
    return {
        "wkt": f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))",
        "srid": 4326,
        "layer": LAYERS,
        "crop": "bounding_box",
        "destination-dimensions": "1000,1000",
        "image-format": "jpeg",
    }


def get_aerial(latitude: float, longitude: float) -> tuple[bytes, str]:
    key = os.getenv("VEXCEL_API_KEY", "").strip()
    if not key:
        raise ProviderError("Vexcel API credentials are not configured.", 503)
    body = aerial_request(latitude, longitude)
    for attempt in range(3):
        try:
            response = httpx.post(
                f"{API}/ortho/extract", json=body,
                headers={"X-API-KEY": key}, timeout=60,
            )
        except httpx.RequestError:
            raise ProviderError("Vexcel could not be reached.") from None
        if response.status_code == 429 and attempt < 2:
            time.sleep(2 ** attempt)
            continue
        if response.status_code == 404:
            raise ProviderError("Vexcel has no aerial imagery for this location and key.", 404)
        if response.status_code in (401, 403):
            raise ProviderError("Vexcel rejected access. Check the key and its coverage permissions.")
        if response.status_code == 429:
            raise ProviderError("Vexcel is rate limiting requests. Try again shortly.", 503)
        if response.status_code != 200:
            raise ProviderError(f"Vexcel returned HTTP {response.status_code}.")
        # Validate the binary response, not just an untrusted Content-Type.
        if response.content.startswith(b"\xff\xd8\xff"):
            return response.content, "image/jpeg"
        if response.content.startswith(b"\x89PNG\r\n\x1a\n"):
            return response.content, "image/png"
        raise ProviderError("Vexcel returned an unexpected image response.")
    raise ProviderError("Vexcel imagery is unavailable.")
