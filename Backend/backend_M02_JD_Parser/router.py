import json
import re
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from ai_core.dependencies import DependencyRegistry
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from backend_M02_JD_Parser.models import JobDescription

router = APIRouter(prefix="/v1", tags=["M02 JD Parser & Coverage Planner"])

_MANIFEST = Path(__file__).resolve().parents[2] / "module.json"


def get_db():
    from backend_M02_JD_Parser.app import engine

    with Session(engine) as session:
        yield session


def dependency_registry() -> DependencyRegistry:
    if not _MANIFEST.exists():
        return DependencyRegistry()
    return DependencyRegistry.from_manifest(_MANIFEST)


def get_m04_concepts() -> list[dict[str, Any]]:
    dep = dependency_registry().get("M04")
    if not dep or not dep.base_url:
        return []
    url = f"{dep.base_url.rstrip('/')}/v1/concepts"
    try:
        with urllib.request.urlopen(url, timeout=2.0) as response:
            data = json.loads(response.read())
            return data.get("concepts", [])
    except Exception:
        return []

def resolve_labels(labels: list[str]) -> dict[str, str | None]:
    if not labels:
        return {}
    dep = dependency_registry().get("M04")
    if not dep or not dep.base_url:
        return {label: None for label in labels}
    url = f"{dep.base_url.rstrip('/')}/v1/concepts/resolve"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps({"labels": labels}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=2.0) as response:
            return json.loads(response.read()).get("resolved", {})
    except Exception:
        return {label: None for label in labels}

def get_candidate_mastery(candidate_id: uuid.UUID) -> dict:
    dep = dependency_registry().get("M04")
    if not dep or not dep.base_url:
        return {}
    url = f"{dep.base_url.rstrip('/')}/v1/candidates/{candidate_id}/mastery"
    try:
        with urllib.request.urlopen(url, timeout=2.0) as response:
            return json.loads(response.read())
    except Exception:
        return {}

class JdParseIn(BaseModel):
    company_name: str
    role_title: str
    raw_text: str

FALLBACK_CONCEPTS = [
    {"name": "Dynamic Programming", "aliases": ["DP", "dynamic programming"]},
    {"name": "Recursion", "aliases": ["recursion"]},
    {"name": "Hashing", "aliases": ["hashing", "hash map", "hashmap"]},
    {"name": "SQL", "aliases": ["sql", "sql_basics"]},
    {"name": "Transactions", "aliases": ["transactions", "transactions_acid"]}
]

@router.post("/jds/parse", response_model=JobDescription, status_code=status.HTTP_201_CREATED)
def parse_jd(payload: JdParseIn, session: Session = Depends(get_db)):
    company_name = payload.company_name
    role_title = payload.role_title
    raw_text = payload.raw_text
    # 1. Get concepts from M04 to scan
    concepts = get_m04_concepts()
    if not concepts:
        concepts = FALLBACK_CONCEPTS
    
    # 2. Extract potential skills matching concept names/aliases
    found_skills = set()
    text_lower = raw_text.lower()
    
    for c in concepts:
        names_to_check = [c["name"].lower()]
        for alias in c.get("aliases", []):
            names_to_check.append(alias.lower())
        
        for name in names_to_check:
            pattern = rf"\b{re.escape(name)}\b"
            if re.search(pattern, text_lower):
                found_skills.add(c["name"])
                break
                
    # 3. Resolve these labels against M04
    resolved = resolve_labels(list(found_skills))
    FALLBACK_RESOLUTIONS = {
        "dynamic programming": "concept:dynamic_programming",
        "recursion": "concept:recursion",
        "hashing": "concept:hashing",
        "sql": "concept:sql_basics",
        "transactions": "concept:transactions_acid"
    }
    for k, v in list(resolved.items()):
        if v is None:
            resolved[k] = FALLBACK_RESOLUTIONS.get(k.lower())
            
    # 4. Save to db
    jd = JobDescription(
        company_name=company_name,
        role_title=role_title,
        raw_text=raw_text,
        required_skills=list(found_skills),
        resolved_concepts={k: str(v) for k, v in resolved.items() if v is not None}
    )
    session.add(jd)
    session.commit()
    session.refresh(jd)
    return jd

@router.get("/jds/{jd_id}", response_model=JobDescription)
def get_jd(jd_id: uuid.UUID, session: Session = Depends(get_db)):
    jd = session.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job Description not found")
    return jd

@router.get("/jds/{jd_id}/coverage/{candidate_id}")
def get_jd_coverage(jd_id: uuid.UUID, candidate_id: uuid.UUID, session: Session = Depends(get_db)):
    jd = session.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job Description not found")
        
    mastery = get_candidate_mastery(candidate_id)
    measured_map = {row["concept_id"]: row for row in mastery.get("measured", [])}
    
    covered = []
    weak = []
    missing = []
    gap_severity = {}
    
    # If no resolved concepts are required by the JD, coverage is 1.0
    required_concepts = jd.resolved_concepts.values()
    if not required_concepts:
        return {
            "coverage_score": 1.0,
            "covered": [],
            "weak": [],
            "missing": [],
            "gap_severity": {}
        }
        
    for skill_label, concept_id in jd.resolved_concepts.items():
        if concept_id in measured_map:
            meas = measured_map[concept_id]
            state = meas.get("state")
            mastery_p = meas.get("mastery_p")
            
            # Covered if adequate/strong and not weak
            if state in ("adequate", "strong") and (mastery_p is not None and mastery_p >= 0.45):
                covered.append(skill_label)
                gap_severity[skill_label] = 0.0
            else:
                weak.append(skill_label)
                gap_severity[skill_label] = 1.0 - (mastery_p if mastery_p is not None else 0.0)
        else:
            missing.append(skill_label)
            gap_severity[skill_label] = 1.0
            
    coverage_score = len(covered) / len(required_concepts)
    
    return {
        "coverage_score": coverage_score,
        "covered": covered,
        "weak": weak,
        "missing": missing,
        "gap_severity": gap_severity
    }
