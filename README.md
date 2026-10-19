# MedGraph — HCP/KOL Engagement Network & Compliance Analytics

A full-stack commercial-analytics & medical-affairs intelligence platform built
**entirely on public data**. It unifies pharmaceutical transparency and
open-science sources into a single system for identifying Key Opinion Leaders
(KOLs), mapping the physician↔physician co-investigator network, and running
compliance/spend analytics — the kind of work an SFE (Sales Force Effectiveness)
& Business Insights team does.

> **Data honesty statement.** Every record comes from authoritative public
> government or open-science sources (listed below). **No company/internal/proprietary
> data was used**, and this project is not affiliated with, endorsed by, or
> representative of any company. It is a portfolio/interview artifact scoped for a
> pharma commercial-analytics / medical-affairs context.

---

## Why this project

Pharma rep transparency data (CMS Open Payments) is public but painful: the
general-payments file alone is **~9 GB / 15.4M rows**. Meanwhile the "who knows
whom" signal (who runs trials together) lives in a different system
(ClinicalTrials.gov), and bibliometric output lives in another (Europe PMC).
MedGraph ingests, cleans, entity-resolves and joins them into:

1. a **multi-signal KOL influence index** (transparent, drillable, not a black box),
2. a genuine **co-investigator network graph**, and
3. a **compliance dashboard** (outlier flagging, Merck-vs-peer benchmarking,
   spend concentration, geospatial distribution).

---

## Data sources (all public, no login/key)

| Source | What we take | How we fetch it | Scale |
|---|---|---|---|
| **CMS Open Payments** — General Payments (PY2024) | pharma→physician transfers of value: amount, nature-of-payment, company, specialty, geography | **HTTP byte-range streaming filter** over the ~9 GB file (see *Engineering notes*) → kept ~420k rows across 27 companies | 15.4M rows total |
| **CMS Open Payments** — Research Payments (PY2024) | principal investigators (up to 5/record) → co-investigator network + research engagement | full CSV parse (~693 MB) | 817k rows |
| **ClinicalTrials.gov** v2 API | trials, investigators, enrollment, phases, conditions, sponsor | REST (`/api/v2/studies`) | ~6k trials |
| **Europe PMC** REST API | publication count per investigator (bibliometric signal) | REST (`/search`) | ~350 author profiles |
| **NPPES NPI Registry** API | specialty/taxonomy/geography cross-check | REST (bounded + cached) | ~400 NPIs |

Exact endpoints, verified during reconnaissance (`tools/recon*.py`):
- `https://download.cms.gov/openpayments/PGYR2024_P06302026_06032026/OP_DTL_GNRL_PGYR2024_P06302026_06032026.csv`
- `https://download.cms.gov/openpayments/PGYR2024_P06302026_06032026/OP_DTL_RSRCH_PGYR2024_P06302026_06032026.csv`
- `https://clinicaltrials.gov/api/v2/studies`
- `https://www.ebi.ac.uk/europepmc/webservices/rest/search`
- `https://npiregistry.cms.hhs.gov/api/`

CMS sits behind an Akamai WAF that rejects the default `python-urllib`
User-Agent (HTTP 403), so the ingest presents a browser identity + referer and
retries (`backend/app/ingest/sources.py`).

---

## Architecture

