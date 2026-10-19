"""Verified public data-source URLs + resilient HTTP helpers.

All sources are authoritative government / open-science endpoints. No API keys,
no logins. The CMS Open Payments site sits behind an Akamai WAF that rejects the
default python-urllib User-Agent, so we send a browser-like identity and retry.
"""

from __future__ import annotations

import gzip
import io
import time
import urllib.error
import urllib.request
from typing import Iterator, Optional

from .. import config

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------- CMS Open Payments
# Exact PY2024 download URLs (captured from the metastore, tools/recon8.py).
_OP_BASE = "https://download.cms.gov/openpayments"
OP_GENERAL_2024 = (
    f"{_OP_BASE}/PGYR2024_{config.OP_PUBLISH_STAMP}/"
    f"OP_DTL_GNRL_PGYR2024_{config.OP_PUBLISH_STAMP}.csv"
)
OP_RESEARCH_2024 = (
    f"{_OP_BASE}/PGYR2024_{config.OP_PUBLISH_STAMP}/"
    f"OP_DTL_RSRCH_PGYR2024_{config.OP_PUBLISH_STAMP}.csv"
)
OP_OWNERSHIP_2024 = (
    f"{_OP_BASE}/PGYR2024_{config.OP_PUBLISH_STAMP}/"
    f"OP_DTL_PHYS_OF_PGYR2024_{config.OP_PUBLISH_STAMP}.csv"
)
OP_METASTORE = (
    "https://openpaymentsdata.cms.gov/api/1/metastore/schemas/dataset/items"
    "?show-reference-ids=true"
)

# ---------------------------------------------------------------- ClinicalTrials.gov
CTGOV_STUDIES = "https://clinicaltrials.gov/api/v2/studies"

# ---------------------------------------------------------------- Europe PMC
EPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

# ---------------------------------------------------------------- NPPES
NPPES_API = "https://npiregistry.cms.hhs.gov/api/"


def _request(url: str, headers: Optional[dict] = None, method: str = "GET") -> urllib.request.Request:
    hdrs = {"User-Agent": config.USER_AGENT, "Accept-Encoding": "identity"}
    if headers:
        hdrs.update(headers)
    return urllib.request.Request(url, headers=hdrs, method=method)


def http_get(url: str, headers: Optional[dict] = None, timeout: int | None = None) -> bytes:
    """GET with retries and WAF-aware browser fallback for CMS hosts."""
    timeout = timeout or config.HTTP_TIMEOUT
    last: Exception | None = None
    for attempt in range(config.HTTP_RETRIES):
        try:
            with urllib.request.urlopen(_request(url, headers), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            # 403 from CMS often means the default UA is blocked -> retry as browser.
            if e.code in (403, 429) and "cms.gov" in url:
                try:
                    with urllib.request.urlopen(
                        _request(url, {**(headers or {}), "User-Agent": BROWSER_UA,
                                        "Referer": "https://openpaymentsdata.cms.gov/"},
                                 ), timeout=timeout,
                    ) as r:
                        return r.read()
                except Exception as e2:  # noqa: BLE001
                    last = e2
            time.sleep(1.2 * (attempt + 1))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"GET failed after {config.HTTP_RETRIES} tries: {url} ({last})")


def head_content_length(url: str, timeout: int | None = None) -> Optional[int]:
    timeout = timeout or config.HTTP_TIMEOUT
    # CMS sits behind an Akamai WAF that 403s non-browser clients on HEAD too,
    # so always present a browser identity + referer for cms.gov hosts.
    if "cms.gov" in url:
        hdrs = {
            "User-Agent": BROWSER_UA,
            "Referer": "https://openpaymentsdata.cms.gov/",
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        }
    else:
        hdrs = {"User-Agent": config.USER_AGENT, "Accept-Encoding": "identity"}
    for attempt in range(3):
        try:
            req = _request(url, hdrs, method="HEAD")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                cl = r.headers.get("Content-Length")
                if cl:
                    return int(cl)
                # some hosts omit it on HEAD; try a 1-byte ranged GET
                return _ranged_len(url, timeout)
        except Exception:  # noqa: BLE001
            time.sleep(1.0 * (attempt + 1))
    return None


def _ranged_len(url: str, timeout: int) -> Optional[int]:
    hdrs = {"User-Agent": BROWSER_UA, "Referer": "https://openpaymentsdata.cms.gov/",
            "Accept-Encoding": "identity", "Range": "bytes=0-0"}
    try:
        req = _request(url, hdrs)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            cr = r.headers.get("Content-Range")  # e.g. "0-0/8300000000"
            if cr and "/" in cr:
                return int(cr.split("/")[-1])
    except Exception:  # noqa: BLE001
        return None
    return None


def stream_byte_range(url: str, start: int, end: int, chunk_size: int = 1 << 20) -> Iterator[bytes]:
    """Yield bytes for [start, end] inclusive using an HTTP Range request."""
    req = _request(url, {**({"Range": f"bytes={start}-{end}"} if start or end else {})})
    with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT) as r:
        while True:
            block = r.read(chunk_size)
            if not block:
                break
            yield block


def open_stream(url: str) -> io.TextIOWrapper:
    """Open a plain-CSV HTTP stream for sequential full-file reads."""
    req = _request(url)
    raw = urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT)
    return io.TextIOWrapper(raw, encoding="utf-8", newline="")


def maybe_gunzip(data: bytes) -> bytes:
    if data[:2] == b"\x1f\x8b":
        return gzip.decompress(data)
    return data
