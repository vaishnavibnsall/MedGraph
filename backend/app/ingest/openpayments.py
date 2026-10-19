"""CMS Open Payments ingest.

* General payments (PY2024, ~8.3 GB) — stratified byte-range filtering. Instead
  of downloading the whole file we pull evenly spaced byte-range slices across
  its full length (the file is roughly state-ordered, so spread sampling keeps
  geographic + company + specialty diversity), keep only TARGET_COMPANIES rows
  for physician/NPP recipients, and cap per company. Uses HTTP Range (206).
* Research payments (PY2024, ~693 MB) — full parse; extracts principal
  investigators (up to 5 per record) which yields the physician<->physician
  co-investigator edges and a research/clinical-trial engagement signal.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from .. import config
from . import sources

log = logging.getLogger("medgraph.ingest.openpayments")

_TARGET_RE = re.compile(
    "|".join(re.escape(t) for t in config.TARGET_COMPANIES), re.IGNORECASE
)


def _norm_money(v: str) -> float:
    try:
        return float(str(v).replace("$", "").replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


@dataclass
class GeneralRow:
    npi: str
    profile_id: str
    first: str
    middle: str
    last: str
    suffix: str
    rtype: str            # covered recipient type (physician / NPP)
    specialty: str
    prim_types: str
    street: str
    city: str
    state: str
    zip_code: str
    country: str
    company: str
    company_id: str
    amount: float
    date: str
    n_payments: int
    form: str
    nature: str
    program_year: str

    def key(self) -> str:
        return self.npi or f"{self.last}|{self.first}"


# ----------------------------------------------------------------------------- general
@dataclass
class _ChunkResult:
    rows: List[GeneralRow] = field(default_factory=list)
    scanned_bytes: int = 0
    matched: int = 0


_GENERAL_HEADER = None


def _filter_chunk(url: str, start: int, end: int) -> _ChunkResult:
    """Download one byte-range slice and keep target-company physician rows.

    Handles the fact that a slice can begin/end mid-record: we drop the first
    (possibly partial) line unless start==0, and stop at the first line that
    crosses `end`.
    """
    global _GENERAL_HEADER
    res = _ChunkResult()
    buf = ""
    first_line = True
    for block in sources.stream_byte_range(url, start, end):
        res.scanned_bytes += len(block)
        buf += block.decode("utf-8", "replace")
        while True:
            nl = buf.find("\n")
            if nl == -1:
                break
            line = buf[:nl]
            buf = buf[nl + 1:]
            if first_line:
                # this is the file header only when our slice starts at byte 0
                if start == 0 and line:
                    _set_header(line)
                first_line = False
                continue
            if not line.strip():
                continue
            row = _parse_general_line(line)
            if row is not None:
                res.rows.append(row)
                res.matched += 1
    return res


def _set_header(line: str) -> None:
    global _GENERAL_HEADER
    _GENERAL_HEADER = next(csv.reader(io.StringIO(line)))


def _idx() -> Dict[str, int]:
    return {h: i for i, h in enumerate(_GENERAL_HEADER or [])}


def _parse_general_line(line: str) -> Optional[GeneralRow]:
    global _GENERAL_HEADER
    if _GENERAL_HEADER is None:
        return None
    try:
        parts = next(csv.reader(io.StringIO(line)))
    except StopIteration:
        return None
    if len(parts) < 45:
        return None
    ix = _idx()
    def g(name: str, default: str = "") -> str:
        i = ix.get(name)
        if i is None or i >= len(parts):
            return default
        return parts[i]

    company = g("Submitting_Applicable_Manufacturer_or_Applicable_GPO_Name") or g(
        "Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Name"
    )
    if not _TARGET_RE.search(company):
        return None
    rtype = g("Covered_Recipient_Type")
    npi = g("Covered_Recipient_NPI").strip()
    # keep physician + non-physician practitioner recipients that carry an NPI
    if not npi:
        return None
    if "Teaching Hospital" in rtype:
        return None
    amount = _norm_money(g("Total_Amount_of_Payment_USDollars"))
    try:
        n_pay = int(float(g("Number_of_Payments_Included_in_Total_Amount") or 0))
    except ValueError:
        n_pay = 1
    return GeneralRow(
        npi=npi,
        profile_id=g("Covered_Recipient_Profile_ID"),
        first=g("Covered_Recipient_First_Name"),
        middle=g("Covered_Recipient_Middle_Name"),
        last=g("Covered_Recipient_Last_Name"),
        suffix=g("Covered_Recipient_Name_Suffix"),
        rtype=rtype,
        specialty=g("Covered_Recipient_Specialty_1"),
        prim_types=g("Covered_Recipient_Primary_Type_1"),
        street=g("Recipient_Primary_Business_Street_Address_Line1"),
        city=g("Recipient_City"),
        state=g("Recipient_State"),
        zip_code=g("Recipient_Zip_Code"),
        country=g("Recipient_Country"),
        company=company,
        company_id=g("Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_ID"),
        amount=amount,
        date=g("Date_of_Payment"),
        n_payments=n_pay,
        form=g("Form_of_Payment_or_Transfer_of_Value"),
        nature=g("Nature_of_Payment_or_Transfer_of_Value"),
        program_year=g("Program_Year") or str(config.OPEN_PAYMENTS_YEAR),
    )


def ingest_general(limit_rows: Optional[int] = None) -> List[GeneralRow]:
    """Stratified byte-range filter over the full general-payments file.

    Result is cached to disk so incremental rebuilds skip the ~9 GB stream.
    """
    import pickle
    limit_rows = limit_rows or config.GENERAL_MAX_ROWS
    cache = config.PROCESSED / f"general_{config.OPEN_PAYMENTS_YEAR}_{limit_rows}.pkl"
    if cache.exists():
        try:
            with open(cache, "rb") as f:
                rows = pickle.load(f)
            log.info("general: loaded %d rows from cache %s", len(rows), cache.name)
            return rows
        except Exception as e:  # noqa: BLE001
            log.warning("general cache unreadable (%s); refetching", e)

    url = sources.OP_GENERAL_2024
    total = sources.head_content_length(url)
    if not total:
        # fall back to sequential streaming filter
        log.warning("no Content-Length; falling back to sequential filter")
        rows = _ingest_general_sequential(url, limit_rows)
        _cache_rows(rows, cache)
        return rows

    n_chunks = config.GENERAL_CHUNKS
    chunk_bytes = min(config.GENERAL_CHUNK_MB * 1_000_000, total // n_chunks + 1)
    slices = []
    stride = total // n_chunks
    for i in range(n_chunks):
        start = i * stride
        end = min(start + chunk_bytes, total) if i < n_chunks - 1 else total - 1
        if start >= total:
            break
        slices.append((start, end))
    log.info("general: %d byte-range slices over %.1f GB", len(slices), total / 1e9)

    # header must be known before workers parse -> pull first line of slice 0
    _prime_header(url)

    per_company: Counter = Counter()
    kept: List[GeneralRow] = []
    with ThreadPoolExecutor(max_workers=config.GENERAL_WORKERS) as pool:
        futs = {pool.submit(_filter_chunk, url, s, e): (s, e) for (s, e) in slices}
        for fut in as_completed(futs):
            r = fut.result()
            for row in r.rows:
                if per_company[row.company] >= config.GENERAL_PER_COMPANY_CAP:
                    continue
                if len(kept) >= limit_rows:
                    continue
                per_company[row.company] += 1
                kept.append(row)
    log.info("general: kept %d rows across %d companies", len(kept), len(per_company))
    _cache_rows(kept, cache)
    return kept


def _cache_rows(rows: List[GeneralRow], cache) -> None:
    import pickle
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        with open(cache, "wb") as f:
            pickle.dump(rows, f)
        log.info("general: cached %d rows -> %s", len(rows), cache.name)
    except Exception as e:  # noqa: BLE001
        log.warning("general cache write failed: %s", e)


def _prime_header(url: str) -> None:
    """Read just enough of the file to learn the CSV header."""
    buf = ""
    for block in sources.stream_byte_range(url, 0, 65535):
        buf += block.decode("utf-8", "replace")
        nl = buf.find("\n")
        if nl != -1:
            _set_header(buf[:nl])
            return


def _ingest_general_sequential(url: str, limit_rows: int) -> List[GeneralRow]:
    kept: List[GeneralRow] = []
    per_company: Counter = Counter()
    reader = csv.reader(sources.open_stream(url))
    header = next(reader, None)
    if header:
        _set_header(",".join(_csv_escape(h) for h in header))
    for parts in reader:
        if len(parts) < 45:
            continue
        # rebuild via the shared parser by re-joining is lossy; parse directly
        row = _parse_parts(parts)
        if row is None:
            continue
        if per_company[row.company] >= config.GENERAL_PER_COMPANY_CAP:
            continue
        if len(kept) >= limit_rows:
            break
        per_company[row.company] += 1
        kept.append(row)
    return kept


def _csv_escape(h: str) -> str:
    return '"' + h.replace('"', '""') + '"' if ("," in h or '"' in h) else h


def _parse_parts(parts: List[str]) -> Optional[GeneralRow]:
    global _GENERAL_HEADER
    saved = _GENERAL_HEADER
    # emulate header context for g()
    _GENERAL_HEADER = saved
    ix = _idx()
    def g(name: str, default: str = "") -> str:
        i = ix.get(name)
        return parts[i] if (i is not None and i < len(parts)) else default
    company = g("Submitting_Applicable_Manufacturer_or_Applicable_GPO_Name") or g(
        "Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Name")
    if not _TARGET_RE.search(company):
        return None
    npi = g("Covered_Recipient_NPI").strip()
    rtype = g("Covered_Recipient_Type")
    if not npi or "Teaching Hospital" in rtype:
        return None
    try:
        n_pay = int(float(g("Number_of_Payments_Included_in_Total_Amount") or 0))
    except ValueError:
        n_pay = 1
    return GeneralRow(
        npi=npi, profile_id=g("Covered_Recipient_Profile_ID"),
        first=g("Covered_Recipient_First_Name"), middle=g("Covered_Recipient_Middle_Name"),
        last=g("Covered_Recipient_Last_Name"), suffix=g("Covered_Recipient_Name_Suffix"),
        rtype=rtype, specialty=g("Covered_Recipient_Specialty_1"),
        prim_types=g("Covered_Recipient_Primary_Type_1"),
        street=g("Recipient_Primary_Business_Street_Address_Line1"),
        city=g("Recipient_City"), state=g("Recipient_State"),
        zip_code=g("Recipient_Zip_Code"), country=g("Recipient_Country"),
        company=company, company_id=g("Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_ID"),
        amount=_norm_money(g("Total_Amount_of_Payment_USDollars")), date=g("Date_of_Payment"),
        n_payments=n_pay, form=g("Form_of_Payment_or_Transfer_of_Value"),
        nature=g("Nature_of_Payment_or_Transfer_of_Value"),
        program_year=g("Program_Year") or str(config.OPEN_PAYMENTS_YEAR),
    )


# ----------------------------------------------------------------------------- research
@dataclass
class ResearchPayment:
    recipient_npi: str
    recipient_name: str
    recipient_specialty: str
    recipient_state: str
    company: str
    form: str
    amount: float
    date: str
    study_id: str          # ClinicalTrial / study context id if present
    program_year: str
    pis: List[Tuple[str, str]] = field(default_factory=list)  # (npi, "First Last")


def _parse_research(parts: List[str], ix: Dict[str, int]) -> Optional[ResearchPayment]:
    def g(name: str, default: str = "") -> str:
        i = ix.get(name)
        return parts[i] if (i is not None and i < len(parts)) else default

    company = g("Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Name")
    amount = _norm_money(g("Total_Amount_of_Payment_USDollars"))
    rnpi = g("Covered_Recipient_NPI").strip()
    rname = " ".join(x for x in [g("Covered_Recipient_First_Name"),
                                 g("Covered_Recipient_Last_Name")] if x).strip()

    pis: List[Tuple[str, str]] = []
    for n in range(1, 6):
        pnpi = g(f"Principal_Investigator_{n}_NPI").strip()
        pf = g(f"Principal_Investigator_{n}_First_Name")
        pl = g(f"Principal_Investigator_{n}_Last_Name")
        if pnpi and (pf or pl):
            pis.append((pnpi, f"{pf} {pl}".strip()))

    study_id = g("Principal_Investigator_1_NPI") and g("Covered_Recipient_Profile_ID")
    # some rows carry a research project / study reference
    study_ref = g("Name_of_Study") or g("Study_or_Research_Project_ID") or ""

    if not rnpi and not pis:
        return None
    return ResearchPayment(
        recipient_npi=rnpi, recipient_name=rname,
        recipient_specialty=g("Covered_Recipient_Specialty_1"),
        recipient_state=g("Recipient_State"), company=company,
        form=g("Form_of_Payment_or_Transfer_of_Value"), amount=amount,
        date=g("Date_of_Payment"), study_id=study_ref or study_id or "",
        program_year=g("Program_Year") or str(config.OPEN_PAYMENTS_YEAR), pis=pis,
    )


def ingest_research_from_path(path) -> List[ResearchPayment]:
    """Parse the downloaded research CSV, keeping rows with a PI or recipient NPI."""
    out: List[ResearchPayment] = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return out
        ix = {h: i for i, h in enumerate(header)}
        for parts in reader:
            if len(parts) < 20:
                continue
            rp = _parse_research(parts, ix)
            if rp is None:
                continue
            out.append(rp)
            if len(out) >= config.RESEARCH_MAX_ROWS:
                break
    log.info("research: parsed %d rows from %s", len(out), path)
    return out


def build_co_investigator_edges(
    research: Iterable[ResearchPayment],
) -> Tuple[Dict[Tuple[str, str], dict], Counter]:
    """Physician<->physician edges from shared research engagements.

    Every research record lists up to 5 principal investigators. Any two PIs on
    the same record are treated as co-investigators on that study; we weight the
    edge by the number of shared engagements and the summed research amount.
    The returned Counter is the *unique-neighbour* degree per physician.
    """
    edges: Dict[Tuple[str, str], dict] = {}
    neighbors: Dict[str, set] = defaultdict(set)
    for rp in research:
        if len(rp.pis) < 2:
            continue
        pis = sorted({npi for npi, _ in rp.pis if npi})
        for i in range(len(pis)):
            for j in range(i + 1, len(pis)):
                a, b = pis[i], pis[j]
                key = (a, b)
                rec = edges.setdefault(key, {"weight": 0, "amount": 0.0, "companies": set()})
                rec["weight"] += 1
                rec["amount"] += rp.amount
                if rp.company:
                    rec["companies"].add(rp.company)
                neighbors[a].add(b)
                neighbors[b].add(a)
    degree = Counter({n: len(nbrs) for n, nbrs in neighbors.items()})
    return edges, degree
