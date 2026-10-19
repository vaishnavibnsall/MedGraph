"""Meta endpoints: health, dataset stats, trials."""
from __future__ import annotations

from fastapi import APIRouter, Query

from .. import config
from ..models import Health, Stats
from ..store import get_store

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health", response_model=Health)
def health():
    store = get_store()
    return Health(
        status="ok" if store.loaded else "no-data",
        db=str(config.DB_PATH),
        physicians=store.stats.get("physicians", 0),
        payments=store.stats.get("payments", 0),
        edges=store.stats.get("edges", 0),
        trials=store.stats.get("trials", 0),
    )


@router.get("/stats", response_model=Stats)
def stats():
    store = get_store()
    return Stats(**store.stats)


@router.get("/trials")
def trials(sponsor: str | None = None, limit: int = Query(50, ge=1, le=300)):
    store = get_store()
    t = store.trials
    if sponsor:
        t = t[t["sponsor"].str.contains(sponsor, case=False, na=False)]
    t = t.sort_values("enrollment", ascending=False).head(limit)
    return [{
        "nct_id": r["nct_id"], "title": r["title"], "status": r["status"],
        "sponsor": r["sponsor"], "phases": r["phases"], "conditions": r["conditions"],
        "enrollment": int(r["enrollment"]), "study_type": r["study_type"],
    } for _, r in t.iterrows()]


@router.get("/trials/summary")
def trial_summary():
    store = get_store()
    t = store.trials
    if not len(t):
        return {"n_trials": 0, "by_sponsor": [], "total_enrollment": 0, "by_phase": []}
    by_sponsor = (t.groupby("sponsor")["enrollment"]
                  .agg(["count", "sum"]).reset_index()
                  .sort_values("count", ascending=False).head(10))
    phase_rows = []
    for _, r in t.iterrows():
        for ph in str(r.get("phases", "")).split("|"):
            if ph and ph != "NA":
                phase_rows.append(ph)
    from collections import Counter
    pc = Counter(phase_rows)
    return {
        "n_trials": int(len(t)),
        "total_enrollment": int(t["enrollment"].sum()),
        "by_sponsor": [{"sponsor": r["sponsor"], "count": int(r["count"]),
                        "enrollment": int(r["sum"])} for _, r in by_sponsor.iterrows()],
        "by_phase": [{"phase": k, "count": v} for k, v in pc.most_common(8)],
    }
