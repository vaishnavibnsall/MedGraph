"""KOL multi-signal influence scoring.

Combines four independent public signals into a single 0-100 index:

  1. publication_score  — Europe PMC publication volume (bibliometric output)
  2. trial_score        — clinical-trial engagement (research PI studies + enrollment)
  3. network_score      — co-investigator network centrality (degree + weighted degree)
  4. payment_score      — industry engagement tier (general-payment received, log-scaled)

Each signal is min-max scaled to [0,1] after a log1p transform (these are heavily
right-skewed count/dollar fields), then combined with configurable weights that
sum to 1. The result is a transparent, defensible KOL index rather than a black box.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_WEIGHTS = {
    "publication": 0.30,
    "trial": 0.30,
    "network": 0.25,
    "payment": 0.15,
}


def _scale(series: pd.Series, log: bool = True) -> pd.Series:
    """Min-max scale to [0,1]; optionally after log1p to tame skew."""
    s = series.astype(float).fillna(0.0)
    if log:
        s = np.log1p(s.clip(lower=0))
    rng = s.max() - s.min()
    if rng <= 0:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - s.min()) / rng


def compute_influence(
    physicians: pd.DataFrame,
    pub_counts: pd.Series | None = None,
    trial_counts: pd.Series | None = None,
    enrollment: pd.Series | None = None,
    degree: pd.Series | None = None,
    wdegree: pd.Series | None = None,
    received: pd.Series | None = None,
    weights: dict | None = None,
) -> pd.DataFrame:
    """Return a per-NPI influence frame.

    `physicians` must have an `npi` column and is the row universe. The signal
    Series are indexed by npi; missing physicians receive a 0 for that signal.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    npi = physicians["npi"]
    idx = npi.values

    def align(s: pd.Series | None) -> pd.Series:
        if s is None:
            return pd.Series(0.0, index=idx)
        return s.reindex(idx).fillna(0.0)

    pubs = align(pub_counts)
    trials = align(trial_counts)
    enr = align(enrollment)
    deg = align(degree)
    wdeg = align(wdegree) if wdegree is not None else deg
    recv = align(received)

    # trial signal blends study count with total enrollment
    trial_raw = trials + 0.001 * enr
    network_raw = deg + 0.5 * wdeg

    pub_s = _scale(pubs)
    trial_s = _scale(trial_raw)
    net_s = _scale(network_raw)
    pay_s = _scale(recv)

    score = (
        w["publication"] * pub_s
        + w["trial"] * trial_s
        + w["network"] * net_s
        + w["payment"] * pay_s
    ) * 100.0

    out = pd.DataFrame({
        "npi": idx,
        "publication_score": (pub_s * 100).round(2),
        "trial_score": (trial_s * 100).round(2),
        "network_score": (net_s * 100).round(2),
        "payment_score": (pay_s * 100).round(2),
        "influence_score": score.round(2),
        "publications": pubs.astype(int).values,
        "trial_count": trials.astype(int).values,
        "total_enrollment": enr.astype(int).values,
        "degree": deg.astype(int).values,
        "total_received": recv.astype(float).round(2).values,
    })
    out = out.sort_values("influence_score", ascending=False).reset_index(drop=True)
    out["rank"] = out.index + 1
    return out
