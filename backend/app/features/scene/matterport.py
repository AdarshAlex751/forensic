"""Read-only Model API access. API credentials never leave the backend."""

import os

import httpx

from .providers import ProviderError

ENDPOINT = "https://api.matterport.com/api/models/graph"
MODEL_QUERY = """
query SceneModel($id: ID!) {
  model(id: $id) {
    id name
    address { address locality administrativeArea countryCode }
    geolocation { lat long }
  }
}
"""


def model_id() -> str:
    return os.getenv("VITE_MATTERPORT_MODEL_ID", "P3S6VUTP3qB").strip() or "P3S6VUTP3qB"


def get_model() -> dict:
    key = os.getenv("MATTERPORT_API_KEY", "").strip()
    token = os.getenv("MATTERPORT_API_TOKEN", "").strip()
    if not key or not token:
        raise ProviderError("Matterport API credentials are not configured.", 503)
    try:
        response = httpx.post(
            ENDPOINT,
            json={"query": MODEL_QUERY, "variables": {"id": model_id()}},
            auth=(key, token), timeout=25,
        )
    except httpx.RequestError:
        raise ProviderError("Matterport could not be reached.") from None
    if response.status_code != 200:
        raise ProviderError(f"Matterport returned HTTP {response.status_code}.")
    try:
        body = response.json()
        model = (body.get("data") or {}).get("model")
        if body.get("errors") or not model or model.get("id") != model_id():
            raise ProviderError("Matterport could not return the selected model. Check model access.")
        return model
    except (ValueError, AttributeError, TypeError):
        raise ProviderError("Matterport returned an invalid model response.") from None
