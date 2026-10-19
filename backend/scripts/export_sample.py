"""Export a small, committed CSV sample from the built warehouse.

Produces data/sample/*.csv so the repository is demonstrable (and the tests can
run) without re-downloading gigabytes of Open Payments data. These are real
public records, just down-sampled.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app import config, db  # noqa: E402


def main() -> int:
    if not config.DB_PATH.exists():
        print("Build the dataset first.")
        return 1
    out = config.SAMPLE
    out.mkdir(parents=True, exist_ok=True)
    with db.get_db() as conn:
        pd.read_sql_query(
            "SELECT * FROM payments ORDER BY RANDOM() LIMIT 40000", conn
        ).to_csv(out / "payments_sample.csv", index=False)
        pd.read_sql_query(
            "SELECT * FROM physicians WHERE npi IN "
            "(SELECT DISTINCT npi FROM payments) LIMIT 20000", conn
        ).to_csv(out / "physicians_sample.csv", index=False)
        pd.read_sql_query(
            "SELECT * FROM co_investigator_edges", conn
        ).to_csv(out / "co_investigator_edges.csv", index=False)
        pd.read_sql_query(
            "SELECT * FROM physician_influence ORDER BY rank LIMIT 2000", conn
        ).to_csv(out / "influence_top.csv", index=False)
        pd.read_sql_query(
            "SELECT * FROM trials LIMIT 1500", conn
        ).to_csv(out / "trials_sample.csv", index=False)
    print(f"Sample CSVs written to {out}")
    for f in sorted(out.glob("*.csv")):
        print(f"  {f.name}: {f.stat().st_size/1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
