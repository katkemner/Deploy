"""Read-only WORKBank importer.

Imports real WORKBank CSV exports into a single **normalized, local** priors
file and exposes them read-only. This is a data-onboarding slice ONLY:

* It reads three CSVs from ``data/imports/workbank/`` (if present), validates
  their columns, joins the worker-survey and expert-rating rows onto each task
  statement, computes per-task averages, and writes
  ``data/priors/workbank_normalized.json``.
* The normalized WORKBank data is **NOT connected to routing, scoring,
  prior-backed scoring, calibration, Monte Carlo, or Project Mode.** Nothing
  about a simulation changes because WORKBank data is present.

No ML, LLM, external API, or database - plain CSV in, JSON out, deterministic.
"""

from __future__ import annotations

import csv
import json
import os
from typing import Dict, List, Optional, Tuple


class WorkbankImportError(ValueError):
    """Raised when a WORKBank file is missing, or has missing/malformed columns."""


SOURCE_NAME = "WORKBank"

# The three expected input files and their required columns.
TASK_FILE = "task_statement_with_metadata.csv"
DESIRES_FILE = "domain_worker_desires.csv"
CAPABILITY_FILE = "expert_rated_technological_capability.csv"

REQUIRED_FILES = (TASK_FILE, DESIRES_FILE, CAPABILITY_FILE)

# Task spine: one row per WORKBank task, carrying identity + requirement metadata.
TASK_REQUIRED_COLS = (
    "task_id",
    "task_statement",
    "occupation_title",
    "onet_soc_code",
    "task_type",
    "physical_action_requirement",
    "uncertainty_or_high_stakes_requirement",
    "domain_expertise_requirement",
    "interpersonal_communication_requirement",
)
# The four 0..1 requirement metadata columns (carried through per task).
TASK_REQUIREMENT_COLS = (
    "physical_action_requirement",
    "uncertainty_or_high_stakes_requirement",
    "domain_expertise_requirement",
    "interpersonal_communication_requirement",
)

# Worker desire survey: many rows per task, averaged.
DESIRES_REQUIRED_COLS = ("task_id", "worker_automation_desire", "worker_desired_has")
# Expert capability ratings: many rows per task, averaged.
CAPABILITY_REQUIRED_COLS = ("task_id", "expert_ai_capability", "expert_feasible_has")


# ---------------------------------------------------------------------------
# Small parsing helpers
# ---------------------------------------------------------------------------

def _norm_text(text: str) -> str:
    """Normalise task text for the stable-text fallback join."""
    return " ".join(str(text or "").lower().split())


def _to_float(value, col: str, ctx: str) -> Optional[float]:
    """Parse a numeric cell. Empty -> None; non-numeric -> clear error."""
    s = str(value).strip() if value is not None else ""
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        raise WorkbankImportError(
            f"{ctx}: column '{col}' has a non-numeric value {value!r}."
        )


def _avg(values: List[Optional[float]]) -> Optional[float]:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 4)


def _read_csv(path: str, required_cols, label: str) -> List[dict]:
    """Read a CSV into a list of row dicts, validating required columns.

    Raises ``WorkbankImportError`` with a clear message when the file is missing
    or a required column is absent.
    """
    if not os.path.exists(path):
        raise WorkbankImportError(
            f"Missing required WORKBank file: {label} (expected at {path})."
        )
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            fieldnames = [c.strip() for c in (reader.fieldnames or [])]
            missing = [c for c in required_cols if c not in fieldnames]
            if missing:
                raise WorkbankImportError(
                    f"{label}: missing required column(s): {missing}. "
                    f"Found columns: {fieldnames}."
                )
            rows = []
            for raw in reader:
                # Strip header whitespace so lookups by clean name work.
                rows.append({(k.strip() if k else k): v for k, v in raw.items()})
            return rows
    except WorkbankImportError:
        raise
    except OSError as exc:
        raise WorkbankImportError(f"{label}: could not read file: {exc}")


# ---------------------------------------------------------------------------
# Core normalisation
# ---------------------------------------------------------------------------

