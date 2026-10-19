"""SQLite schema + connection helpers for MedGraph.

The database is a denormalised-but-queryable warehouse: raw-ish payment facts,
research engagements, co-investigator edges, trials, publications and a
precomputed physician influence table that powers the leaderboard.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from . import config

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS physicians (
    npi            TEXT PRIMARY KEY,
    profile_id     TEXT,
    first_name     TEXT,
    middle_name    TEXT,
    last_name      TEXT,
    suffix         TEXT,
    display_name   TEXT,
    specialty      TEXT,
    primary_type   TEXT,
    city           TEXT,
    state          TEXT,
    zip_code       TEXT,
    country        TEXT
);

CREATE TABLE IF NOT EXISTS companies (
    company_id     TEXT,
    company_name   TEXT PRIMARY KEY,
    total_amount   REAL,
    n_records      INTEGER,
    n_physicians   INTEGER
);

CREATE TABLE IF NOT EXISTS payments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    npi            TEXT,
    company_name   TEXT,
    company_id     TEXT,
    amount         REAL,
    date           TEXT,
    n_payments     INTEGER,
    form           TEXT,
    nature         TEXT,
    program_year   TEXT
);
CREATE INDEX IF NOT EXISTS idx_payments_npi ON payments(npi);
CREATE INDEX IF NOT EXISTS idx_payments_company ON payments(company_name);
CREATE INDEX IF NOT EXISTS idx_payments_nature ON payments(nature);

CREATE TABLE IF NOT EXISTS research_payments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_npi  TEXT,
    company_name   TEXT,
    amount         REAL,
    form           TEXT,
    date           TEXT,
    study_id       TEXT,
    program_year   TEXT
);
CREATE INDEX IF NOT EXISTS idx_research_npi ON research_payments(recipient_npi);

CREATE TABLE IF NOT EXISTS co_investigator_edges (
    npi_a          TEXT,
    npi_b          TEXT,
    weight         INTEGER,
    amount         REAL,
    companies      TEXT
);
CREATE INDEX IF NOT EXISTS idx_edges_a ON co_investigator_edges(npi_a);
CREATE INDEX IF NOT EXISTS idx_edges_b ON co_investigator_edges(npi_b);

CREATE TABLE IF NOT EXISTS trials (
    nct_id         TEXT PRIMARY KEY,
    title          TEXT,
    status         TEXT,
    sponsor        TEXT,
    sponsor_class  TEXT,
    conditions     TEXT,
    interventions  TEXT,
    phases         TEXT,
    enrollment     INTEGER,
    start_date     TEXT,
    completion_date TEXT,
    study_type     TEXT
);

CREATE TABLE IF NOT EXISTS trial_officials (
    nct_id         TEXT,
    name           TEXT,
    affiliation    TEXT,
    role           TEXT
);
CREATE INDEX IF NOT EXISTS idx_trial_officials_name ON trial_officials(name);

CREATE TABLE IF NOT EXISTS publications (
    npi            TEXT,
    query_name     TEXT,
    hit_count      INTEGER,
    first_year     INTEGER,
    last_year      INTEGER,
    top_journals   TEXT
);
CREATE INDEX IF NOT EXISTS idx_pub_npi ON publications(npi);

CREATE TABLE IF NOT EXISTS nppes (
    npi            TEXT PRIMARY KEY,
    credential     TEXT,
    primary_specialty TEXT,
    taxonomy       TEXT,
    state          TEXT,
    city           TEXT,
    country        TEXT
);

CREATE TABLE IF NOT EXISTS physician_influence (
    npi            TEXT PRIMARY KEY,
    influence_score REAL,
    publication_score REAL,
    trial_score    REAL,
    network_score  REAL,
    payment_score  REAL,
    publications   INTEGER,
    trial_count    INTEGER,
    total_enrollment INTEGER,
    degree         INTEGER,
    total_received REAL,
    n_companies    INTEGER,
    rank           INTEGER
);
"""


def connect(db_path=None) -> sqlite3.Connection:
    path = str(db_path or config.DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def get_db(db_path=None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def reset_db(db_path=None) -> None:
    path = db_path or config.DB_PATH
    for suffix in ("", "-wal", "-shm"):
        p = f"{path}{suffix}"
        try:
            import os
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass
