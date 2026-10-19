"""NPPES NPI Registry API ingest — optional specialty/geography enrichment.

The NPPES registry is rate-limited, so we only look up a bounded sample of NPIs
and cache results to disk. Open Payments already carries specialty/state, so this
acts as an independent cross-check and adds taxonomy detail where available.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import List
from urllib.parse import urlencode

from .. import config
from . import sources

log = logging.getLogger("medgraph.ingest.nppes")

CACHE_PATH = config.PROCESSED / "nppes_cache.json"


@dataclass
class NppesRecord:
    npi: str
    first: str
    last: str
    credential: str
    primary_specialty: str
    taxonomy: str
    state: str
    city: str
    country: str
    enumeration_type: str


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    try:
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.debug("nppes cache save failed: %s", e)


def lookup_npi(npi: str) -> NppesRecord | None:
    params = urlencode({"version": "2.1", "number": npi, "limit": "1"})
    url = f"{sources.NPPES_API}?{params}"
    try:
        data = json.loads(sources.http_get(url))
    except Exception as e:  # noqa: BLE001
        log.debug("nppes lookup failed %s: %s", npi, e)
        return None
    results = data.get("results", [])
    if not results:
        return None
    r = results[0]
    basic = r.get("basic", {})
    tax = r.get("taxonomies", [])
    primary_tax = next((t.get("desc", "") for t in tax if t.get("primary")), "")
    loc = next((a for a in r.get("addresses", []) if a.get("address_purpose") == "LOCATION"), {})
    return NppesRecord(
        npi=npi, first=basic.get("first_name", ""), last=basic.get("last_name", ""),
        credential=basic.get("credential", ""),
        primary_specialty=tax[0].get("desc", "") if tax else "",
        taxonomy=primary_tax, state=loc.get("state", ""), city=loc.get("city", ""),
        country=loc.get("country_name", ""), enumeration_type=basic.get("enumeration_type", ""),
    )


def enrich_npis(npis: List[str]) -> List[NppesRecord]:
    cache = _load_cache()
    out: List[NppesRecord] = []
    bounded = npis[: config.NPPES_MAX_LOOKUPS]
    for i, npi in enumerate(bounded):
        if npi in cache:
            d = cache[npi]
            out.append(NppesRecord(**d))
            continue
        rec = lookup_npi(npi)
        if rec:
            out.append(rec)
            cache[npi] = rec.__dict__
        time.sleep(0.15)  # registry rate limit courtesy
        if i % 20 == 0:
            _save_cache(cache)
    _save_cache(cache)
    log.info("nppes: enriched %d NPIs", len(out))
    return out
