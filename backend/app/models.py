"""Pydantic response models for the MedGraph API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class Health(BaseModel):
    status: str
    db: str
    physicians: int
    payments: int
    edges: int
    trials: int


class KolRow(BaseModel):
    rank: int
    npi: str
    name: str
    specialty: str
    state: str
    influence_score: float
    publication_score: float
    trial_score: float
    network_score: float
    payment_score: float
    publications: int
    trial_count: int
    degree: int
    total_received: float
    n_companies: int


class KolLeaderboard(BaseModel):
    total: int
    rows: List[KolRow]


class InfluenceBreakdown(BaseModel):
    npi: str
    name: str
    weights: Dict[str, float]
    signals: Dict[str, float]


class NetworkGraph(BaseModel):
    nodes: List[Dict[str, Any]]
    links: List[Dict[str, Any]]
    n_nodes: int
    n_links: int


class OutlierSummary(BaseModel):
    n_payments: int
    n_outliers: int
    outlier_rate: float
    outlier_amount: float
    top_companies: List[Dict[str, Any]]


class BenchmarkRow(BaseModel):
    specialty: str
    anchor_mean: float = 0
    anchor_median: float = 0
    anchor_physicians: int = 0
    market_mean: float = 0
    market_median: float = 0
    market_physicians: int = 0
    peer_mean: float = 0
    peer_median: float = 0
    anchor_vs_market_mean: Optional[float] = None


class ParetoPoint(BaseModel):
    physician_pct: float
    spend_pct: float


class GeoPoint(BaseModel):
    state: str
    total: float
    mean: float
    n_payments: int
    n_physicians: int


class MetroPoint(BaseModel):
    metro: str
    total: float
    mean: float
    n_payments: int
    n_physicians: int


class NaturePoint(BaseModel):
    nature: str
    total: float
    mean: float
    n: int


class CompanyTotal(BaseModel):
    company_name: str
    total: float
    mean: float
    median: float
    n: int
    n_physicians: int


class Concentration(BaseModel):
    top_1pct_share: float
    top_10pct_share: float
    gini: float
    n_physicians: int
    total_spend: float


class Bipartite(BaseModel):
    physicians: List[str]
    companies: List[str]
    matrix: List[List[float]]


class PhysicianProfile(BaseModel):
    npi: str
    name: str
    specialty: str
    primary_type: str
    city: str
    state: str
    influence: Optional[KolRow] = None
    payments_by_company: List[Dict[str, Any]]
    payments_by_nature: List[Dict[str, Any]]
    research: List[Dict[str, Any]]
    publications: Optional[Dict[str, Any]]
    nppes: Optional[Dict[str, Any]]
    network_neighbors: List[Dict[str, Any]]
    trials: List[Dict[str, Any]]


class Stats(BaseModel):
    physicians: int
    companies: int
    payments: int
    research_payments: int
    edges: int
    trials: int
    publications: int
    total_spend: float
    program_year: int
