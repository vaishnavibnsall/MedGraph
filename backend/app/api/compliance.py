"""Compliance analytics endpoints: outliers, benchmarking, Pareto, geospatial,
bipartite engagement."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..analytics import compliance as cmod
from ..models import (BenchmarkRow, Bipartite, CompanyTotal, Concentration,
                      GeoPoint, MetroPoint, NaturePoint, OutlierSummary, ParetoPoint)
from ..store import get_store

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


@router.get("/outliers", response_model=OutlierSummary)
def outliers(z_thresh: float = Query(4.0, ge=1, le=12)):
    store = get_store()
    flagged = cmod.flag_payment_outliers(store.payments, z_thresh=z_thresh)
    return cmod.outlier_summary(flagged)


@router.get("/outliers/top")
def top_outliers(limit: int = Query(30, ge=1, le=200),
                 z_thresh: float = Query(4.0, ge=1, le=12),
                 company: str | None = None):
    store = get_store()
    flagged = cmod.flag_payment_outliers(store.payments, z_thresh=z_thresh)
    out = flagged[flagged["is_outlier"]]
    if company:
        out = out[out["company_name"].str.contains(company, case=False, na=False)]
    out = out.sort_values("robust_z", ascending=False).head(limit)
    rows = []
    for _, r in out.iterrows():
        rows.append({
            "npi": r["npi"],
            "name": r.get("display_name", "") or r["npi"],
            "specialty": r.get("specialty", ""),
            "state": r.get("state", ""),
            "company_name": r["company_name"],
            "amount": round(float(r["amount"]), 2),
            "nature": r.get("nature", ""),
            "form": r.get("form", ""),
            "cohort_median": float(r["cohort_median"]),
            "robust_z": float(r["robust_z"]),
        })
    return {"count": len(rows), "rows": rows}


@router.get("/benchmark", response_model=list[BenchmarkRow])
def benchmark(anchor: str = Query("MERCK"), top_n: int = Query(12, ge=3, le=30)):
    store = get_store()
    bench = cmod.specialty_benchmark(store.payments, anchor=anchor, top_n=top_n)
    return [BenchmarkRow(**{k: (None if r.get(k) != r.get(k) else r.get(k))
                            for k in BenchmarkRow.model_fields})
            for r in bench.to_dict(orient="records")]


@router.get("/companies", response_model=list[CompanyTotal])
def company_totals(top: int = Query(20, ge=1, le=60)):
    store = get_store()
    g = cmod.company_totals(store.payments, top=top)
    return [CompanyTotal(**r) for r in g.to_dict(orient="records")]


@router.get("/pareto", response_model=list[ParetoPoint])
def pareto(n_bins: int = Query(20, ge=5, le=50)):
    store = get_store()
    curve = cmod.pareto_curve(store.payments, n_bins=n_bins)
    return [ParetoPoint(**r) for r in curve.to_dict(orient="records")]


@router.get("/concentration", response_model=Concentration)
def concentration():
    store = get_store()
    return Concentration(**cmod.concentration_stats(store.payments))


@router.get("/geospatial", response_model=list[GeoPoint])
def geospatial():
    store = get_store()
    g = cmod.geospatial_spend(store.payments)
    return [GeoPoint(**r) for r in g.to_dict(orient="records")]


@router.get("/metro", response_model=list[MetroPoint])
def metro(top: int = Query(15, ge=1, le=50)):
    store = get_store()
    g = cmod.metro_spend(store.payments, top=top)
    return [MetroPoint(**r) for r in g.to_dict(orient="records")]


@router.get("/nature", response_model=list[NaturePoint])
def nature():
    store = get_store()
    g = cmod.nature_distribution(store.payments)
    return [NaturePoint(**r) for r in g.to_dict(orient="records")]


@router.get("/bipartite", response_model=Bipartite)
def bipartite(top_companies: int = Query(10, ge=3, le=20),
              top_physicians: int = Query(40, ge=5, le=120)):
    store = get_store()
    data = cmod.bipartite_engagement(store.payments, top_companies=top_companies,
                                     top_physicians=top_physicians)
    # attach names for the physicians
    data["physician_names"] = [store.name_map.get(n, n) for n in data["physicians"]]
    return Bipartite(**{k: data[k] for k in ("physicians", "companies", "matrix")})
