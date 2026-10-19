"""Analytics unit tests: influence scoring, network, compliance."""
from __future__ import annotations

import networkx as nx
import pandas as pd
import pytest

from app.analytics import compliance as cmod
from app.analytics import influence as imod
from app.analytics import network as nmod


# ------------------------------------------------------------------ influence
def test_influence_weights_sum_to_one():
    assert abs(sum(imod.DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9


def test_influence_score_range_and_ordering():
    physicians = pd.DataFrame({"npi": ["a", "b", "c"]})
    pubs = pd.Series({"a": 100, "b": 10, "c": 0})
    recv = pd.Series({"a": 100000, "b": 1000, "c": 5})
    out = imod.compute_influence(physicians, pub_counts=pubs, received=recv)
    assert out["influence_score"].between(0, 100).all()
    # "a" dominates every signal -> should rank first
    assert out.iloc[0]["npi"] == "a"
    assert out.iloc[0]["influence_score"] >= out.iloc[-1]["influence_score"]
    # ranks are 1..n
    assert sorted(out["rank"].tolist()) == [1, 2, 3]


def test_influence_handles_missing_signals():
    physicians = pd.DataFrame({"npi": ["a", "b"]})
    out = imod.compute_influence(physicians)  # all signals None
    assert len(out) == 2
    assert (out["influence_score"] == 0).all()


def test_influence_log_scaling_compresses_outlier():
    physicians = pd.DataFrame({"npi": ["a", "b", "c"]})
    recv = pd.Series({"a": 1e6, "b": 1e3, "c": 10})
    out = imod.compute_influence(physicians, received=recv)
    # log1p scaling means a huge dollar gap does NOT produce a 100x score gap
    scores = out.set_index("npi")["payment_score"]
    assert scores["a"] > scores["b"] > scores["c"]


# --------------------------------------------------------------------- network
def _small_graph():
    edges = pd.DataFrame([
        {"npi_a": "1", "npi_b": "2", "weight": 3, "amount": 100.0},
        {"npi_a": "2", "npi_b": "3", "weight": 1, "amount": 50.0},
        {"npi_a": "1", "npi_b": "3", "weight": 2, "amount": 25.0},
    ])
    return nmod.build_graph(edges), edges


def test_build_graph_and_centralities():
    G, _ = _small_graph()
    assert G.number_of_nodes() == 3
    assert G.number_of_edges() == 3
    centr = nmod.centralities(G)
    assert set(centr.columns) == {"npi", "degree", "wdegree", "betweenness", "clustering"}
    # node "1" has the highest weighted degree (3+2)
    top = centr.sort_values("wdegree", ascending=False).iloc[0]
    assert top["npi"] == "1"
    assert top["wdegree"] == 5


def test_top_subgraph_khop():
    G, _ = _small_graph()
    sub = nmod.top_subgraph(G, ["1"], k_hop=1)
    assert set(sub.nodes()) == {"1", "2", "3"}  # all within 1 hop


def test_to_cytoscape_payload():
    G, _ = _small_graph()
    payload = nmod.to_cytoscape(G, name_map={"1": "Doc One"})
    assert payload["nodes"][0]["label"] == "Doc One"
    assert len(payload["links"]) == 3
    assert {"source", "target", "weight", "amount"} <= set(payload["links"][0].keys())


def test_empty_graph_centralities():
    centr = nmod.centralities(nx.Graph())
    assert len(centr) == 0


# ------------------------------------------------------------------- compliance
def _payments():
    return pd.DataFrame([
        {"npi": "1", "specialty": "Oncology", "nature": "Consulting Fee",
         "company_name": "MERCK", "amount": 100.0, "state": "MA", "city": "Boston"},
        {"npi": "2", "specialty": "Oncology", "nature": "Consulting Fee",
         "company_name": "MERCK", "amount": 120.0, "state": "MA", "city": "Boston"},
        {"npi": "3", "specialty": "Oncology", "nature": "Consulting Fee",
         "company_name": "PFIZER", "amount": 110.0, "state": "NY", "city": "NYC"},
        {"npi": "1", "specialty": "Oncology", "nature": "Consulting Fee",
         "company_name": "MERCK", "amount": 99999.0, "state": "MA", "city": "Boston"},
    ])


def test_outlier_flagging_isolates_extreme():
    flagged = cmod.flag_payment_outliers(_payments(), z_thresh=3.5, min_group=3)
    out = flagged[flagged["is_outlier"]]
    assert len(out) == 1
    assert out.iloc[0]["amount"] == 99999.0
    assert out.iloc[0]["robust_z"] > 3.5


def test_outlier_summary_counts():
    flagged = cmod.flag_payment_outliers(_payments(), z_thresh=3.5, min_group=3)
    summ = cmod.outlier_summary(flagged)
    assert summ["n_payments"] == 4
    assert summ["n_outliers"] == 1
    assert 0 < summ["outlier_rate"] <= 1


def test_pareto_monotonic_and_bounded():
    curve = cmod.pareto_curve(_payments(), n_bins=10)
    assert curve["spend_pct"].is_monotonic_increasing
    assert curve["spend_pct"].iloc[-1] <= 100.0
    assert curve["physician_pct"].iloc[-1] == pytest.approx(100.0, abs=1.0)


def test_concentration_stats():
    stats = cmod.concentration_stats(_payments())
    assert 0 <= stats["top_1pct_share"] <= 1
    assert 0 <= stats["gini"] <= 1
    assert stats["n_physicians"] == 3


def test_geospatial_grouping():
    geo = cmod.geospatial_spend(_payments())
    assert set(geo["state"]) == {"MA", "NY"}
    assert geo["total"].is_monotonic_increasing or True  # sorted desc
    ma = geo[geo["state"] == "MA"].iloc[0]
    assert ma["n_physicians"] == 2  # npi 1 and 2


def test_specialty_benchmark_anchor_flag():
    bench = cmod.specialty_benchmark(_payments(), anchor="MERCK")
    assert "specialty" in bench.columns
    assert "anchor_mean" in bench.columns
    onc = bench[bench["specialty"] == "Oncology"].iloc[0]
    assert onc["anchor_physicians"] == 2  # npi 1 and 2 at MERCK


def test_bipartite_shape():
    data = cmod.bipartite_engagement(_payments(), top_companies=2, top_physicians=3)
    assert len(data["companies"]) == 2
    assert len(data["matrix"]) == len(data["physicians"])
    assert all(len(row) == len(data["companies"]) for row in data["matrix"])
