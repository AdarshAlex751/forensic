"""Agent-facing spatial tools. Signatures never change. Stubs return hard-coded answers
so Persons 3 and 4 are never blocked; Person 2 replaces the bodies with real sweep-graph math."""


def walk_time(room_a: str, room_b: str) -> dict:
    if room_a == room_b:
        return {"seconds": 0, "path": [room_a]}
    return {"seconds": 74, "path": [room_a, "elev-B", room_b]}


def ap_covers(ap_id: str, room_id: str) -> bool:
    return True


def camera_sees(camera_id: str, room_id: str) -> bool:
    return True
