"""Co-investigator network graph endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..analytics import network as network_mod
from ..models import NetworkGraph
from ..store import get_store

router = APIRouter(prefix="/api/network", tags=["network"])


@router.get("/graph", response_model=NetworkGraph)
def graph(
    top_n: int = Query(120, ge=5, le=600),
    k_hop: int = Query(1, ge=1, le=3),
    anchor_npi: str | None = None,
):
    """Return a pruned co-investigator subgraph for visualisation.

    Anchors on the highest-influence physicians (or a given NPI) and expands
    k hops, keeping the graph legible while preserving the professional core.
    """
    store = get_store()
    G = store.G
    if G.number_of_nodes() == 0:
        return NetworkGraph(nodes=[], links=[], n_nodes=0, n_links=0)

    if anchor_npi and anchor_npi in G:
        anchors = [anchor_npi]
    else:
        infl = store.influence.sort_values("influence_score", ascending=False)
        anchors = [n for n in infl["npi"].tolist() if n in G][:max(top_n // 3, 10)]

    sub = network_mod.top_subgraph(G, anchors, k_hop=k_hop)
    if sub.number_of_nodes() > top_n:
        # keep the highest-degree nodes in the neighbourhood
        deg = sorted(sub.nodes(), key=lambda n: sub.degree(n), reverse=True)[:top_n]
        sub = sub.subgraph(deg).copy()

    centr = store.centrality
    extra = {}
    if len(centr):
        cmap = centr.set_index("npi")
        for n in sub.nodes():
            if n in cmap.index:
                extra[n] = {
                    "degree": int(cmap.loc[n, "degree"]),
                    "wdegree": int(cmap.loc[n, "wdegree"]),
                    "betweenness": round(float(cmap.loc[n, "betweenness"]), 5),
                }
    # attach influence for node sizing on the frontend
    infl_map = store.influence.set_index("npi")["influence_score"].to_dict() \
        if len(store.influence) else {}
    for n in sub.nodes():
        extra.setdefault(n, {})
        extra[n]["influence"] = round(float(infl_map.get(n, 0)), 2)

    payload = network_mod.to_cytoscape(sub, name_map=store.name_map,
                                       extra_node_attrs=extra)
    return NetworkGraph(nodes=payload["nodes"], links=payload["links"],
                        n_nodes=len(payload["nodes"]), n_links=len(payload["links"]))


@router.get("/ego/{npi}")
def ego(npi: str, hops: int = Query(1, ge=1, le=3)):
    store = get_store()
    G = store.G
    if npi not in G:
        return {"npi": npi, "exists": False, "neighbors": []}
    neighbors = []
    for nbr in G.neighbors(npi):
        d = G[npi][nbr]
        neighbors.append({
            "npi": nbr,
            "name": store.name_map.get(nbr, nbr),
            "shared_studies": int(d.get("weight", 1)),
            "shared_amount": round(float(d.get("amount", 0.0)), 2),
            "influence": round(float(store.influence.set_index("npi")["influence_score"].get(nbr, 0)), 2)
            if len(store.influence) else 0.0,
        })
    neighbors.sort(key=lambda x: x["shared_studies"], reverse=True)
    return {
        "npi": npi, "exists": True, "name": store.name_map.get(npi, npi),
        "degree": G.degree(npi), "neighbors": neighbors,
    }


@router.get("/stats")
def stats():
    store = get_store()
    G = store.G
    import networkx as nx
    n = G.number_of_nodes()
    if n == 0:
        return {"nodes": 0, "edges": 0, "density": 0, "components": 0, "avg_degree": 0}
    return {
        "nodes": n,
        "edges": G.number_of_edges(),
        "density": round(nx.density(G), 5),
        "components": nx.number_connected_components(G),
        "avg_degree": round(2 * G.number_of_edges() / n, 2),
    }
