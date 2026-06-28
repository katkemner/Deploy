"""Employee Digital Twin Seed parsing & validation.

Turns an uploaded **employee digital twin seed file** (``.csv`` or ``.xlsx``)
into engine ``Worker`` objects plus a validation report and a sanitized preview.

These are **seed profiles used for simulation — not full digital twins.** Only a
subset of fields feeds the deterministic engine (name, role, skills,
capacity/workload, and cost_rate/quality_score). Recommended fields are captured
for the preview but do not affect scoring or routing.

Privacy: sensitive columns are **dropped on ingest** — never parsed into the
result, never stored, never returned. They are only listed by name in the
report. Nothing here is persisted to disk; the caller holds the active set in
memory for the session.
"""

from __future__ import annotations

import io
import re
from typing import List, Tuple

import pandas as pd

from models import HUMAN, Worker

# Defaults for engine-needed fields that the spec treats as "recommended".
DEFAULT_COST_RATE = 75.0
DEFAULT_QUALITY_SCORE = 7.0

# Column aliases -> canonical field. Matching is case/space/underscore-insensitive.
_ALIASES = {
    "name": ["name", "employee_name", "full_name"],
    "employee_id": ["employee_id", "emp_id", "employeeid", "id"],
    "role": ["role", "job_title", "title", "position"],
    "department": ["department", "team", "dept", "division"],
    "skills": ["skills", "skill", "skillset", "skill_set"],
    "capacity_hours": ["capacity_hours", "capacity", "weekly_capacity_hours", "capacity_hrs"],
    "workload_hours": ["workload_hours", "workload", "current_workload_hours", "workload_hrs"],
    "cost_rate": ["cost_rate", "cost", "hourly_rate", "rate", "bill_rate"],
    "quality_score": ["quality_score", "quality"],
}

# Recommended profile fields (captured for preview; NOT used by the engine).
RECOMMENDED_FIELDS = [
    "manager", "location", "time_zone", "employment_type", "job_family",
    "job_level", "skill_proficiency", "certifications", "cost_rate",
    "quality_score", "availability_notes", "domain_expertise", "tools",
    "project_history", "preferred_work_type", "collaboration_style",
    "communication_preference", "learning_goals", "innovation_capability_tags",
]

# Required seed columns (per spec). Of these, the four ENGINE-ESSENTIAL ones must
# be present or the file is rejected; the rest are reported-but-tolerated
# (role defaults, department optional, employee_id generated).
REQUIRED_FIELDS = [
    "employee_id", "name", "role", "department",
    "skills", "capacity_hours", "workload_hours",
]
ENGINE_ESSENTIAL = ["name", "skills", "capacity_hours", "workload_hours"]

# Sensitive column tokens — any column whose name contains one of these (as a
# whole token) is dropped on ingest. Privacy-first: the engine never needs them.
_SENSITIVE_TOKENS = {
    "dob", "birth", "birthdate", "birthday", "age",
    "address",
    "phone", "mobile", "telephone",
    "email",
    "ssn", "sin", "national", "nationality", "passport", "citizenship",
    "visa", "immigration",
    "tax", "taxid",
    "bank", "iban", "routing",
    "benefit", "benefits",
    "dependent", "dependents",
    "medical", "disability", "disabilities", "health", "diagnosis",
    "race", "ethnicity", "ethnic", "gender", "religion", "religious",
    "orientation", "sexual", "marital",
    "disciplinary", "discipline",
}


class SeedError(Exception):
    """Raised when the seed file can't be used. Carries an HTTP ``status``."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _norm(col: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(col).strip().lower()).strip("_")


def _tokens(col: str) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", str(col).strip().lower()) if t}


def _is_sensitive(col: str) -> bool:
    return bool(_tokens(col) & _SENSITIVE_TOKENS)


def _build_alias_index(columns) -> dict:
    """Map canonical field -> actual column name present in the file."""
    norm_to_actual = {}
    for c in columns:
        norm_to_actual.setdefault(_norm(c), c)
    index = {}
    for field, aliases in _ALIASES.items():
        for a in aliases:
            if a in norm_to_actual:
                index[field] = norm_to_actual[a]
                break
    return index


def _split_list(raw) -> List[str]:
    """Split a skills/tags cell on | , or ; into a clean list."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    parts = re.split(r"[|,;]", str(raw))
    return [p.strip() for p in parts if p.strip()]


def _num(raw):
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _cell(row, col):
    if col is None:
        return None
    val = row.get(col)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return val