```
MedGraph/
├── backend/                     # Python 3.12 · FastAPI · SQLite · pandas/networkx/scipy
│   ├── app/
│   │   ├── main.py              # FastAPI app + CORS + router mounting
│   │   ├── config.py            # source URLs, target companies, size caps
│   │   ├── db.py                # SQLite schema (11 tables) + connections
│   │   ├── store.py             # in-memory analytics cache (memoised outliers/centrality)
│   │   ├── models.py            # Pydantic response models
│   │   ├── transform.py         # entity resolution → tidy DataFrames
│   │   ├── ingest/
│   │   │   ├── sources.py       # WAF-aware HTTP, byte-range streaming
│   │   │   ├── openpayments.py  # general byte-range filter + research PI extraction
│   │   │   ├── clinicaltrials.py# CT.gov v2 fetch + investigator co-occurrence
│   │   │   ├── europepmc.py     # publication signal
│   │   │   ├── nppes.py         # registry cross-check (bounded + cached)
│   │   │   └── build.py         # end-to-end orchestrator → SQLite
│   │   ├── analytics/
│   │   │   ├── influence.py     # multi-signal KOL index (log1p + min-max + weights)
│   │   │   ├── network.py       # networkx graph, centrality, pruned subgraph, serialize
│   │   │   └── compliance.py    # outlier z-score, benchmarking, Pareto/Gini, geospatial, bipartite
│   │   └── api/                 # routers: kol · network · compliance · physician · meta
│   ├── scripts/                 # smoke_test.py · export_sample.py
│   └── tests/                   # 42 pytest tests (offline, synthetic fixture)
├── frontend/                    # React 18 · TypeScript · Vite · Recharts · react-force-graph
│   └── src/
│       ├── pages/               # Dashboard · Leaderboard · Network · Compliance · Physician
│       ├── api/client.ts        # typed fetch wrapper
│       └── types.ts             # shared API types
├── data/
│   ├── raw/                     # downloaded source files (gitignored; rebuilt by pipeline)
│   ├── processed/               # medgraph.sqlite (gitignored)
│   └── sample/                  # small committed CSVs → offline demo
└── tools/                       # data reconnaissance scripts
```

**Data flow:** `ingest` (I/O) → `transform` (cleaning / entity resolution) →
`analytics` (pure pandas/networkx math) → `store` (memoised) → `api` (FastAPI) →
`frontend` (React). Each layer is independently testable; the analytics are pure
functions with no I/O.

---

## The KOL influence index (methodology)

Four independent public signals, each **log1p-transformed** (these fields are
heavily right-skewed) then **min-max scaled** to [0,1] and combined into a
transparent 0–100 composite:

| Signal | Weight | Source | Rationale |
|---|---|---|---|
| Publication | 0.30 | Europe PMC | bibliometric output / scientific influence |
| Trial engagement | 0.30 | Open Payments research (PI studies + scope proxy) | clinical-trial leadership |
| Network centrality | 0.25 | co-investigator graph (degree + weighted degree) | professional reach |
| Payment tier | 0.15 | Open Payments general (received, log-scaled) | industry engagement |

```
score = 100 · (0.30·pub + 0.30·trial + 0.25·network + 0.15·payment)
```

Every component is exposed via `/api/kol/breakdown/{npi}` so a reviewer can audit
any KOL's score. Weights live in one place (`analytics/influence.py`) and are
unit-tested to sum to 1.

---

## Compliance analytics (methodology)

- **Payment outlier flagging** — robust z-score within each *(specialty ×
  nature-of-payment)* cohort: `z = 0.6745·(x − median)/MAD`. Robust to extreme
  values (unlike mean/σ). Sparse cohorts fall back to global statistics.
- **Company benchmarking** — per-physician spend pivoted by company, then Merck
  (anchor) vs the whole market by specialty → share-of-wallet / SFE targeting lens.
- **Concentration** — Lorenz/Pareto curve, top-1%/top-10% spend share, and Gini
  coefficient over per-physician totals.
- **Geospatial** — per-state and per-metro spend totals / averages.
- **Bipartite engagement** — company↔physician matrix for the engagement view.

---

## Reproduce it

### 1. Backend
```bash
cd backend
python -m venv .venv && .\.venv\Scripts\python -m pip install -r requirements.txt   # Windows
python -m app.ingest.build          # full build (~15–20 min; streams the 9 GB file once, then caches)
python scripts/smoke_test.py        # verify the warehouse
python -m pytest -q                 # 42 tests, offline
uvicorn app.main:app --reload --port 8000
```
`python -m app.ingest.build --quick` produces a tiny sample in ~1 min (CI/smoke).
The general-payment filter caches to `data/processed/general_*.pkl`, so rebuilds
skip the 9 GB stream.

