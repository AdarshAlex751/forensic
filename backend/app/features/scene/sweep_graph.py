"""Directed sweep-neighbor distances; no invented edges or elevator waits."""
import heapq
import math


def route(sweeps: list, start: str, end: str) -> dict:
    nodes = {s["id"]: s for s in sweeps if s.get("enabled", True)
             and s.get("alignmentType") == "aligned" and s.get("placementType") != "unplaced"}
    if start not in nodes or end not in nodes:
        raise ValueError("Selected rooms do not have enabled, aligned scan positions.")
    queue = [(0.0, start, [start])]
    visited = set()
    while queue:
        distance, node, path = heapq.heappop(queue)
        if node in visited:
            continue
        visited.add(node)
        if node == end:
            return {"seconds": round(distance / 1.4, 2), "distance_m": round(distance, 3),
                    "sweep_path": path, "status": "scan_distance_estimate", "walking_speed_m_s": 1.4,
                    "limitations": "Sweep spacing estimate; excludes door, stair and elevator delays; not a proven minimum travel time."}
        for neighbor in nodes[node].get("neighbors", []):
            if neighbor not in nodes or neighbor in visited:
                continue
            a, b = nodes[node]["position"], nodes[neighbor]["position"]
            length = math.dist([a[k] for k in ("x", "y", "z")], [b[k] for k in ("x", "y", "z")])
            if math.isfinite(length):
                heapq.heappush(queue, (distance + length, neighbor, path + [neighbor]))
    raise ValueError("No connected scan path between the selected rooms.")
