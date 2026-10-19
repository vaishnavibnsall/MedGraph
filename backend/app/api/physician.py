"""Physician drill-down profile endpoint."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..models import PhysicianProfile
from ..store import get_store

router = APIRouter(prefix="/api/physician", tags=["physician"])


@router.get("/{npi}", response_model=PhysicianProfile)
def profile(npi: str):
    store = get_store()
    p = store.physicians[store.physicians["npi"] == npi]
    if p.empty:
        raise HTTPException(status_code=404, detail="NPI not found")
    prow = p.iloc[0]

    # influence row
    infl = store.influence[store.influence["npi"] == npi]
    infl_row = None
    if not infl.empty:
        r = infl.iloc[0]
        infl_row = {
            "rank": int(r["rank"]), "npi": npi,
            "name": prow.get("display_name", npi),
            "specialty": prow.get("specialty", ""), "state": prow.get("state", ""),
            "influence_score": float(r["influence_score"]),
            "publication_score": float(r["publication_score"]),
            "trial_score": float(r["trial_score"]),
            "network_score": float(r["network_score"]),
            "payment_score": float(r["payment_score"]),
            "publications": int(r["publications"]), "trial_count": int(r["trial_count"]),
            "degree": int(r["degree"]), "total_received": float(r["total_received"]),
            "n_companies": int(r.get("n_companies", 0)),
        }

    # payments by company + nature
    pay = store.payments[store.payments["npi"] == npi]
    by_company = (pay.groupby("company_name")["amount"]
                  .agg(["sum", "count"]).reset_index()
                  .sort_values("sum", ascending=False).head(15))
    payments_by_company = [
        {"company_name": r["company_name"], "total": round(float(r["sum"]), 2),
         "n": int(r["count"])} for _, r in by_company.iterrows()]
    by_nature = (pay.groupby(pay["nature"].fillna("Unknown"))["amount"]
                 .agg(["sum", "count"]).reset_index()
                 .sort_values("sum", ascending=False).head(12))
    by_nature.columns = ["nature", "sum", "count"]
    payments_by_nature = [
        {"nature": r["nature"], "total": round(float(r["sum"]), 2), "n": int(r["count"])}
        for _, r in by_nature.iterrows()]

    # research engagements
    res = store.research[store.research["recipient_npi"] == npi]
    research = [
        {"company_name": r["company_name"], "amount": round(float(r["amount"]), 2),
         "date": r["date"], "study_id": r["study_id"], "form": r["form"]}
        for _, r in res.head(20).iterrows()]

    # publications
    pub = store.publications[store.publications["query_name"].str.upper().str.startswith(
        str(prow.get("last_name", "")).upper())] if len(store.publications) else store.publications
    publications = None
    if pub is not None and len(pub):
        # match by last name best-effort
        ln = str(prow.get("last_name", "")).upper()
        m = pub[pub["query_name"].str.upper().str.split(",").str[0].str.strip() == ln]
        if len(m):
            pr = m.iloc[0]
            publications = {"query_name": pr["query_name"], "hit_count": int(pr["hit_count"]),
                            "first_year": pr["first_year"], "last_year": pr["last_year"],
                            "top_journals": pr["top_journals"]}

    # nppes
    nppes = None
    nrow = store.nppes[store.nppes["npi"] == npi] if len(store.nppes) else None
    if nrow is not None and len(nrow):
        nr = nrow.iloc[0]
        nppes = {"credential": nr.get("credential", ""),
                 "primary_specialty": nr.get("primary_specialty", ""),
                 "taxonomy": nr.get("taxonomy", ""), "state": nr.get("state", ""),
                 "city": nr.get("city", "")}

    # network neighbors
    neighbors = []
    G = store.G
    if npi in G:
        for nbr in G.neighbors(npi):
            d = G[npi][nbr]
            neighbors.append({
                "npi": nbr, "name": store.name_map.get(nbr, nbr),
                "shared_studies": int(d.get("weight", 1)),
                "shared_amount": round(float(d.get("amount", 0.0)), 2)})
        neighbors.sort(key=lambda x: x["shared_studies"], reverse=True)

    # trials this physician is linked to (via official name match, best-effort)
    trials = []
    if len(store.officials):
        full = str(prow.get("display_name", "")).upper()
        last = str(prow.get("last_name", "")).upper()
        off = store.officials[store.officials["name"].str.upper().str.contains(last, na=False)] \
            if last else store.officials.iloc[0:0]
        if len(off) and len(store.trials):
            nct_ids = off["nct_id"].unique()[:10]
            t = store.trials[store.trials["nct_id"].isin(nct_ids)]
            trials = [{"nct_id": r["nct_id"], "title": r["title"], "sponsor": r["sponsor"],
                       "status": r["status"], "enrollment": int(r["enrollment"])}
                      for _, r in t.iterrows()]

    return PhysicianProfile(
        npi=npi, name=prow.get("display_name", npi),
        specialty=prow.get("specialty", ""), primary_type=prow.get("primary_type", ""),
        city=prow.get("city", ""), state=prow.get("state", ""),
        influence=infl_row, payments_by_company=payments_by_company,
        payments_by_nature=payments_by_nature, research=research,
        publications=publications, nppes=nppes, network_neighbors=neighbors,
        trials=trials,
    )


@router.get("/search/one")
def search(q: str = Query(..., min_length=2), limit: int = Query(10, ge=1, le=50)):
    store = get_store()
    physicians = store.physicians
    ql = q.lower()
    m = physicians[
        physicians["display_name"].str.lower().str.contains(ql, na=False)
        | physicians["npi"].str.contains(q, na=False)
    ].head(limit)
    return [{
        "npi": r["npi"], "name": r["display_name"], "specialty": r["specialty"],
        "state": r["state"],
    } for _, r in m.iterrows()]