### 2. Frontend
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173  (proxies /api → :8000)
npm run build      # green production build → dist/
```

### 3. API (interactive docs at `/docs`)
| Endpoint | Purpose |
|---|---|
| `GET /api/health` · `/api/stats` | readiness + dataset stats |
| `GET /api/kol/leaderboard` | ranked KOLs with filters (specialty/state/company) |
| `GET /api/kol/breakdown/{npi}` | auditable influence decomposition |
| `GET /api/network/graph` | pruned co-investigator subgraph (nodes+links) |
| `GET /api/network/ego/{npi}` | a physician's collaborators |
| `GET /api/compliance/outliers` · `/outliers/top` | robust-z outlier flags |
| `GET /api/compliance/benchmark` | Merck-vs-market by specialty |
| `GET /api/compliance/pareto` · `/concentration` | spend concentration |
| `GET /api/compliance/geospatial` · `/metro` · `/nature` | distributions |
| `GET /api/compliance/bipartite` | company↔physician engagement |
| `GET /api/physician/{npi}` | full drill-down profile |

---

## Engineering notes (the interesting parts)

- **Streaming a 9 GB file without downloading it.** `openpayments.py` issues
  HTTP **Range** requests for evenly spaced byte slices across the file,
  downloads them in parallel (`ThreadPoolExecutor`), and filters rows in-flight
  to a curated company set (Merck + peers), keeping only physician/NPP recipients.
  Because the file is roughly state-ordered, spread sampling preserves geographic,
  company and specialty diversity. A per-company cap prevents any one payer from
  dominating. This turns a 9 GB / 68-minute sequential download into a bounded,
  resumable, ~12-minute stratified sample.
- **Co-investigator network from two sources.** Open Payments *research* records
  name up to 5 principal investigators → NPI-linked co-investigation edges (genuine
  but sparse: ~0.3% of records have 2+ PIs). ClinicalTrials.gov *investigators*
  add a denser layer; official names are normalised (credentials stripped, generic
  placeholders like "Medical Director" dropped) and resolved to NPIs where the
  investigator is also a paid recipient — unresolved officials stay as `OBS:<name>`
  nodes so the network keeps its true shape.
- **Entity resolution.** NPI is the join key for Open Payments ↔ NPPES. Europe PMC
  has no NPI, so publication counts are matched by `(last name, first initial)` —
  best-effort and documented as a soft signal (author-name ambiguity is real).
- **WAF resilience.** CMS 403s default clients; the HTTP layer retries with a
  browser identity + referer and falls back to ranged GETs for content length.

---

## Limitations (stated honestly)

- The general-payments layer is a **stratified byte-range sample**, not the full
  15.4M rows — representative, not exhaustive. The pipeline code scales to the
  full file (increase `GENERAL_CHUNKS` / raise the caps).
- Publication matching is by author name (fuzzy); disambiguation is heuristic.
- Trial↔physician linkage uses Open Payments research PI records (NPI-linked) as
  the trial-influence proxy; ClinicalTrials.gov officials don't carry NPIs, so
  that layer is name-resolved and partly `OBS:`-keyed.
- Figures are illustrative of public transparency data, not investment/compliance
  advice, and carry no implication about any specific company's practices.

---

## Tests

`backend/tests/` — **42 tests**, all offline against a deterministic synthetic
fixture (`conftest.py`), covering the transform, influence math, network
centralities, every compliance statistic, the ingest parsers, and the full API
surface (leaderboard filters, network, outliers, benchmark, Pareto, physician
drill-down, 404s).

```bash
cd backend && python -m pytest -q
# ..........................................  [100%]  42 passed
```

---

## License / data terms

Code: MIT. Data: US public data (CMS Open Payments, ClinicalTrials.gov, NPPES)
and Europe PMC (used under its open license) — see each source's terms. No
redistribution of bulk source files is included in this repository.
