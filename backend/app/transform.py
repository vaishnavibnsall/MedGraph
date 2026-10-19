"""Transform layer: unify heterogeneous ingest outputs into tidy DataFrames.

Kept separate from both ingest (I/O) and analytics (math) so the cleaning /
entity-resolution rules live in one testable place.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

import pandas as pd

from .ingest.openpayments import GeneralRow, ResearchPayment


def general_to_frame(rows: Iterable[GeneralRow]) -> pd.DataFrame:
    rows = list(rows)
    if not rows:
        return pd.DataFrame(columns=[
            "npi", "profile_id", "first_name", "middle_name", "last_name", "suffix",
            "specialty", "primary_type", "city", "state", "zip_code", "country",
            "company_name", "company_id", "amount", "date", "n_payments", "form",
            "nature", "program_year"])
    df = pd.DataFrame([r.__dict__ for r in rows])
    df = df.rename(columns={
        "first": "first_name", "middle": "middle_name", "last": "last_name",
        "company": "company_name", "rtype": "primary_type",
        "street": "street", "zip_code": "zip_code",
    })
    return df


def research_to_frame(rows: Iterable[ResearchPayment]) -> pd.DataFrame:
    rows = list(rows)
    if not rows:
        return pd.DataFrame(columns=[
            "recipient_npi", "recipient_name", "recipient_specialty", "recipient_state",
            "company_name", "form", "amount", "date", "study_id", "program_year", "pis"])
    df = pd.DataFrame([{
        "recipient_npi": r.recipient_npi, "recipient_name": r.recipient_name,
        "recipient_specialty": r.recipient_specialty, "recipient_state": r.recipient_state,
        "company_name": r.company, "form": r.form, "amount": r.amount, "date": r.date,
        "study_id": r.study_id, "program_year": r.program_year, "pis": r.pis,
    } for r in rows])
    return df


def build_physicians(general: pd.DataFrame, research: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per NPI, merged from general-payment recipients + research PIs."""
    frames = []
    if general is not None and len(general):
        g = (general.groupby("npi")
             .agg(first_name=("first_name", "first"),
                  middle_name=("middle_name", "first"),
                  last_name=("last_name", "first"),
                  specialty=("specialty", "first"),
                  primary_type=("primary_type", "first"),
                  city=("city", "first"),
                  state=("state", "first"),
                  zip_code=("zip_code", "first"),
                  country=("country", "first"),
                  profile_id=("profile_id", "first"))
             .reset_index())
        frames.append(g)

    if research is not None and len(research):
        # research principal investigators (expand pis list)
        recs = []
        for row in research.itertuples(index=False):
            for npi, name in (row.pis or []):
                if not npi:
                    continue
                parts = name.split()
                recs.append({
                    "npi": npi,
                    "first_name": parts[0] if parts else "",
                    "last_name": parts[-1] if len(parts) > 1 else "",
                    "specialty": row.recipient_specialty or "",
                    "state": row.recipient_state or "",
                })
        if recs:
            rp = pd.DataFrame(recs).drop_duplicates("npi")
            frames.append(rp.reindex(columns=[
                "npi", "first_name", "middle_name", "last_name", "specialty",
                "primary_type", "city", "state", "zip_code", "country", "profile_id"]))

    if not frames:
        return pd.DataFrame(columns=[
            "npi", "first_name", "middle_name", "last_name", "specialty",
            "primary_type", "city", "state", "zip_code", "country", "profile_id"])

    merged = pd.concat(frames, ignore_index=True)
    # general-payment data is authoritative for demographics; fill gaps from research
    merged = merged.drop_duplicates("npi", keep="first")
    merged["display_name"] = (
        merged["first_name"].fillna("").str.title() + " " + merged["last_name"].fillna("").str.title()
    ).str.strip()
    return merged.fillna("")


def edges_to_frame(edges: Dict[Tuple[str, str], dict]) -> pd.DataFrame:
    if not edges:
        return pd.DataFrame(columns=["npi_a", "npi_b", "weight", "amount", "companies"])
    recs = []
    for (a, b), d in edges.items():
        recs.append({
            "npi_a": a, "npi_b": b, "weight": d.get("weight", 1),
            "amount": round(float(d.get("amount", 0.0)), 2),
            "companies": "|".join(sorted(d.get("companies", []))),
        })
    return pd.DataFrame(recs)


def publication_frame(profiles) -> pd.DataFrame:
    if not profiles:
        return pd.DataFrame(columns=["query_name", "hit_count", "first_year", "last_year", "top_journals"])
    return pd.DataFrame([{
        "query_name": p.query_name, "hit_count": p.hit_count,
        "first_year": p.first_year, "last_year": p.last_year,
        "top_journals": "|".join(p.top_journals),
    } for p in profiles])


def trials_to_frame(trials) -> pd.DataFrame:
    if not trials:
        return pd.DataFrame(columns=[
            "nct_id", "title", "status", "sponsor", "sponsor_class", "conditions",
            "interventions", "phases", "enrollment", "start_date", "completion_date",
            "study_type"])
    return pd.DataFrame([{
        "nct_id": t.nct_id, "title": t.title, "status": t.status, "sponsor": t.sponsor,
        "sponsor_class": t.sponsor_class, "conditions": "|".join(t.conditions),
        "interventions": "|".join(t.interventions), "phases": "|".join(t.phases),
        "enrollment": t.enrollment, "start_date": t.start_date,
        "completion_date": t.completion_date, "study_type": t.study_type,
    } for t in trials])


def trial_officials_frame(trials) -> pd.DataFrame:
    recs = []
    for t in trials:
        for o in t.officials:
            recs.append({"nct_id": t.nct_id, "name": o.name,
                         "affiliation": o.affiliation, "role": o.role})
    if not recs:
        return pd.DataFrame(columns=["nct_id", "name", "affiliation", "role"])
    return pd.DataFrame(recs)
