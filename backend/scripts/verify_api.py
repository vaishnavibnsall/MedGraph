"""Verify live API endpoints return MedGraph-shaped payloads.

Usage: python scripts/verify_api.py [base_url] (default http://127.0.0.1:8010)
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"

ENDPOINTS = [
    "/api/health",
    "/api/stats",
    "/api/kol/leaderboard?limit=3",
    "/api/network/stats",
    "/api/compliance/outliers?limit=3",
    "/api/compliance/benchmark?company=MERCK&limit=3",
    "/api/compliance/concentration?company=MERCK",
    "/api/compliance/pareto?company=MERCK",
    "/api/compliance/geospatial?company=MERCK&limit=5",
    "/api/compliance/metro?company=MERCK&limit=5",
    "/api/compliance/nature?company=MERCK",
    "/api/compliance/bipartite?company=MERCK&limit=10",
]


def get(path: str, timeout: float = 60.0):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as resp:
        return json.loads(resp.read())


def wait_for_server() -> bool:
    for _ in range(30):
        try:
            urllib.request.urlopen(BASE + "/api/health", timeout=3)
            return True
        except Exception:
            time.sleep(1)
    return False


def main() -> int:
    if not wait_for_server():
        print(f"FAIL server not reachable at {BASE}")
        return 1

    failures = 0

    for ep in ENDPOINTS:
        try:
            data = get(ep)
            if isinstance(data, list):
                detail = f"list[{len(data)}]"
            else:
                keys = list(data)[:8]
                detail = str({k: data[k] for k in keys})[:200]
            print(f"OK  {ep} -> {detail}")
        except urllib.error.HTTPError as exc:
            failures += 1
            print(f"ERR {ep} -> HTTP {exc.code}: {exc.read()[:150]!r}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ERR {ep} -> {exc}")

    # physician drill-down using an NPI from the leaderboard
    try:
        top = get("/api/kol/leaderboard?limit=1")
        npi = top["rows"][0]["npi"]
        profile = get(f"/api/physician/{npi}")
        print(f"OK  /api/physician/{npi} -> keys={list(profile.keys())}")
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print(f"ERR physician -> {exc}")

    # network graph payload
    try:
        graph = get("/api/network/graph?limit_nodes=50")
        n_nodes = len(graph.get("nodes", []))
        n_links = len(graph.get("links", []))
        print(f"OK  /api/network/graph -> nodes={n_nodes} links={n_links}")
        if n_nodes == 0 or n_links == 0:
            failures += 1
            print("ERR graph payload empty")
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print(f"ERR graph -> {exc}")

    print(f"\n{'PASS' if failures == 0 else 'FAIL'}: {failures} failure(s)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
