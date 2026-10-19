"""ClinicalTrials.gov v2 API ingest.

Pulls interventional studies for a set of sponsor terms (anchor: Merck/MSD) to
characterise the trial landscape and to derive investigator-level trial
influence (PI counts, enrollment, phases, conditions). The v2 API returns
`protocolSection.contactsLocationsModule.overallOfficials` (name + affiliation
+ role) which we use to link investigators to studies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List
from urllib.parse import urlencode

from .. import config
from . import sources

log = logging.getLogger("medgraph.ingest.clinicaltrials")


@dataclass
class TrialOfficial:
    name: str
    affiliation: str
    role: str


@dataclass
class Trial:
    nct_id: str
    title: str
    status: str
    sponsor: str
    sponsor_class: str
    conditions: List[str] = field(default_factory=list)
    interventions: List[str] = field(default_factory=list)
    phases: List[str] = field(default_factory=list)
    enrollment: int = 0
    start_date: str = ""
    completion_date: str = ""
    study_type: str = ""
    officials: List[TrialOfficial] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)


_FIELDS = ",".join([
    "NCTId", "BriefTitle", "OverallStatus", "LeadSponsorName", "LeadSponsorClass",
    "Condition", "InterventionName", "Phase", "EnrollmentCount",
    "StartDate", "CompletionDate", "StudyType",
])


def fetch_trials_for_term(term: str, max_studies: int | None = None,
                          page_size: int | None = None) -> List[Trial]:
    max_studies = max_studies or config.CTGOV_MAX_STUDIES
    page_size = page_size or config.CTGOV_PAGE_SIZE
    trials: List[Trial] = []
    page_token = None
    while len(trials) < max_studies:
        params: Dict[str, str] = {
            "query.term": term,
            "pageSize": str(min(page_size, max_studies - len(trials))),
            "format": "json",
            "fields": _FIELDS + ",OverallOfficialsName,OverallOfficialsAffiliation,OverallOfficialsRole",
        }
        # overall-officials fields must be requested via the full record; the v2
        # `fields` filter rejects them, so we fetch full studies and slice.
        params.pop("fields")
        if page_token:
            params["pageToken"] = page_token
        url = f"{sources.CTGOV_STUDIES}?{urlencode(params)}"
        try:
            payload = sources.http_get(url)
        except Exception as e:  # noqa: BLE001
            log.warning("ctgov fetch failed for %r: %s", term, e)
            break
        import json
        data = json.loads(payload)
        for study in data.get("studies", []):
            t = _parse_study(study)
            if t:
                trials.append(t)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    log.info("ctgov: %d trials for term %r", len(trials), term)
    return trials


def _parse_study(study: dict) -> Trial | None:
    proto = study.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    nct = ident.get("nctId")
    if not nct:
        return None
    status = proto.get("statusModule", {})
    sponsor = proto.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {})
    design = proto.get("designModule", {})
    conds = proto.get("conditionsModule", {}).get("conditions", [])
    arms = proto.get("armsInterventionsModule", {}).get("interventions", [])
    officials_raw = proto.get("contactsLocationsModule", {}).get("overallOfficials", [])
    locs = proto.get("contactsLocationsModule", {}).get("locations", [])

    officials = [
        TrialOfficial(name=o.get("name", ""), affiliation=o.get("affiliation", ""),
                      role=o.get("role", ""))
        for o in officials_raw if o.get("name")
    ]
    locations = [loc.get("facility", "") for loc in locs if loc.get("facility")]
    return Trial(
        nct_id=nct, title=ident.get("briefTitle", ""),
        status=status.get("overallStatus", ""),
        sponsor=sponsor.get("name", ""), sponsor_class=sponsor.get("class", ""),
        conditions=conds, interventions=[a.get("name", "") for a in arms if a.get("name")],
        phases=design.get("phases", []), enrollment=design.get("enrollmentInfo", {}).get("count", 0),
        start_date=status.get("startDateStruct", {}).get("date", ""),
        completion_date=status.get("completionDateStruct", {}).get("date", ""),
        study_type=design.get("studyType", ""), officials=officials, locations=locations,
    )


def fetch_sponsor_trials(terms: List[str]) -> List[Trial]:
    seen = set()
    out: List[Trial] = []
    for term in terms:
        for t in fetch_trials_for_term(term):
            if t.nct_id in seen:
                continue
            seen.add(t.nct_id)
            out.append(t)
    return out


# --------------------------------------------------------------------------
# Co-investigator network from trial officials
# --------------------------------------------------------------------------
import re as _re

# CT.gov often records generic placeholders instead of a person's name.
_GENERIC = _re.compile(
    r"^(medical director|study director|principal investigator|investigator|"
    r"study chair|sub.?investigator|site investigator|null|n/?a|unknown|"
    r"director|coordinator|monitor|none|na|-)+$", _re.IGNORECASE)

_SUFFIX = _re.compile(r",?\s*(md|do|phd|mph|msc|mbbs|facc|facp|jr|ii|iii)\.?$", _re.IGNORECASE)


def normalize_name(name: str) -> str:
    """Uppercase 'First Last' with credentials stripped; '' if generic/empty."""
    if not name:
        return ""
    n = name.strip().rstrip(",")
    n = _SUFFIX.sub("", n).strip()
    # keep only letters, spaces, hyphens, apostrophes
    n = _re.sub(r"[^A-Za-z\-'\s]", " ", n)
    n = _re.sub(r"\s+", " ", n).strip()
    if not n or _GENERIC.match(n.lower()):
        return ""
    # must look like at least First Last (two tokens) to be a real person
    if len(n.split()) < 2:
        return ""
    return n.upper()


def build_official_edges(trials: List[Trial]) -> Dict[str, dict]:
    """Co-investigator edges from shared trials.

    Returns {(key_a, key_b): {weight, enrollment, ncts:set}} where a key is the
    normalised official name (NPI resolution happens downstream). Only trials with
    2+ *real* named officials contribute, so generic placeholders are dropped.
    """
    edges: Dict[Tuple[str, str], dict] = {}
    for t in trials:
        names = []
        seen = set()
        for o in t.officials:
            norm = normalize_name(o.name)
            if norm and norm not in seen:
                seen.add(norm)
                names.append((norm, o.affiliation or ""))
        if len(names) < 2:
            continue
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = sorted([names[i][0], names[j][0]])
                key = (a, b)
                rec = edges.setdefault(key, {"weight": 0, "enrollment": 0, "ncts": set()})
                rec["weight"] += 1
                rec["enrollment"] += int(t.enrollment or 0)
                rec["ncts"].add(t.nct_id)
    return edges


def officials_affiliations(trials: List[Trial]) -> Dict[str, str]:
    """Map normalised official name -> most common affiliation."""
    from collections import Counter, defaultdict
    aff: Dict[str, List[str]] = defaultdict(list)
    for t in trials:
        for o in t.officials:
            norm = normalize_name(o.name)
            if norm and o.affiliation:
                aff[norm].append(o.affiliation)
    return {k: Counter(v).most_common(1)[0][0] for k, v in aff.items() if v}


def fetch_network_trials(max_per_query: int = 250) -> List[Trial]:
    """Pull trials across sponsors + conditions likely to name multiple real
    investigators, so the co-investigator network is genuinely dense.

    Academic / investigator-initiated trials (surfaced via condition queries)
    typically list several named officials, unlike industry sponsor queries that
    return a single 'Medical Director'.
    """
    import json
    queries = [
        "Merck Sharp & Dohme", "Pfizer", "AstraZeneca", "Novartis", "Eli Lilly",
        # condition queries surface academic trials with named investigator teams
        "cancer pembrolizumab investigator", "cardiovascular outcomes trial",
        "diabetes phase 3", "Alzheimer disease trial", "NASH trial",
        "hypertension randomized", "asthma biologic", "rheumatoid arthritis trial",
        "multiple sclerosis trial", "chronic kidney disease trial",
    ]
    seen = set()
    out: List[Trial] = []
    for term in queries:
        trials = fetch_trials_for_term(term, max_studies=max_per_query)
        for t in trials:
            if t.nct_id in seen:
                continue
            seen.add(t.nct_id)
            out.append(t)
    return out
