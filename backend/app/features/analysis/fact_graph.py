"""Stage 4: fact graph (NetworkX).

Nodes (PLAN.md stage 4): persons, devices, rooms, files, accounts, events.
Edges: used, located_in, accessed, sent, paid, said.
Betweenness centrality and Louvain communities feed the yarn board and the anomaly features.

Node ids: persons and devices keep their own ids (p_hank, rdr-219, lt-219); rooms are "room:219";
everything else is "<kind>:<value>" (file:C:\\Projects\\Titan\\x.step, usb:<serial>, channel:D0HANKKIM,
org:Northline Systems Inc, vehicle:W26-VCU, email:x@y). Statements are their event id (e9912).
"""
from collections import defaultdict
from typing import Any

import networkx as nx

from app.features.analysis import vocab
from app.features.analysis.entity_resolution import resolve_identifier

SEED = 42


def _room(room_id: str) -> str:
    return f"room:{room_id}"


def _add(g: nx.MultiDiGraph, node: str, kind: str, **attrs: Any) -> str:
    if node not in g:
        g.add_node(node, kind=kind, **attrs)
    return node


def _edges_for(e: dict, index: dict[str, str]) -> list[tuple[str, str, str, str, str]]:
    """(from, from_kind, to, to_kind, edge_type) facts this event supports."""
    p, t, a = e.get("person"), e.get("type"), e.get("attrs") or {}
    if not p and t == "email" and a.get("from"):
        # Outside sender (not in inventory): keep it as an account node so the message is still on the board.
        sender = f"email:{a['from'].lower()}"
        return [(sender, "account", resolve_identifier("email", addr, index) or f"email:{addr.lower()}",
                 "person" if resolve_identifier("email", addr, index) else "account", "sent") for addr in a.get("to") or []]
    if not p:
        return []
    host = a.get("host") or e.get("device")
    if t in vocab.BADGE | vocab.WIFI:
        return [(p, "person", e["device"], "device", "used")] if e.get("device") else []
    if t in vocab.PARKING:
        return [(p, "person", f"vehicle:{a['plate']}", "vehicle", "used")] if a.get("plate") else []
    if t in vocab.LOGON | vocab.LOGOFF:
        return [(p, "person", host, "device", "accessed")] if host else []
    if t in vocab.FILE_ACCESS:
        return [(p, "person", f"file:{a['path']}", "file", "accessed")] if a.get("path") else []
    if t in vocab.USB:
        out = [(p, "person", host, "device", "accessed")] if host else []
        if a.get("serial"):
            out.append((p, "person", f"usb:{a['serial']}", "usb", "used"))
        return out
    if t in vocab.MAINTENANCE:
        return [(p, "person", a["asset"], "device", "accessed")] if a.get("asset") else []
    if t == "email":
        out = []
        for addr in a.get("to") or []:
            to = resolve_identifier("email", addr, index)
            out.append((p, "person", to, "person") if to else (p, "person", f"email:{addr.lower()}", "account"))
        return [(f, fk, to, tk, "sent") for f, fk, to, tk in out]
    if t == "chat":
        return [(p, "person", f"channel:{a['channel']}", "account", "sent")] if a.get("channel") else []
    if t in vocab.PAYMENT:
        org = f"org:{a.get('counterparty') or 'unknown'}"
        if (a.get("amount") or 0) >= 0:
            return [(org, "org", p, "person", "paid")]
        return [(p, "person", org, "org", "paid")]
    if t in vocab.STATEMENT:
        return [(p, "person", e["id"], "statement", "said")]
    return []


def build_graph(events: list[dict], persons: list[dict], devices_csv: list[dict], index: dict[str, str]) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for p in persons:
        _add(g, p["id"], "person", name=p.get("name", ""))
    for d in devices_csv:
        _add(g, d["device_id"], "device", device_type=d.get("type"))
        if d.get("room"):
            g.add_edge(d["device_id"], _add(g, _room(d["room"]), "room"), type="located_in", events=[])

    seen_messages: set[str] = set()
    for e in events:
        if e.get("type") == "email":
            # One event per body line (FORMAT.md 3.2): link each message once, citing its first line.
            msg = (e.get("attrs") or {}).get("message_id") or e["id"]
            if msg in seen_messages:
                continue
            seen_messages.add(msg)
        for src, src_kind, dst, dst_kind, edge_type in _edges_for(e, index):
            _add(g, src, src_kind)
            _add(g, dst, dst_kind)
            g.add_edge(src, dst, type=edge_type, events=[e["id"]])
        a = e.get("attrs") or {}
        if e.get("type") in vocab.FILE_ACCESS and a.get("path") and a.get("host"):
            g.add_edge(f"file:{a['path']}", a["host"], type="located_in", events=[])  # structural, no event
    return g


def export_edges(g: nx.MultiDiGraph) -> list[dict[str, Any]]:
    """One {from, to, type, events} per (from, to, type). Adds from_kind/to_kind for the yarn board."""
    grouped: dict[tuple, list[str]] = defaultdict(list)
    for u, v, data in g.edges(data=True):
        grouped[(u, v, data["type"])].extend(data.get("events", []))
    return [
        {"from": u, "to": v, "type": t, "events": sorted(set(evs), key=lambda x: int(x[1:]) if x[1:].isdigit() else 0),
         "from_kind": g.nodes[u].get("kind"), "to_kind": g.nodes[v].get("kind")}
        for (u, v, t), evs in grouped.items()
    ]


def metrics(g: nx.MultiDiGraph) -> tuple[dict[str, float], dict[str, int]]:
    """(betweenness, community) per node, on the undirected simple projection."""
    simple = nx.Graph(g.to_undirected())
    if simple.number_of_nodes() == 0:
        return {}, {}
    betweenness = nx.betweenness_centrality(simple, normalized=True)
    community = {}
    for i, members in enumerate(nx.community.louvain_communities(simple, seed=SEED)):
        for node in members:
            community[node] = i
    return betweenness, community
