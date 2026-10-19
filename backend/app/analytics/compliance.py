"""Compliance analytics over Open Payments general payments.

Implements the SFE / business-insights style checks a commercial-analytics team
would run on transparency data:

  * outlier flagging      — robust z-score (vs specialty x nature-of-payment median)
  * company benchmarking  — Merck vs peers on per-physician spend by specialty
  * Pareto / concentration — share of spend captured by the top X% of physicians
  * geospatial spend      — per-state and per-metro totals / averages
  * bipartite engagement  — company -> physician engagement matrix

All functions take tidy pandas frames and return DataFrames / dicts, so they are
unit-testable and API-reusable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# --------------------------------------------------------------------- outliers
def flag_payment_outliers(payments: pd.DataFrame, z_thresh: float = 4.0,
                          min_group: int = 8) -> pd.DataFrame:
    """Flag unusually large payments within (specialty, nature) cohorts.

    Uses a robust z-score based on the median/MAD so a handful of extreme
    transfers don't mask their own outliers. Groups smaller than `min_group`
    are compared against the global distribution instead.
    """
    df = payments.copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["specialty"] = df["specialty"].fillna("Unknown")
    df["nature"] = df["nature"].fillna("Unknown")

    grouped = df.groupby(["specialty", "nature"])["amount"]
    med = grouped.transform("median")
    mad = grouped.transform(lambda s: (s - s.median()).abs().median())
    n = grouped.transform("size")

    # fall back to global stats for sparse cohorts
    glob_med = df["amount"].median()
    glob_mad = (df["amount"] - glob_med).abs().median()
    med = med.where(n >= min_group, glob_med)
    mad = mad.where(n >= min_group, glob_mad)

    mad = mad.replace(0, np.nan)
    robust_z = 0.6745 * (df["amount"] - med) / mad
    robust_z = robust_z.fillna(0.0)

    df["cohort_median"] = med.round(2)
    df["robust_z"] = robust_z.round(2)
    df["is_outlier"] = robust_z >= z_thresh
    return df


def outlier_summary(flagged: pd.DataFrame, top: int = 15) -> dict:
    out = flagged[flagged["is_outlier"]]
    by_company = (out.groupby("company_name")["amount"].agg(["count", "sum"])
                  .sort_values("sum", ascending=False).head(top))
    return {
        "n_payments": int(len(flagged)),
        "n_outliers": int(len(out)),
        "outlier_rate": round(len(out) / max(len(flagged), 1), 4),
        "outlier_amount": round(float(out["amount"].sum()), 2),
        "top_companies": [
            {"company": idx, "count": int(r["count"]), "amount": round(float(r["sum"]), 2)}
            for idx, r in by_company.iterrows()
        ],
    }


# ----------------------------------------------------------------- benchmarking
def company_physician_spend(payments: pd.DataFrame) -> pd.DataFrame:
    """Per-physician total received, pivoted by company (for Merck vs peers)."""
    df = payments.copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    g = df.groupby(["npi", "company_name"])["amount"].sum().reset_index()
    return g


def specialty_benchmark(payments: pd.DataFrame, anchor: str = "MERCK",
                        top_n: int = 12) -> pd.DataFrame:
    """Compare anchor company vs market on per-physician spend by specialty.

    Returns one row per specialty with the anchor's mean/median per-physician
    spend next to the market (all companies) figures and the peer mean.
    """
    df = payments.copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["specialty"] = df["specialty"].fillna("Unknown")
    df["is_anchor"] = df["company_name"].str.upper().str.contains(anchor, na=False)

    # per physician per company totals
    per_pc = (df.groupby(["specialty", "npi", "is_anchor"])["amount"]
              .sum().reset_index())

    anchor_rows = per_pc[per_pc["is_anchor"]]
    market_rows = per_pc

    a = (anchor_rows.groupby("specialty")["amount"]
         .agg(anchor_mean="mean", anchor_median="median", anchor_physicians="count"))
    m = (market_rows.groupby("specialty")["amount"]
         .agg(market_mean="mean", market_median="median", market_physicians="count"))

    peer = (market_rows[~market_rows["is_anchor"]]
            .groupby("specialty")["amount"]
            .agg(peer_mean="mean", peer_median="median"))

    bench = a.join(m, how="outer").join(peer, how="outer").fillna(0.0)
    bench["anchor_vs_market_mean"] = (
        bench["anchor_mean"] / bench["market_mean"].replace(0, np.nan)
    ).round(3)
    bench = bench.reset_index().rename(columns={"index": "specialty"})
    bench = bench.sort_values("market_physicians", ascending=False).head(top_n)
    return bench.round(2)


def company_totals(payments: pd.DataFrame, top: int = 20) -> pd.DataFrame:
    df = payments.copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    g = (df.groupby("company_name")["amount"]
         .agg(total="sum", mean="mean", median="median", n="count")
         .reset_index())
    g["n_physicians"] = df.groupby("company_name")["npi"].nunique().reindex(g["company_name"]).values
    return g.sort_values("total", ascending=False).head(top).round(2)


# ----------------------------------------------------------------- pareto / concentration
def pareto_curve(payments: pd.DataFrame, n_bins: int = 20) -> pd.DataFrame:
    """Cumulative share of spend vs share of physicians (Lorenz/Pareto)."""
    df = payments.copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    per_phys = df.groupby("npi")["amount"].sum().sort_values(ascending=False)
    total = per_phys.sum()
    if total <= 0:
        return pd.DataFrame(columns=["physician_pct", "spend_pct"])
    cum = per_phys.cumsum() / total
    ranks = np.arange(1, len(cum) + 1) / len(cum)
    step = 1.0 / n_bins
    grid = np.arange(step, 1.0001, step)
    # spend share captured by top X% physicians
    spend_at = [float(cum.iloc[max(int(p * len(cum)) - 1, 0)]) for p in grid]
    return pd.DataFrame({"physician_pct": (grid * 100).round(1),
                         "spend_pct": (np.array(spend_at) * 100).round(2)})


def concentration_stats(payments: pd.DataFrame) -> dict:
    df = payments.copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    per_phys = df.groupby("npi")["amount"].sum().sort_values(ascending=False)
    total = per_phys.sum()
    if total <= 0:
        return {"top_1pct_share": 0.0, "top_10pct_share": 0.0, "gini": 0.0}
    cum = per_phys.cumsum() / total
    top1 = float(cum.iloc[max(int(0.01 * len(cum)) - 1, 0)])
    top10 = float(cum.iloc[max(int(0.10 * len(cum)) - 1, 0)])
    # Gini via the trapezoid over the Lorenz curve (needs ASCENDING spend order)
    vals = per_phys.sort_values().values  # ascending for a proper Lorenz curve
    n = len(vals)
    cum_vals = np.cumsum(vals) / total
    lorenz = np.insert(cum_vals, 0, 0)
    x = np.linspace(0, 1, n + 1)
    gini = 1 - 2 * np.trapezoid(lorenz, x) if hasattr(np, "trapezoid") \
        else 1 - 2 * np.trapz(lorenz, x)
    gini = float(np.clip(gini, 0.0, 1.0))
    return {
        "top_1pct_share": round(top1, 4),
        "top_10pct_share": round(top10, 4),
        "gini": round(float(gini), 4),
        "n_physicians": int(n),
        "total_spend": round(float(total), 2),
    }


# --------------------------------------------------------------------- geospatial
def geospatial_spend(payments: pd.DataFrame) -> pd.DataFrame:
    df = payments.copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["state"] = df["state"].fillna("NA").replace("", "NA")
    g = (df.groupby("state")["amount"]
         .agg(total="sum", mean="mean", n_payments="count").reset_index())
    g["n_physicians"] = df.groupby("state")["npi"].nunique().reindex(g["state"]).values
    return g.sort_values("total", ascending=False).round(2)


def metro_spend(payments: pd.DataFrame, top: int = 15) -> pd.DataFrame:
    df = payments.copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["metro"] = (df["city"].fillna("").str.upper().str.strip() + ", "
                   + df["state"].fillna("").str.upper().str.strip())
    g = (df.groupby("metro")["amount"]
         .agg(total="sum", mean="mean", n_payments="count").reset_index())
    g["n_physicians"] = df.groupby("metro")["npi"].nunique().reindex(g["metro"]).values
    g = g[g["metro"].str.strip(", ") != ""]
    return g.sort_values("total", ascending=False).head(top).round(2)


def nature_distribution(payments: pd.DataFrame) -> pd.DataFrame:
    df = payments.copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    g = (df.groupby(df["nature"].fillna("Unknown"))["amount"]
         .agg(total="sum", mean="mean", n="count").reset_index())
    return g.sort_values("total", ascending=False).round(2)


# ------------------------------------------------------------------- bipartite
def bipartite_engagement(payments: pd.DataFrame, top_companies: int = 10,
                         top_physicians: int = 40) -> dict:
    """Company<->physician engagement matrix for the bipartite view."""
    df = payments.copy()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    top_cos = df.groupby("company_name")["amount"].sum().nlargest(top_companies).index
    d = df[df["company_name"].isin(top_cos)]
    per_phys = d.groupby("npi")["amount"].sum().nlargest(top_physicians).index
    d = d[d["npi"].isin(per_phys)]
    matrix = (d.pivot_table(index="npi", columns="company_name", values="amount",
                            aggfunc="sum", fill_value=0.0))
    return {
        "physicians": matrix.index.tolist(),
        "companies": matrix.columns.tolist(),
        "matrix": matrix.round(2).values.tolist(),
    }
