"""API integration tests against the synthetic store (no network)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main as app_main


@pytest.fixture()
def client(store):
    # inject the synthetic store into the singleton the routers read from
    import app.store as store_mod
    store_mod._STORE = store
    with TestClient(app_main.app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok"
    assert j["physicians"] == 6
    assert j["payments"] > 0


def test_stats(client):
    r = client.get("/api/stats")
    assert r.status_code == 200
    j = r.json()
    assert j["physicians"] == 6
    assert j["edges"] == 4  # STUDY-A -> 3 edges, STUDY-B -> 1 edge
    assert j["program_year"] == 2024


def test_kol_leaderboard(client):
    r = client.get("/api/kol/leaderboard?limit=10")
    assert r.status_code == 200
    j = r.json()
    assert j["total"] == 6
    assert len(j["rows"]) == 6
    # sorted by influence desc
    scores = [row["influence_score"] for row in j["rows"]]
    assert scores == sorted(scores, reverse=True)
    # Grace Hopper has the most publications -> should rank #1
    assert j["rows"][0]["name"] == "Grace Hopper"


def test_kol_leaderboard_specialty_filter(client):
    r = client.get("/api/kol/leaderboard?specialty=Oncology")
    j = r.json()
    assert j["total"] == 3  # Ada Curie, Grace Hopper, Ada Lovelace
    assert all("Oncology" in row["specialty"] for row in j["rows"])


def test_kol_leaderboard_company_filter(client):
    r = client.get("/api/kol/leaderboard?company=PFIZER")
    j = r.json()
    npis = {row["npi"] for row in j["rows"]}
    assert npis == {"1003", "1006"}


def test_influence_breakdown(client):
    r = client.get("/api/kol/breakdown/1001")
    assert r.status_code == 200
    j = r.json()
    assert j["npi"] == "1001"
    assert set(j["signals"].keys()) == {"publication", "trial", "network", "payment", "composite"}
    assert abs(sum(j["weights"].values()) - 1.0) < 1e-6


def test_influence_breakdown_404(client):
    assert client.get("/api/kol/breakdown/9999").status_code == 404


def test_network_graph(client):
    r = client.get("/api/network/graph")
    assert r.status_code == 200
    j = r.json()
    assert j["n_nodes"] > 0
    assert j["n_links"] > 0
    # every link endpoint resolves to a node
    ids = {n["id"] for n in j["nodes"]}
    for link in j["links"]:
        assert link["source"] in ids and link["target"] in ids


def test_network_ego(client):
    r = client.get("/api/network/ego/1001")
    j = r.json()
    assert j["exists"] is True
    nbrs = {n["npi"] for n in j["neighbors"]}
    # 1001 co-investigated with 1003 and 1005 on STUDY-A
    assert {"1003", "1005"} <= nbrs


def test_compliance_outliers(client):
    r = client.get("/api/compliance/outliers")
    assert r.status_code == 200
    j = r.json()
    assert j["n_payments"] == 13  # 12 normal + 1 outlier
    assert j["n_outliers"] >= 1   # the 250k consulting payment


def test_compliance_top_outliers(client):
    r = client.get("/api/compliance/outliers/top")
    j = r.json()
    assert j["count"] >= 1
    top = j["rows"][0]
    assert top["amount"] == 250000.0
    assert top["robust_z"] > 0


def test_compliance_benchmark(client):
    r = client.get("/api/compliance/benchmark?anchor=MERCK")
    assert r.status_code == 200
    j = r.json()
    assert len(j) >= 1
    assert "specialty" in j[0]


def test_compliance_pareto_and_concentration(client):
    pareto = client.get("/api/compliance/pareto").json()
    assert len(pareto) >= 5
    conc = client.get("/api/compliance/concentration").json()
    assert conc["n_physicians"] == 6
    assert conc["total_spend"] > 0


def test_compliance_geospatial(client):
    geo = client.get("/api/compliance/geospatial").json()
    states = {g["state"] for g in geo}
    assert {"MA", "NY", "CA", "OR"} <= states


def test_compliance_nature(client):
    nat = client.get("/api/compliance/nature").json()
    natures = {n["nature"] for n in nat}
    assert "Consulting Fee" in natures


def test_compliance_bipartite(client):
    b = client.get("/api/compliance/bipartite").json()
    assert len(b["companies"]) >= 2
    assert len(b["matrix"]) == len(b["physicians"])


def test_physician_profile(client):
    r = client.get("/api/physician/1003")
    assert r.status_code == 200
    j = r.json()
    assert j["name"] == "Grace Hopper"
    assert j["specialty"] == "Oncology"
    assert j["influence"]["rank"] == 1
    # has neighbors from research network
    assert any(n["npi"] in {"1001", "1002"} for n in j["network_neighbors"])


def test_physician_profile_404(client):
    assert client.get("/api/physician/9999999999").status_code == 404


def test_physician_search(client):
    r = client.get("/api/physician/search/one?q=Hopper")
    j = r.json()
    assert any(x["npi"] == "1003" for x in j)


def test_trials_endpoints_empty_ok(client):
    # synthetic store has no trials table rows; endpoints should degrade gracefully
    assert client.get("/api/trials").status_code == 200
    assert client.get("/api/trials/summary").status_code == 200
