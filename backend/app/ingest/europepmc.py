"""Europe PMC REST API ingest — bibliometric influence per investigator.

For the top KOL candidates we query Europe PMC by author name to obtain a
publication count (and first/last publication years) used as one signal in the
multi-signal influence index. Author-name matching is inherently fuzzy, so this
is treated as a soft signal and bounded to the top candidates to stay polite to
the public API.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import List
from urllib.parse import quote

from .. import config
from . import sources

log = logging.getLogger("medgraph.ingest.europepmc")


@dataclass
class PublicationProfile:
    query_name: str
    hit_count: int
    first_year: int | None
    last_year: int | None
    top_journals: List[str]


def _build_query(last: str, first: str) -> str:
    # Europe PMC author syntax: AUTH:"Lastname F" — use last name + first initial.
    initial = (first[:1] if first else "").upper()
    author = f"{last} {initial}".strip()
    return f'AUTH:"{author}"'


def fetch_publication_profile(last: str, first: str,
                              extra: str = "") -> PublicationProfile | None:
    if not last:
        return None
    q = _build_query(last, first)
    if extra:
        q = f"{q} AND {extra}"
    url = (f"{sources.EPMC_SEARCH}?query={quote(q)}&format=json&pageSize=1"
           f"&resultType=core")
    try:
        raw = sources.http_get(url)
        data = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        log.debug("epmc query failed %r: %s", q, e)
        return None
    hit = int(data.get("hitCount", 0) or 0)
    results = data.get("resultList", {}).get("result", [])
    years = [int(r["pubYear"]) for r in results if str(r.get("pubYear", "")).isdigit()]
    journals = [r.get("journalTitle", "") for r in results if r.get("journalTitle")]
    return PublicationProfile(
        query_name=f"{last}, {first}".strip(", "),
        hit_count=hit,
        first_year=min(years) if years else None,
        last_year=max(years) if years else None,
        top_journals=journals[:3],
    )


def enrich_candidates(cands: List[dict]) -> List[PublicationProfile]:
    """cands: [{'last':..,'first':..,'npi':..}] -> profiles (bounded, throttled)."""
    out: List[PublicationProfile] = []
    bounded = cands[: config.EPMC_MAX_CANDIDATES]
    for i, c in enumerate(bounded):
        prof = fetch_publication_profile(c.get("last", ""), c.get("first", ""))
        if prof:
            out.append(prof)
        if i % 25 == 0:
            time.sleep(0.4)  # be polite to the public endpoint
    log.info("epmc: enriched %d candidates", len(out))
    return out