def _source_confidence(worker_n: int, expert_n: int) -> float:
    """Deterministic per-task confidence from data coverage.

    Both worker desires and expert ratings present -> 1.0; only one -> 0.7;
    neither -> 0.4. (Sample sizes beyond presence do not change it here.)
    """
    return round(0.4 + 0.3 * (worker_n > 0) + 0.3 * (expert_n > 0), 2)


def _resolve_task(row: dict, by_id: dict, by_text: dict):
    """Resolve a desires/capability row to a task: by task_id, else task text."""
    tid = str(row.get("task_id", "") or "").strip()
    if tid and tid in by_id:
        return by_id[tid]
    # Stable text fallback (only if the row carries a task statement/text).
    text = row.get("task_statement") or row.get("task_text") or ""
    key = _norm_text(text)
    if key and key in by_text:
        return by_text[key]
    return None


def normalize_workbank(import_dir: str) -> dict:
    """Read + validate + join the three CSVs into the normalized result dict.

    Does NOT write anything. Raises ``WorkbankImportError`` on missing files or
    missing/malformed columns. Returns the result payload (see ``import_status``
    set by the caller).
    """
    task_rows = _read_csv(
        os.path.join(import_dir, TASK_FILE), TASK_REQUIRED_COLS, TASK_FILE
    )
    desire_rows = _read_csv(
        os.path.join(import_dir, DESIRES_FILE), DESIRES_REQUIRED_COLS, DESIRES_FILE
    )
    capability_rows = _read_csv(
        os.path.join(import_dir, CAPABILITY_FILE),
        CAPABILITY_REQUIRED_COLS, CAPABILITY_FILE,
    )

    warnings: List[str] = []

    # Build the task spine + lookup indexes (by id and by normalized text).
    records: List[dict] = []
    by_id: Dict[str, dict] = {}
    by_text: Dict[str, dict] = {}
    # Accumulators keyed by the task record's identity (id() of the dict).
    worker_desire: Dict[int, list] = {}
    worker_has: Dict[int, list] = {}
    expert_cap: Dict[int, list] = {}
    expert_has: Dict[int, list] = {}

    for i, row in enumerate(task_rows):
        ctx = f"{TASK_FILE}[row {i + 1}]"
        tid = str(row.get("task_id", "") or "").strip()
        text = str(row.get("task_statement", "") or "").strip()
        if not tid and not text:
            warnings.append(f"{ctx}: row has neither task_id nor task_statement; skipped.")
            continue
        requirement_vals = {
            col: _to_float(row.get(col), col, ctx) for col in TASK_REQUIREMENT_COLS
        }
        record = {
            "workbank_task_id": tid,
            "task_text": text,
            "occupation_title": str(row.get("occupation_title", "") or "").strip(),
            "onet_soc_code": str(row.get("onet_soc_code", "") or "").strip(),
            "task_type": str(row.get("task_type", "") or "").strip(),
            "avg_worker_automation_desire": None,
            "avg_expert_ai_capability": None,
            "avg_worker_desired_has": None,
            "avg_expert_feasible_has": None,
            **requirement_vals,
            "worker_sample_count": 0,
            "expert_sample_count": 0,
            "source_name": SOURCE_NAME,
            "source_confidence": 0.0,
            "notes": "",
        }
        records.append(record)
        key = id(record)
        worker_desire[key], worker_has[key] = [], []
        expert_cap[key], expert_has[key] = [], []
        if tid:
            if tid in by_id:
                warnings.append(f"{ctx}: duplicate task_id {tid!r}; later row wins for joins.")
            by_id[tid] = record
        if text:
            by_text[_norm_text(text)] = record

    # Join worker desires.
    for i, row in enumerate(desire_rows):
        ctx = f"{DESIRES_FILE}[row {i + 1}]"
        rec = _resolve_task(row, by_id, by_text)
        if rec is None:
            warnings.append(
                f"{ctx}: references unknown task (task_id="
                f"{str(row.get('task_id', '') or '').strip()!r}); skipped."
            )
            continue
        key = id(rec)
        worker_desire[key].append(_to_float(row.get("worker_automation_desire"),
                                            "worker_automation_desire", ctx))
        worker_has[key].append(_to_float(row.get("worker_desired_has"),
                                         "worker_desired_has", ctx))

    # Join expert capability ratings.
    for i, row in enumerate(capability_rows):
        ctx = f"{CAPABILITY_FILE}[row {i + 1}]"
        rec = _resolve_task(row, by_id, by_text)
        if rec is None:
            warnings.append(
                f"{ctx}: references unknown task (task_id="
                f"{str(row.get('task_id', '') or '').strip()!r}); skipped."
            )
            continue
        key = id(rec)
        expert_cap[key].append(_to_float(row.get("expert_ai_capability"),
                                         "expert_ai_capability", ctx))
        expert_has[key].append(_to_float(row.get("expert_feasible_has"),
                                         "expert_feasible_has", ctx))

    # Finalise per-task averages, counts, confidence, and notes.
    for rec in records:
        key = id(rec)
        wn = len(worker_desire[key])
        en = len(expert_cap[key])
        rec["avg_worker_automation_desire"] = _avg(worker_desire[key])
        rec["avg_worker_desired_has"] = _avg(worker_has[key])
        rec["avg_expert_ai_capability"] = _avg(expert_cap[key])
        rec["avg_expert_feasible_has"] = _avg(expert_has[key])
        rec["worker_sample_count"] = wn
        rec["expert_sample_count"] = en
        rec["source_confidence"] = _source_confidence(wn, en)
        rec["notes"] = f"worker n={wn}, expert n={en}."
        if wn == 0:
            warnings.append(f"Task {rec['workbank_task_id'] or rec['task_text']!r}: no worker desire rows.")
        if en == 0:
            warnings.append(f"Task {rec['workbank_task_id'] or rec['task_text']!r}: no expert capability rows.")

    occupations = sorted({r["occupation_title"] for r in records if r["occupation_title"]})
    return {
        "import_status": "imported",
        "source_name": SOURCE_NAME,
        "task_count": len(records),
        "occupation_count": len(occupations),
        "normalized_priors": records,
        "validation_warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def import_workbank(import_dir: str, output_path: Optional[str] = None) -> dict:
    """Normalize the WORKBank CSVs and (optionally) write the JSON output.

    Raises ``WorkbankImportError`` if any file is missing or has missing/
    malformed columns. When ``output_path`` is given, the normalized result is
    written there as pretty JSON.
    """
    result = normalize_workbank(import_dir)
    if output_path is not None:
        write_normalized(output_path, result)
    return result


def write_normalized(output_path: str, result: dict) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)


