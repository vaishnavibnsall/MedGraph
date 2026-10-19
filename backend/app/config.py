"""MedGraph configuration: paths and tunable ingest parameters."""
from __future__ import annotations

from pathlib import Path

# backend/app/config.py -> parents[2] == MedGraph root
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
SAMPLE = DATA / "sample"

for _p in (RAW, PROCESSED, SAMPLE):
    _p.mkdir(parents=True, exist_ok=True)

DB_PATH = PROCESSED / "medgraph.sqlite"

# --- Open Payments program-year snapshot we ingest (verified PY2024 publish) ---
OPEN_PAYMENTS_YEAR = 2024
# Publish-stamped file segment; if CMS re-publishes, refresh via tools/recon.py.
OP_PUBLISH_STAMP = "P06302026_06032026"

# Reporting companies kept during general-payment filtering. "MERCK" is the
# anchor (MSD/Merck Sharp & Dohme); the rest enable peer benchmarking.
TARGET_COMPANIES = [
    "MERCK", "PFIZER", "ASTRAZENECA", "NOVARTIS", "LILLY", "JOHNSON & JOHNSON",
    "ABBVIE", "BRISTOL-MYERS", "GSK", "GLAXOSMITHKLINE", "SANOFI", "AMGEN",
    "BAYER", "BOEHRINGER", "TAKEDA", "GILEAD",
]

# General-payment ingest size controls. The full PY2024 file is ~8.3 GB / 15.4M
# rows; we stratify with evenly spaced byte-range chunks so we never download it
# whole while still sampling every region (the file is roughly state-ordered).
GENERAL_CHUNKS = 14          # number of byte-range slices to sample
GENERAL_CHUNK_MB = 105       # target size per slice (MB)
GENERAL_MAX_ROWS = 420_000   # hard cap on stored general-payment rows
GENERAL_WORKERS = 6          # parallel download workers

# Cap rows kept per company so no single payer dominates the sample.
GENERAL_PER_COMPANY_CAP = 60_000

# Research payments: keep rows that yield a usable principal-investigator edge
# or a physician recipient with an NPI.
RESEARCH_MAX_ROWS = 260_000

# ClinicalTrials.gov trial pull (per sponsor term).
CTGOV_MAX_STUDIES = 400
CTGOV_PAGE_SIZE = 100

# Europe PMC bibliometric enrichment for top-KOL candidates.
EPMC_MAX_CANDIDATES = 350

# NPPES enrichment sample (registry is rate-limited; keep small + cached).
NPPES_MAX_LOOKUPS = 400

HTTP_TIMEOUT = 90
HTTP_RETRIES = 4

USER_AGENT = (
    "MedGraph/1.0 (public-data research; academic portfolio project) "
    "python-urllib"
)
