"""MedGraph FastAPI application.

Run locally:
    uvicorn app.main:app --reload --port 8000   (from backend/)
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import kol, meta, network, physician, compliance
from .store import get_store

app = FastAPI(
    title="MedGraph API",
    description=(
        "HCP/KOL Engagement Network & Compliance Analytics built on public data "
        "(CMS Open Payments, ClinicalTrials.gov, Europe PMC, NPPES)."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:4173", "http://127.0.0.1:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(kol.router)
app.include_router(network.router)
app.include_router(compliance.router)
app.include_router(physician.router)


@app.on_event("startup")
def _startup() -> None:
    # warm the in-memory store so first requests are fast
    get_store()
