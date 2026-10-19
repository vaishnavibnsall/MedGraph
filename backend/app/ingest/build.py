"""End-to-end dataset build orchestrator.

Runs the full MedGraph pipeline:
  1. Open Payments general payments  — stratified byte-range filter (8.3 GB -> sample)
  2. Open Payments research payments — full parse -> co-investigator edges
  3. ClinicalTrials.gov trials       — sponsor trial portfolio
  4. Europe PMC                      — publication signal for top candidates
  5. NPPES                           — optional specialty cross-check
  6. Influence scoring + SQLite load

Every stage is resumable-ish and logs progress. Run:
    python -m app.ingest.build            # full build
    python -m app.ingest.build --quick    # tiny sample (CI / smoke)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, Tuple

import networkx as nx
import pandas as pd

from .. import config, db, transform
from ..analytics import influence as influence_mod
from ..analytics import network as network_mod
from . import clinicaltrials, europepmc, nppes, openpayments
from .openpayments import build_co_investigator_edges

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("medgraph.build")

RESEARCH_CSV = config.RAW / "research_2024.csv"


def _ensure_research_download() -> Path:
    if RESEARCH_CSV.exists() and RESEARCH_CSV.stat().st_size > 1_000_000:
        return RESEARCH_CSV
    log.info("downloading research payments CSV ...")
    import urllib.request
    req = urllib.request.Request(
        sources_url(), headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=300) as r, open(RESEARCH_CSV, "wb") as f:
        while True:
            block = r.read(1 << 20)
            if not block:
                break
            f.write(block)
    return RESEARCH_CSV


def sources_url() -> str:
    from . import sources
    return sources.OP_RESEARCH_2024


def _build_name_to_npi(physicians: pd.DataFrame) -> Dict[str, str]:
    """Map normalised 'FIRST LAST' -> first matching physician NPI."""
    mapping: Dict[str, str] = {}
    for _, r in physicians.iterrows():
        first = str(r.get("first_name", "")).strip().upper()
        last = str(r.get("last_name", "")).strip().upper()
        npi = str(r.get("npi", "")).strip()
        if first and last and npi:
            key = f"{first} {last}"
            mapping.setdefault(key, npi)
    return mapping


def _build_merged_network(research_rows, trials, physicians):
    """Combine research-PI edges (NPI-keyed) with ClinicalTrials.gov investigator
    co-occurrence (name-keyed, resolved to NPI where possible) into one graph.

    Research PIs give a genuine but sparse NPI-linked core; trial officials add a
    denser professional layer. Officials that can't be resolved to a paid-recipient
    NPI remain as `OBS:<name>` nodes so the network keeps its true shape.
    Returns (edges_df, degree_series, wdegree_series, graph).
    """
    merged: Dict[Tuple[str, str], dict] = {}

    # 1) research-PI co-investigation (NPI <-> NPI)
    pi_edges, _ = build_co_investigator_edges(research_rows)
    for (a, b), d in pi_edges.items():
        key = tuple(sorted([a, b]))
        rec = merged.setdefault(key, {"weight": 0, "amount": 0.0, "companies": set(),
                                      "enrollment": 0, "ncts": set(), "source": "research"})
        rec["weight"] += d.get("weight", 1)
        rec["amount"] += d.get("amount", 0.0)
        rec["companies"] |= set(d.get("companies", set()))

    # 2) ClinicalTrials.gov investigator co-occurrence (name-keyed -> NPI)
    name_to_npi = _build_name_to_npi(physicians)
    off_edges = clinicaltrials.build_official_edges(trials)
    for (na, nb), d in off_edges.items():
        ka = name_to_npi.get(na, f"OBS:{na}")
        kb = name_to_npi.get(nb, f"OBS:{nb}")
        if ka == kb:
            continue
        key = tuple(sorted([ka, kb]))
        rec = merged.setdefault(key, {"weight": 0, "amount": 0.0, "companies": set(),
                                      "enrollment": 0, "ncts": set(), "source": "trial"})
        rec["weight"] += d.get("weight", 1)
        rec["enrollment"] += int(d.get("enrollment", 0))
        rec["ncts"] |= set(d.get("ncts", set()))

    edges = transform.edges_to_frame(merged)
    if not len(edges):
        return edges, None, None, nx.Graph()

    G = network_mod.build_graph(edges)
    centr = network_mod.centralities(G)
    degree_series = centr.set_index("npi")["degree"]
    wdegree_series = centr.set_index("npi")["wdegree"]

    # ensure OBS nodes get a readable label from their name
    for node in G.nodes():
        if isinstance(node, str) and node.startswith("OBS:"):
            G.nodes[node]["label"] = node[4:].title()
    return edges, degree_series, wdegree_series, G


def build(quick: bool = False, skip_network_signals: bool = False) -> Path:
    from . import sources  # noqa: F401  (ensure package importable)

    log.info("=== MedGraph build %s ===", "(quick)" if quick else "")

    # ---- 1. general payments -------------------------------------------------
    if quick:
        general_rows = openpayments.ingest_general(limit_rows=8000)
    else:
        general_rows = openpayments.ingest_general()
    general = transform.general_to_frame(general_rows)
    log.info("general frame: %s", general.shape)

    # ---- 2. research payments ------------------------------------------------
    research_csv = _ensure_research_download()
    research_rows = openpayments.ingest_research_from_path(research_csv)
    research = transform.research_to_frame(research_rows)
    log.info("research frame: %s", research.shape)

    # ---- 3. physicians registry ---------------------------------------------
    physicians = transform.build_physicians(general, research)
    log.info("physicians: %s", len(physicians))
    name_map = dict(zip(physicians["npi"], physicians["display_name"]))

    # ---- 4. clinical trials (sponsor portfolio + investigator network) ------
    sponsor_terms = ["Merck Sharp & Dohme", "Merck", "Pfizer", "AstraZeneca", "Novartis"]
    if quick:
        trials = clinicaltrials.fetch_sponsor_trials(["Merck Sharp & Dohme"])
    else:
        trials = clinicaltrials.fetch_sponsor_trials(sponsor_terms)
        trials.extend(clinicaltrials.fetch_network_trials(max_per_query=220))
    seen_nct, uniq = set(), []
    for t in trials:
        if t.nct_id in seen_nct:
            continue
        seen_nct.add(t.nct_id)
        uniq.append(t)
    trials = uniq
    trials_df = transform.trials_to_frame(trials)
    officials_df = transform.trial_officials_frame(trials)
    log.info("trials: %s  officials: %s", trials_df.shape, officials_df.shape)

    # ---- 5. merged co-investigator network ----------------------------------
    edges, degree_series, wdegree_series, G = _build_merged_network(
        research_rows, trials, physicians)
    log.info("network: %d edges, %d nodes", len(edges),
             G.number_of_nodes() if G is not None else 0)

    # trial influence per NPI via PI name match is fuzzy; we instead use research
    # engagement as the trial proxy (PI studies), which is NPI-linked and robust.
    research_per_pi = research_engagement_per_pi(research_rows)
    trial_counts = research_per_pi.get("trial_count")
    enrollment = research_per_pi.get("enrollment")

    # ---- 7. Europe PMC publications for top candidates -----------------------
    top_cands = _top_candidates(physicians, research_per_pi, limit=600 if quick else 1500)
    profiles = europepmc.enrich_candidates(top_cands)
    pub_df = transform.publication_frame(profiles)
    # map publication hits back to NPIs by (last, first-initial) key
    pub_map = _map_publications_to_npi(pub_df, physicians)
    pub_series = pd.Series({npi: v for npi, v in pub_map.items()})

    # ---- 8. NPPES cross-check (bounded) --------------------------------------
    sample_npis = physicians["npi"].head(400).tolist() if not quick else physicians["npi"].head(60).tolist()
    nppes_recs = nppes.enrich_npis(sample_npis)
    nppes_df = pd.DataFrame([r.__dict__ for r in nppes_recs]) if nppes_recs else pd.DataFrame()

    # ---- 9. influence scoring ------------------------------------------------
    received = general.groupby("npi")["amount"].sum() if len(general) else None
    n_companies = general.groupby("npi")["company_name"].nunique() if len(general) else None
    infl = influence_mod.compute_influence(
        physicians,
        pub_counts=pub_series,
        trial_counts=trial_counts,
        enrollment=enrollment,
        degree=degree_series,
        wdegree=wdegree_series,
        received=received,
    )
    if n_companies is not None:
        infl = infl.merge(n_companies.rename("n_companies"), on="npi", how="left")
    else:
        infl["n_companies"] = 0
    infl["n_companies"] = infl["n_companies"].fillna(0).astype(int)

    # ---- 10. load SQLite -----------------------------------------------------
    _load_sqlite(general, research, edges, trials_df, officials_df, physicians,
                 pub_df, nppes_df, infl, name_map)
    log.info("=== build complete -> %s ===", config.DB_PATH)
    return config.DB_PATH


def research_engagement_per_pi(research_rows) -> dict:
    """Per-PI research engagement: distinct studies + summed enrollment proxy.

    Open Payments research rows don't expose enrollment directly, so we use the
    number of distinct research engagements (study contexts) as the trial signal
    and scale by distinct companies as a light proxy for scope.
    """
    from collections import defaultdict
    studies = defaultdict(set)
    companies = defaultdict(set)
    for rp in research_rows:
        pis = {npi for npi, _ in rp.pis if npi}
        if rp.recipient_npi:
            pis.add(rp.recipient_npi)
        key_id = rp.study_id or rp.date or ""
        for npi in pis:
            if key_id:
                studies[npi].add(key_id)
            if rp.company:
                companies[npi].add(rp.company)
    trial_counts = pd.Series({k: len(v) for k, v in studies.items()})
    # engagement scope proxy: distinct studies x distinct companies
    enrollment = pd.Series({k: len(studies[k]) * max(len(companies[k]), 1)
                            for k in studies if k in companies})
    return {"trial_count": trial_counts, "enrollment": enrollment}


def _top_candidates(physicians: pd.DataFrame, research_per_pi: dict, limit: int) -> list:
    """Rank physician candidates for Europe PMC enrichment by research activity."""
    tc = research_per_pi.get("trial_count")
    ranked = physicians.copy()
    if tc is not None:
        ranked["tc"] = ranked["npi"].map(tc).fillna(0)
    else:
        ranked["tc"] = 0
    ranked = ranked.sort_values("tc", ascending=False).head(limit)
    return [{"last": r["last_name"], "first": r["first_name"], "npi": r["npi"]}
            for _, r in ranked.iterrows()]


def _map_publications_to_npi(pub_df: pd.DataFrame, physicians: pd.DataFrame) -> dict:
    """Best-effort join of Europe PMC name hits back to NPIs via last+initial."""
    if pub_df is None or len(pub_df) == 0:
        return {}
    def key(last, first):
        return f"{str(last).upper()}|{(str(first)[:1] if first else '').upper()}"
    pub_df = pub_df.copy()
    pub_df[["last", "first"]] = pub_df["query_name"].str.split(",", n=1, expand=True)
    pub_df["k"] = pub_df["last"].str.strip().str.upper() + "|" + pub_df["first"].str.strip().str[0].str.upper()
    lookup = dict(zip(pub_df["k"], pub_df["hit_count"]))
    out = {}
    for _, r in physicians.iterrows():
        k = key(r["last_name"], r["first_name"])
        if k in lookup:
            out[r["npi"]] = lookup[k]
    return out


def _load_sqlite(general, research, edges, trials_df, officials_df, physicians,
                 pub_df, nppes_df, infl, name_map) -> None:
    db.reset_db()
    with db.get_db() as conn:
        # physicians
        physicians_sub = physicians[[
            "npi", "profile_id", "first_name", "middle_name", "last_name", "display_name",
            "specialty", "primary_type", "city", "state", "zip_code", "country"]]
        physicians_sub.to_sql("physicians", conn, if_exists="append", index=False)

        # companies rollup
        if len(general):
            comp = (general.groupby("company_name")
                    .agg(total_amount=("amount", "sum"), n_records=("amount", "count"),
                         n_physicians=("npi", "nunique")).reset_index())
            comp["company_id"] = general.groupby("company_name")["company_id"].first().values
            comp[["company_id", "company_name", "total_amount", "n_records", "n_physicians"]] \
                .to_sql("companies", conn, if_exists="append", index=False)

        # payments
        pay_cols = ["npi", "company_name", "company_id", "amount", "date", "n_payments",
                    "form", "nature", "program_year"]
        general[pay_cols].to_sql("payments", conn, if_exists="append", index=False)

        # research payments
        if len(research):
            research[["recipient_npi", "company_name", "amount", "form", "date",
                      "study_id", "program_year"]].to_sql(
                "research_payments", conn, if_exists="append", index=False)

        # co-investigator edges
        if len(edges):
            edges.to_sql("co_investigator_edges", conn, if_exists="append", index=False)

        # trials + officials
        if len(trials_df):
            trials_df.to_sql("trials", conn, if_exists="append", index=False)
        if len(officials_df):
            officials_df.to_sql("trial_officials", conn, if_exists="append", index=False)

        # publications
        if len(pub_df):
            pub_df.to_sql("publications", conn, if_exists="append", index=False)

        # nppes
        if len(nppes_df):
            keep = [c for c in ["npi", "credential", "primary_specialty", "taxonomy",
                                "state", "city", "country"] if c in nppes_df.columns]
            nppes_df[keep].to_sql("nppes", conn, if_exists="append", index=False)

        # influence
        infl_cols = ["npi", "influence_score", "publication_score", "trial_score",
                     "network_score", "payment_score", "publications", "trial_count",
                     "total_enrollment", "degree", "total_received", "n_companies", "rank"]
        for c in infl_cols:
            if c not in infl.columns:
                infl[c] = 0
        infl[infl_cols].to_sql("physician_influence", conn, if_exists="append", index=False)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Build the MedGraph dataset")
    p.add_argument("--quick", action="store_true", help="tiny sample build for CI/smoke")
    args = p.parse_args(argv)
    build(quick=args.quick)
    return 0


if __name__ == "__main__":
    sys.exit(main())
