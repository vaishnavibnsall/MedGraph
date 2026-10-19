"""In-memory analytics store.

Loads the SQLite warehouse into pandas once and memoises the heavier analytics
(compliance outliers, network graph, influence) so API responses stay fast even
on a few hundred thousand payment rows. Reloading is explicit (`refresh()`).
"""
from __future__ import annotations

import sqlite3
import threading
from typing import Optional

import networkx as nx
import pandas as pd

from . import config, db
from .analytics import compliance as compliance_mod
from .analytics import network as network_mod

_LOCK = threading.Lock()


class Store:
    def __init__(self) -> None:
        self.loaded = False
        self.payments: pd.DataFrame = pd.DataFrame()
        self.research: pd.DataFrame = pd.DataFrame()
        self.physicians: pd.DataFrame = pd.DataFrame()
        self.edges: pd.DataFrame = pd.DataFrame()
        self.influence: pd.DataFrame = pd.DataFrame()
        self.trials: pd.DataFrame = pd.DataFrame()
        self.officials: pd.DataFrame = pd.DataFrame()
        self.publications: pd.DataFrame = pd.DataFrame()
        self.nppes: pd.DataFrame = pd.DataFrame()
        self.companies: pd.DataFrame = pd.DataFrame()
        self.G: Optional[nx.Graph] = None
        self.name_map: dict = {}
        self.stats: dict = {}
        # memoised analytics
        self._flagged: Optional[pd.DataFrame] = None
        self._centrality: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------ load
    def load(self, db_path=None) -> None:
        with db.connect(db_path) as conn:
            self.payments = _read(conn, "SELECT * FROM payments")
            self.research = _read(conn, "SELECT * FROM research_payments")
            self.physicians = _read(conn, "SELECT * FROM physicians")
            self.edges = _read(conn, "SELECT * FROM co_investigator_edges")
            self.influence = _read(conn, "SELECT * FROM physician_influence")
            self.trials = _read(conn, "SELECT * FROM trials")
            self.officials = _read(conn, "SELECT * FROM trial_officials")
            self.publications = _read(conn, "SELECT * FROM publications")
            self.nppes = _read(conn, "SELECT * FROM nppes")
            self.companies = _read(conn, "SELECT * FROM companies")

        # payments joined with recipient specialty/state for compliance analytics
        if len(self.payments) and len(self.physicians):
            self.payments = self.payments.merge(
                self.physicians[["npi", "specialty", "state", "city", "display_name"]],
                on="npi", how="left")

        if len(self.edges):
            self.G = network_mod.build_graph(self.edges)
        else:
            self.G = nx.Graph()
        self.name_map = dict(zip(self.physicians["npi"], self.physicians["display_name"])) \
            if len(self.physicians) else {}

        self.stats = {
            "physicians": int(len(self.physicians)),
            "companies": int(len(self.companies)),
            "payments": int(len(self.payments)),
            "research_payments": int(len(self.research)),
            "edges": int(len(self.edges)),
            "trials": int(len(self.trials)),
            "publications": int(len(self.publications)),
            "total_spend": round(float(self.payments["amount"].sum()), 2) if len(self.payments) else 0.0,
            "program_year": config.OPEN_PAYMENTS_YEAR,
        }
        self._flagged = None
        self._centrality = None
        self.loaded = True

    # ------------------------------------------------------------- memoised
    @property
    def flagged(self) -> pd.DataFrame:
        if self._flagged is None:
            self._flagged = compliance_mod.flag_payment_outliers(self.payments)
        return self._flagged

    @property
    def centrality(self) -> pd.DataFrame:
        if self._centrality is None:
            self._centrality = network_mod.centralities(self.G)
        return self._centrality


def _read(conn: sqlite3.Connection, sql: str) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn)


_STORE: Optional[Store] = None


def get_store() -> Store:
    global _STORE
    if _STORE is None or not _STORE.loaded:
        with _LOCK:
            if _STORE is None or not _STORE.loaded:
                s = Store()
                s.load()
                _STORE = s
    return _STORE


def refresh() -> Store:
    global _STORE
    with _LOCK:
        s = Store()
        s.load()
        _STORE = s
    return _STORE
