"""Smoke test: verify the built MedGraph SQLite warehouse is sane.

Run after `python -m app.ingest.build`:
    python scripts/smoke_test.py
Exits non-zero if any invariant fails. Useful in CI or before demoing.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, db  # noqa: E402


def check(name: str, cond: bool, detail: str = "") -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}{(' — ' + detail) if detail else ''}")
    return cond


def main() -> int:
    if not config.DB_PATH.exists():
        print(f"DB not found at {config.DB_PATH}. Run the build first.")
        return 1

    ok = True
    with db.get_db() as conn:
        def scalar(sql: str):
            return conn.execute(sql).fetchone()[0]

        n_phys = scalar("SELECT COUNT(*) FROM physicians")
        n_pay = scalar("SELECT COUNT(*) FROM payments")
        n_comp = scalar("SELECT COUNT(*) FROM companies")
        n_edges = scalar("SELECT COUNT(*) FROM co_investigator_edges")
        n_research = scalar("SELECT COUNT(*) FROM research_payments")
        n_trials = scalar("SELECT COUNT(*) FROM trials")
        n_infl = scalar("SELECT COUNT(*) FROM physician_influence")
        spend = scalar("SELECT COALESCE(SUM(amount),0) FROM payments")
        merck = scalar("SELECT COUNT(*) FROM payments WHERE company_name LIKE '%MERCK%'")

        ok &= check("physicians loaded", n_phys > 1000, f"{n_phys:,}")
        ok &= check("payments loaded", n_pay > 50000, f"{n_pay:,}")
        ok &= check("companies loaded", n_comp >= 10, f"{n_comp}")
        ok &= check("research payments loaded", n_research > 1000, f"{n_research:,}")
        ok &= check("trials loaded", n_trials > 100, f"{n_trials:,}")
        ok &= check("influence table populated", n_infl > 1000, f"{n_infl:,}")
        ok &= check("total spend > 0", spend > 0, f"${spend:,.0f}")
        ok &= check("Merck present (anchor)", merck > 0, f"{merck:,} payments")

        # referential sanity: every payment npi exists in physicians (sample)
        orphans = scalar(
            "SELECT COUNT(*) FROM payments p WHERE NOT EXISTS "
            "(SELECT 1 FROM physicians ph WHERE ph.npi = p.npi) LIMIT 1")
        ok &= check("payments reference known physicians", orphans == 0, f"{orphans} orphans")

        # influence ranks are dense 1..n
        min_rank = scalar("SELECT MIN(rank) FROM physician_influence")
        max_rank = scalar("SELECT MAX(rank) FROM physician_influence")
        ok &= check("influence ranks start at 1", min_rank == 1, f"min={min_rank}")
        ok &= check("influence rank spread sane", max_rank <= n_infl, f"max={max_rank}")

        # network
        if n_edges:
            avg_degree = scalar(
                "SELECT 2.0*COUNT(*)/(SELECT COUNT(DISTINCT npi_a) FROM co_investigator_edges) "
                "FROM co_investigator_edges")
            ok &= check("network has edges", n_edges > 0, f"{n_edges:,} edges")
        else:
            print("[WARN] co-investigator graph is empty (sparse research PIs)")

    print("\n" + ("SMOKE TEST PASSED" if ok else "SMOKE TEST FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
