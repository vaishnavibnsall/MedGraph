"""Co-investigator network analytics (networkx).

Builds a physician<->physician graph from shared research engagements (Open
Payments principal investigators) and exposes centrality metrics + a pruned,
front-end-ready subgraph for visualisation.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

import networkx as nx
import pandas as pd


def build_graph(edges: pd.DataFrame) -> nx.Graph:
    """edges columns: npi_a, npi_b, weight, amount."""
    G = nx.Graph()
    for row in edges.itertuples(index=False):
        a, b = row.npi_a, row.npi_b
        if not a or not b or a == b:
            continue
        w = int(getattr(row, "weight", 1) or 1)
        amt = float(getattr(row, "amount", 0.0) or 0.0)
        if G.has_edge(a, b):
            G[a][b]["weight"] += w
            G[a][b]["amount"] += amt
        else:
            G.add_edge(a, b, weight=w, amount=amt)
    return G


def add_names(G: nx.Graph, name_map: Dict[str, str]) -> nx.Graph:
    for n in G.nodes:
        G.nodes[n]["label"] = name_map.get(n, n)
    return G


def centralities(G: nx.Graph) -> pd.DataFrame:
    """degree, weighted-degree (strength), and betweenness per node."""
    if G.number_of_nodes() == 0:
        return pd.DataFrame(columns=["npi", "degree", "wdegree", "betweenness", "clustering"])
    degree = dict(G.degree())
    wdegree = dict(G.degree(weight="weight"))
    # betweenness can be expensive on huge graphs; cap via topological order
    if G.number_of_nodes() > 20000:
        btw = {n: 0.0 for n in G.nodes}
    else:
        btw = nx.betweenness_centrality(G, weight="weight", k=min(200, G.number_of_nodes()))
    clustering = nx.clustering(G, weight="weight")
    df = pd.DataFrame({
        "npi": list(G.nodes()),
        "degree": [degree[n] for n in G.nodes()],
        "wdegree": [wdegree.get(n, 0) for n in G.nodes()],
        "betweenness": [btw.get(n, 0.0) for n in G.nodes()],
        "clustering": [clustering.get(n, 0.0) for n in G.nodes()],
    })
    return df


def top_subgraph(G: nx.Graph, top_npi: Iterable[str], k_hop: int = 1) -> nx.Graph:
    """Induce the subgraph around a set of anchor nodes (k-hop neighbourhood)."""
    anchors = [n for n in top_npi if n in G]
    keep = set(anchors)
    frontier = set(anchors)
    for _ in range(k_hop):
        nxt = set()
        for n in frontier:
            nxt.update(G.neighbors(n))
        keep |= nxt
        frontier = nxt
    return G.subgraph(keep).copy()


def largest_component_graph(G: nx.Graph) -> nx.Graph:
    if G.number_of_nodes() == 0:
        return G
    cc = max(nx.connected_components(G), key=len)
    return G.subgraph(cc).copy()


def to_cytoscape(G: nx.Graph, name_map: Dict[str, str] | None = None,
                 extra_node_attrs: Dict[str, dict] | None = None) -> Dict:
    """Serialise a graph to a {nodes, links} payload for the frontend."""
    name_map = name_map or {}
    extra_node_attrs = extra_node_attrs or {}
    nodes = []
    for n in G.nodes():
        attrs = dict(G.nodes[n])
        attrs.update(extra_node_attrs.get(n, {}))
        nodes.append({
            "id": n,
            "label": name_map.get(n, attrs.get("label", n)),
            **{k: v for k, v in attrs.items() if k != "label"},
        })
    links = []
    for u, v, data in G.edges(data=True):
        links.append({
            "source": u, "target": v,
            "weight": int(data.get("weight", 1)),
            "amount": round(float(data.get("amount", 0.0)), 2),
        })
    return {"nodes": nodes, "links": links}