def parse_seed(content: bytes, filename: str) -> Tuple[List[Worker], dict, List[dict]]:
    """Parse an uploaded seed file. Returns ``(workers, report, preview)``.

    Raises :class:`SeedError` (with an HTTP ``status``) on an unreadable file,
    an unsupported type, missing engine-essential columns, or no usable rows.
    """
    if not content:
        raise SeedError(400, "The uploaded file is empty.")

    lower = (filename or "").lower()
    try:
        if lower.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
        elif lower.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            raise SeedError(
                415, "Unsupported file type. Upload an employee seed .xlsx or .csv."
            )
    except SeedError:
        raise
    except Exception as exc:  # malformed file
        raise SeedError(400, f"Could not read the seed file: {exc}")

    # 1. Drop sensitive columns BEFORE anything else touches them.
    sensitive_dropped = [str(c) for c in df.columns if _is_sensitive(c)]
    if sensitive_dropped:
        df = df.drop(columns=sensitive_dropped)

    if df.empty:
        raise SeedError(400, "The seed file has no data rows.")

    idx = _build_alias_index(df.columns)

    # 2. Engine-essential columns must be present.
    missing_essential = [f for f in ENGINE_ESSENTIAL if f not in idx]
    if missing_essential:
        raise SeedError(
            400,
            "Seed file is missing essential column(s): "
            f"{missing_essential}. Required: {REQUIRED_FIELDS} "
            "(employee_id, role, department are recommended-but-tolerated).",
        )

    # Track which seed-required columns are absent (informational).
    missing_required = [f for f in REQUIRED_FIELDS if f not in idx]
    recommended_present = sorted(
        f for f in RECOMMENDED_FIELDS
        if _norm(f) in {_norm(c) for c in df.columns}
    )
    recommended_missing = [f for f in RECOMMENDED_FIELDS if f not in recommended_present]

    workers: List[Worker] = []
    preview: List[dict] = []
    row_errors: List[str] = []
    cost_defaulted = 0
    quality_defaulted = 0
    role_defaulted = 0
    id_generated = 0

    for i, row in df.iterrows():
        rownum = int(i) + 2  # +2 = header row + 1-based
        name = _cell(row, idx.get("name"))
        skills = _split_list(_cell(row, idx.get("skills")))
        capacity = _num(_cell(row, idx.get("capacity_hours")))
        workload = _num(_cell(row, idx.get("workload_hours")))

        problems = []
        if not name or not str(name).strip():
            problems.append("missing name")
        if not skills:
            problems.append("missing skills")
        if capacity is None:
            problems.append("missing/invalid capacity_hours")
        if workload is None:
            problems.append("missing/invalid workload_hours")
        if problems:
            row_errors.append(f"Row {rownum}: " + ", ".join(problems) + " (skipped)")
            continue

        # role: default if absent.
        role = _cell(row, idx.get("role"))
        if role is None or not str(role).strip():
            role = "Employee"
            role_defaulted += 1
        # employee_id: generate if absent.
        emp_id = _cell(row, idx.get("employee_id"))
        if emp_id is None or not str(emp_id).strip():
            emp_id = f"EMP-{len(workers) + 1:03d}"
            id_generated += 1
        # cost_rate / quality_score: default + flag.
        cost = _num(_cell(row, idx.get("cost_rate")))
        cost_is_default = cost is None
        if cost_is_default:
            cost = DEFAULT_COST_RATE
            cost_defaulted += 1
        quality = _num(_cell(row, idx.get("quality_score")))
        quality_is_default = quality is None
        if quality_is_default:
            quality = DEFAULT_QUALITY_SCORE
            quality_defaulted += 1

        workers.append(
            Worker(
                name=str(name).strip(),
                type=HUMAN,
                role=str(role).strip(),
                skills=skills,
                capacity_hours=float(capacity),
                workload_hours=float(workload),
                cost_rate=float(cost),
                quality_score=float(quality),
                speed_multiplier=1.0,
            )
        )

        # Sanitized preview (no sensitive data — those columns are gone).
        item = {
            "employee_id": str(emp_id).strip(),
            "name": str(name).strip(),
            "role": str(role).strip(),
            "department": (str(_cell(row, idx.get("department"))).strip()
                           if _cell(row, idx.get("department")) is not None else None),
            "skills": skills,
            "capacity_hours": float(capacity),
            "workload_hours": float(workload),
            "cost_rate": float(cost),
            "cost_rate_defaulted": cost_is_default,
            "quality_score": float(quality),
            "quality_score_defaulted": quality_is_default,
        }
        preview.append(item)

    if not workers:
        raise SeedError(
            400,
            "No usable employee rows were found. "
            + (" ".join(row_errors[:5]) if row_errors else ""),
        )

    distinct_skills = sorted({s for w in workers for s in w.skills})
    defaulted_fields = []
    if cost_defaulted:
        defaulted_fields.append(f"cost_rate (defaulted to {DEFAULT_COST_RATE:g} for {cost_defaulted} employee(s))")
    if quality_defaulted:
        defaulted_fields.append(f"quality_score (defaulted to {DEFAULT_QUALITY_SCORE:g} for {quality_defaulted} employee(s))")
    if role_defaulted:
        defaulted_fields.append(f"role (defaulted to 'Employee' for {role_defaulted} employee(s))")
    if id_generated:
        defaulted_fields.append(f"employee_id (generated for {id_generated} employee(s))")

    report = {
        "filename": filename,
        "employee_count": len(workers),
        "distinct_skills": distinct_skills,
        "missing_required": missing_required,
        "recommended_present": recommended_present,
        "recommended_missing": recommended_missing,
        "sensitive_columns_dropped": sensitive_dropped,
        "defaulted_fields": defaulted_fields,
        "row_errors": row_errors,
        "note": (
            "Seed profiles used for simulation — not full employee digital twins. "
            "Recommended fields are captured for preview only and do not affect "
            "scoring or routing. Sensitive columns were dropped and never stored."
        ),
    }
    return workers, report, preview