def load_normalized(output_path: str) -> dict:
    """Load a previously written normalized WORKBank file."""
    with open(output_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _empty(status: str, warnings: List[str]) -> dict:
    return {
        "import_status": status,
        "source_name": SOURCE_NAME,
        "task_count": 0,
        "occupation_count": 0,
        "normalized_priors": [],
        "validation_warnings": warnings,
    }


def workbank_status(import_dir: str, output_path: str) -> dict:
    """Resolve the WORKBank import for the API, never raising.

    Priority: if all three CSVs are present, (re)import them (writing the
    normalized JSON) and report ``imported``; else fall back to a previously
    written normalized JSON if one exists; else report ``not_imported`` with a
    warning naming the missing files. Malformed input -> ``error`` + message.
    """
    missing = [f for f in REQUIRED_FILES if not os.path.exists(os.path.join(import_dir, f))]
    if not missing:
        try:
            return import_workbank(import_dir, output_path)
        except WorkbankImportError as exc:
            return _empty("error", [str(exc)])

    if os.path.exists(output_path):
        try:
            data = load_normalized(output_path)
            data.setdefault("import_status", "imported")
            data.setdefault("validation_warnings", [])
            data["validation_warnings"] = list(data["validation_warnings"]) + [
                "Loaded from a previously imported normalized file; "
                f"current import folder is missing: {missing}."
            ]
            return data
        except (OSError, json.JSONDecodeError):
            pass

    return _empty(
        "not_imported",
        [
            f"WORKBank import file(s) not found: {missing}. "
            f"Place the CSVs in {import_dir} to import."
        ],
    )
