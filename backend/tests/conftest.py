"""Shared pytest fixtures: an in-memory synthetic MedGraph DB.

The tests do NOT hit the network. They build a tiny deterministic dataset that
exercises the transform, analytics, and API layers the same way the real build
does, so the whole stack is verified offline and fast.
"""
from __future__ import annotations

import pandas as pd
import pytest

from app import db
from app.store import Store, refresh
from app.ingest.openpayments import GeneralRow, ResearchPayment, build_co_investigator_edges
from app import transform
from app.analytics import influence as influence_mod


def _gen(npi, first, last, specialty, state, city, company, amount, nature, n_pay=1):
    return GeneralRow(
        npi=npi, profile_id="", first=first, middle="", last=last, suffix="",
        rtype="Covered Recipient Physician", specialty=specialty, prim_types=specialty,
        street="1 Main St", city=city, state=state, zip_code="00000",
        country="United States", company=company, company_id="1", amount=amount,
        date="2024-05-01", n_payments=n_pay, form="Cash or cash equivalent",
        nature=nature, program_year="2024")


@pytest.fixture(scope="session")
def synth_data():
    """Deterministic mini-dataset: 6 physicians, 3 companies, a PI network."""
    docs = [
        ("1001", "Ada", "Curie", "Oncology", "MA", "Boston", "MERCK SHARP & DOHME"),
        ("1002", "Ben", "Franklin", "Cardiology", "NY", "New York", "MERCK SHARP & DOHME"),
        ("1003", "Grace", "Hopper", "Oncology", "MA", "Boston", "PFIZER INC."),
        ("1004", "Alan", "Turing", "Neurology", "CA", "Palo Alto", "ASTRAZENECA"),
        ("1005", "Ada", "Lovelace", "Oncology", "MA", "Boston", "MERCK SHARP & DOHME"),
        ("1006", "Linus", "Torvalds", "Family Medicine", "OR", "Portland", "PFIZER INC."),
    ]
    general = []
    for npi, f, l, spec, st, city, comp in docs:
        general.append(_gen(npi, f, l, spec, st, city, comp, 100.0, "Food and Beverage"))
        general.append(_gen(npi, f, l, spec, st, city, comp, 5000.0, "Consulting Fee"))
    # an outlier: one huge consulting payment to Grace Hopper
    general.append(_gen("1003", "Grace", "Hopper", "Oncology", "MA", "Boston",
                        "PFIZER INC.", 250000.0, "Consulting Fee"))

    # research engagements define PI co-investigator links
    research = [
        ResearchPayment("1001", "Ada Curie", "Oncology", "MA", "MERCK", "", 10000,
                        "2024-01-01", "STUDY-A", "2024",
                        pis=[("1001", "Ada Curie"), ("1003", "Grace Hopper"),
                             ("1005", "Ada Lovelace")]),
        ResearchPayment("1003", "Grace Hopper", "Oncology", "MA", "PFIZER", "", 5000,
                        "2024-02-01", "STUDY-B", "2024",
                        pis=[("1003", "Grace Hopper"), ("1002", "Ben Franklin")]),
        ResearchPayment("1004", "Alan Turing", "Neurology", "CA", "ASTRA", "", 7000,
                        "2024-03-01", "STUDY-C", "2024",
                        pis=[("1004", "Alan Turing")]),  # single PI -> no edge
    ]
    edges, degree = build_co_investigator_edges(research)
    return {"general": general, "research": research, "edges": edges, "degree": degree}


@pytest.fixture(scope="session")
def store(synth_data, tmp_path_factory):
    """Materialise a Store from the synthetic dataset (points DB at temp file)."""
    tmpdir = tmp_path_factory.mktemp("medgraph")
    dbfile = tmpdir / "test.sqlite"

    general = transform.general_to_frame(synth_data["general"])
    research = transform.research_to_frame(synth_data["research"])
    edges = transform.edges_to_frame(synth_data["edges"])
    physicians = transform.build_physicians(general, research)

    # influence with a trivial publication signal
    pubs = pd.Series({"1001": 40, "1003": 120, "1005": 5})
    received = general.groupby("npi")["amount"].sum()
    ncomp = general.groupby("npi")["company_name"].nunique()
    degree_series = pd.Series(synth_data["degree"])
    infl = influence_mod.compute_influence(
        physicians, pub_counts=pubs, trial_counts=None, enrollment=None,
        degree=degree_series, wdegree=degree_series, received=received)
    infl = infl.merge(ncomp.rename("n_companies"), on="npi", how="left")
    infl["n_companies"] = infl["n_companies"].fillna(0).astype(int)

    # write to sqlite using the same loader shape
    db.reset_db(str(dbfile))
    with db.get_db(str(dbfile)) as conn:
        physicians[["npi", "profile_id", "first_name", "middle_name", "last_name",
                    "display_name", "specialty", "primary_type", "city", "state",
                    "zip_code", "country"]].to_sql("physicians", conn, if_exists="append",
                                                   index=False)
        comp = (general.groupby("company_name")
                .agg(total_amount=("amount", "sum"), n_records=("amount", "count"),
                     n_physicians=("npi", "nunique")).reset_index())
        comp["company_id"] = "1"
        comp.to_sql("companies", conn, if_exists="append", index=False)
        general[["npi", "company_name", "company_id", "amount", "date", "n_payments",
                 "form", "nature", "program_year"]].to_sql("payments", conn,
                                                           if_exists="append", index=False)
        research[["recipient_npi", "company_name", "amount", "form", "date", "study_id",
                  "program_year"]].to_sql("research_payments", conn, if_exists="append",
                                          index=False)
        edges.to_sql("co_investigator_edges", conn, if_exists="append", index=False)
        infl[["npi", "influence_score", "publication_score", "trial_score", "network_score",
              "payment_score", "publications", "trial_count", "total_enrollment", "degree",
              "total_received", "n_companies", "rank"]].to_sql(
            "physician_influence", conn, if_exists="append", index=False)

    s = Store()
    s.load(str(dbfile))
    return s
