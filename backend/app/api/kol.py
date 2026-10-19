"""KOL leaderboard + influence-scoring endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..analytics import influence as influence_mod
from ..models import InfluenceBreakdown, KolLeaderboard, KolRow
from ..store import get_store

router = APIRouter(prefix="/api/kol", tags=["kol"])


def _filters(df, specialty=None, state=None, company=None, min_score=None):
    out = df
    if specialty:
        out = out[out["specialty"].str.contains(specialty, case=False, na=False)]
    if state:
        out = out[out["state"].str.upper() == state.upper()]
    if company:
        store = get_store()
        npis = store.payments[
            store.payments["company_name"].str.contains(company, case=False, na=False)
        ]["npi"].unique()
        out = out[out["npi"].isin(npis)]
    if min_score is not None:
        out = out[out["influence_score"] >= min_score]
    return out


@router.get("/leaderboard", response_model=KolLeaderboard)
def leaderboard(
    specialty: str | None = None,
    state: str | None = None,
    company: str | None = None,
    min_score: float | None = Query(None, ge=0, le=100),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    store = get_store()
    infl = store.influence.merge(
        store.physicians[["npi", "display_name", "specialty", "state"]],
        on="npi", how="left")
    infl = _filters(infl, specialty, state, company, min_score)
    total = len(infl)
    page = infl.iloc[offset:offset + limit]
    rows = []
    for _, r in page.iterrows():
        rows.append(KolRow(
            rank=int(r["rank"]), npi=r["npi"],
            name=r.get("display_name", "") or r["npi"],
            specialty=r.get("specialty", ""), state=r.get("state", ""),
            influence_score=float(r["influence_score"]),
            publication_score=float(r["publication_score"]),
            trial_score=float(r["trial_score"]),
            network_score=float(r["network_score"]),
            payment_score=float(r["payment_score"]),
            publications=int(r["publications"]), trial_count=int(r["trial_count"]),
            degree=int(r["degree"]), total_received=float(r["total_received"]),
            n_companies=int(r["n_companies"]),
        ))
    return KolLeaderboard(total=total, rows=rows)


@router.get("/specialties", response_model=list[str])
def specialties():
    store = get_store()
    s = store.physicians["specialty"].fillna("")
    s = s[s != ""]
    return sorted(s.unique().tolist())[:200]


@router.get("/states", response_model=list[str])
def states():
    store = get_store()
    s = store.physicians["state"].fillna("").str.upper()
    return sorted([x for x in s.unique() if x])


@router.get("/companies", response_model=list[str])
def companies(q: str | None = None):
    store = get_store()
    names = store.payments["company_name"].dropna().unique().tolist()
    if q:
        names = [n for n in names if q.lower() in n.lower()]
    return sorted(names)[:200]


@router.get("/breakdown/{npi}", response_model=InfluenceBreakdown)
def breakdown(npi: str):
    store = get_store()
    row = store.influence[store.influence["npi"] == npi]
    if row.empty:
        raise HTTPException(status_code=404, detail="NPI not found")
    r = row.iloc[0]
    name = store.name_map.get(npi, npi)
    return InfluenceBreakdown(
        npi=npi, name=name,
        weights=influence_mod.DEFAULT_WEIGHTS,
        signals={
            "publication": float(r["publication_score"]),
            "trial": float(r["trial_score"]),
            "network": float(r["network_score"]),
            "payment": float(r["payment_score"]),
            "composite": float(r["influence_score"]),
        },
    )
