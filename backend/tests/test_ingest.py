"""Ingest-layer unit tests (offline; no network).

Tests the CSV parsing / entity-resolution / edge-building logic that powers the
pipeline, using synthetic CSV text so nothing hits the public APIs.
"""
from __future__ import annotations

import csv
import io

import pytest

from app.ingest import openpayments as op
from app.ingest.openpayments import ResearchPayment, build_co_investigator_edges


def test_target_company_regex_matches_variants():
    assert op._TARGET_RE.search("Merck Sharp & Dohme LLC")
    assert op._TARGET_RE.search("MERCK SHARP & DOHME")
    assert op._TARGET_RE.search("Pfizer Inc.")
    assert op._TARGET_RE.search("AstraZeneca Pharmaceuticals LP")
    assert not op._TARGET_RE.search("Walmart Stores")


def test_norm_money():
    assert op._norm_money("$1,234.56") == 1234.56
    assert op._norm_money("0") == 0.0
    assert op._norm_money("") == 0.0
    assert op._norm_money("garbage") == 0.0


def test_build_co_investigator_edges_from_pis():
    research = [
        ResearchPayment("100", "R Doc", "Onc", "MA", "MERCK", "", 1000, "2024-01-01",
                        "S1", "2024", pis=[("1", "A One"), ("2", "B Two"), ("3", "C Three")]),
        ResearchPayment("100", "R Doc", "Onc", "MA", "MERCK", "", 500, "2024-02-01",
                        "S2", "2024", pis=[("1", "A One"), ("2", "B Two")]),
        ResearchPayment("101", "R Doc2", "Car", "NY", "PFIZER", "", 100, "2024-03-01",
                        "S3", "2024", pis=[("9", "Z Nine")]),  # single PI -> no edge
    ]
    edges, degree = build_co_investigator_edges(research)
    # pair (1,2) shared twice; (1,3) and (2,3) once each
    assert edges[("1", "2")]["weight"] == 2
    assert edges[("1", "3")]["weight"] == 1
    assert edges[("2", "3")]["weight"] == 1
    # amount accumulates on the shared edge
    assert edges[("1", "2")]["amount"] == 1500.0
    assert degree["1"] == 2 and degree["2"] == 2


def test_build_edges_ignores_single_pi():
    research = [ResearchPayment("1", "A", "", "", "X", "", 0, "", "S", "2024",
                                pis=[("5", "Only One")])]
    edges, degree = build_co_investigator_edges(research)
    assert edges == {}
    assert degree["5"] == 0


def test_parse_research_extracts_pis():
    header = [
        "Covered_Recipient_NPI", "Covered_Recipient_First_Name",
        "Covered_Recipient_Last_Name", "Covered_Recipient_Specialty_1",
        "Recipient_State", "Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Name",
        "Form_of_Payment_or_Transfer_of_Value", "Total_Amount_of_Payment_USDollars",
        "Date_of_Payment", "Program_Year",
        "Principal_Investigator_1_NPI", "Principal_Investigator_1_First_Name",
        "Principal_Investigator_1_Last_Name",
        "Principal_Investigator_2_NPI", "Principal_Investigator_2_First_Name",
        "Principal_Investigator_2_Last_Name",
    ]
    row = ["200", "Rec", "Ipient", "Oncology", "MA", "MERCK", "Cash", "1234.5",
           "2024-01-01", "2024", "11", "Ann", "Alpha", "22", "Bob", "Bravo"]
    ix = {h: i for i, h in enumerate(header)}
    rp = op._parse_research(row, ix)
    assert rp is not None
    assert rp.recipient_npi == "200"
    assert rp.amount == 1234.5
    assert len(rp.pis) == 2
    assert rp.pis[0] == ("11", "Ann Alpha")
    assert rp.pis[1] == ("22", "Bob Bravo")


def test_parse_research_requires_some_npi():
    header = ["Covered_Recipient_NPI", "Principal_Investigator_1_NPI"]
    ix = {h: i for i, h in enumerate(header)}
    assert op._parse_research(["", ""], ix) is None  # no recipient, no PI


def test_csv_escape_quotes():
    assert op._csv_escape("plain") == "plain"
    assert op._csv_escape("has,comma") == '"has,comma"'
    assert op._csv_escape('say "hi"') == '"say ""hi"""'
