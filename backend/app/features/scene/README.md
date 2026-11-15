# Spatial tools: part 1 handoff

The three functions in `tools.py` are ready for Persons 3 and 4 to call.
They use **synthetic demo fixtures**, not measured building geometry. No API
credentials, SDK, network access, or third-party Python packages are needed.

With `backend` on the Python import path:

```python
from app.features.scene.tools import walk_time, ap_covers, camera_sees

walk_time("lobby", "212")
# {"seconds": 74, "path": ["lobby", "elev-B", "212"]}

walk_time("212", "lobby")
# {"seconds": 74, "path": ["212", "elev-B", "lobby"]}

walk_time("210", "210")
# {"seconds": 0, "path": ["210"]}

ap_covers("ap-2-east", "210")       # True
ap_covers("ap-2-east", "212")       # False (mock assumption)
camera_sees("cam-3", "corridor-2")  # True
camera_sees("cam-3", "212")         # False (mock assumption)
```

Use exact canonical IDs from `data/evidence/devices.csv`, not capitalized IDs
inside raw source quotes. Current fixtures use floor 2 and room `212`; the
floor 4 / `412` example in the plan is not the current fixture naming.

Known rooms are `lobby`, `elev-B`, `corridor-2`, `210`, and `212`.
Only lobby-to-212 and its reverse have travel-time fixtures. Same-room calls
return zero for any known room. Unknown IDs and unsupported journeys raise
`ValueError`; callers should skip the spatial check or report unavailable data,
not turn that exception into zero travel time or a negative coverage finding.

Coverage is explicitly mocked: the AP covers only `210`, and camera 3 sees only
`corridor-2`. These assumptions require validation against the real spatial
model. A camera coverage answer says nothing about whether its feed was working.
Do not present any stub answer as verified evidence.

Run the contract checks from the repository root:

```powershell
python -m unittest discover -s tests/scene -v
```

The next stage replaces these fixtures with measured graph travel times,
AP coverage, and camera view cones while preserving the three signatures.
No real scene output files or configuration flags are enabled by this step.

## Selected Matterport location

The user supplied model SID `P3S6VUTP3qB`, identifying it as the Princeton
Rabinowitz Hall foyer. The scene page embeds this tour as a location preview:
https://my.matterport.com/show/?m=P3S6VUTP3qB

The evidence owner's current case fixture still describes Houston and uses a
different model SID. Its room and sweep IDs are placeholders, not mappings into
this Princeton scan. The preview does not change case metadata or turn the
74-second mock journey into a measured route.

Next integration needs SDK access authorized for the application domain and
this model, actual sweep positions/connectivity, and a mapping from the case
rooms/devices to those sweeps. Coordinate case metadata changes with Person 1.
The iframe alone does not provide event camera synchronization or device overlays.

## Provider connections and scene preview

The scene now connects through the installed `@matterport/sdk` package. It offers
walk-through, dollhouse, and floor-plan controls, connection status and retry,
and an export of actual sweep IDs, positions, and neighbor links under
**Scene mapping setup**. Subscriptions and SDK connections are disposed when
leaving the page. The raw export uses the SDK's Y-up coordinate system in meters;
it is not yet a room mapping or verified travel-time model.

Vexcel requests use REST API 2.0 at `https://api.vexcelgroup.com/v2` with an
`X-API-KEY` header, following the supplied hackathon tutorial (pages 2-7).
The aerial view requests a 160 m square around the selected model's geolocation,
using all four recommended layers. It does not use the tutorial's example house
coordinates or claim that this square is a parcel boundary. Missing coordinates,
coverage, authentication failures, and rate limiting produce explicit errors.

Local credentials belong in the repository-root `.env`, which is ignored by Git:

```dotenv
MATTERPORT_API_KEY=<server-side token ID>
MATTERPORT_API_TOKEN=<server-side token secret>
VEXCEL_API_KEY=<server-side aerial key>
VITE_MATTERPORT_MODEL_ID=P3S6VUTP3qB
VITE_MATTERPORT_SDK_KEY=<browser SDK key authorized for localhost>
```

Only the two `VITE_` variables are intended for browser code. The private API
credentials must never receive a `VITE_` prefix. The existing Vite configuration
loads the root `.env`; restart Vite after changing it. Open the app using
`http://localhost:5173/scene` to match the SDK key's domain allowlist.
Integrator handoff: add `MATTERPORT_API_KEY`, `MATTERPORT_API_TOKEN`, and
`VEXCEL_API_KEY` names to the shared `.env.example` when merging.

Read-only scene routes:

- `GET /api/scene/model`: selected model's name, address, and geolocation.
- `GET /api/scene/aerial`: JPEG/PNG bytes fetched on the backend, with a private
  five-minute browser cache. The provider key never appears in this URL.
- `GET /api/scene/health`: service status and explicit demo spatial-tool status.

Run `python backend/app/features/scene/check_connections.py` from the repository
root for a live, read-only check of both providers. It prints model identity and
image size, never credentials. Normal tests use mocks and make no network calls.

The PDF's object detection and embedding search are not needed for the initial
aerial view and are not called. CoStar's supplied CSV starter lists do not contain
the Princeton SID, so tenant labels cannot be inferred from that kit for this model.


## Guided timeline (current UI)

Open /scene. The bottom time bar supports timestamp selection, chronological
scrubbing, previous/next events, and 10x/60x/300x playback. Only room 217 and
room 219 events move the camera. cam-03 events use room 219; all other places
remain timeline notes. Guided mode makes the embedded tour inert, blocking
pointer and keyboard navigation.

Use **Set up views** once: navigate to a known room view, face the desired
direction, and save as 217 or 219. The backend stores both sweep ID and camera
rotation in data/scene/mapping.json. Return to guided mode afterward.

Scenario preview follows CASE.md section 5 and the user's scene decisions.
It is clearly labeled as story data, with no fabricated verification or hashes.
Parking stays absent until released case evidence is available. Case evidence
mode filters out old Houston records and uses fixed -05:00 incident timestamps.
The configured 230-to-219 walking time is 74 seconds, per user instruction.
