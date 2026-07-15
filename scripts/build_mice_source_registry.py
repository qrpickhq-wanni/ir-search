"""Validate config/mice-source-registry.yaml and emit reports/mice-source-audit.csv.

The YAML file is the sole source of truth for MICE source metadata.
This script must not hardcode per-source records.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "mice-source-registry.yaml"
CSV_PATH = ROOT / "reports" / "mice-source-audit.csv"

REQUIRED_FIELDS = [
    "source_id",
    "source_name",
    "source_category",
    "owner_organization",
    "base_url",
    "list_urls",
    "coverage_region",
    "data_types",
    "source_role",
    "original_or_aggregator",
    "official_source_priority",
    "login_required",
    "robots_status",
    "terms_status",
    "commercial_use_status",
    "rendering_type",
    "api_or_xhr_status",
    "pagination_type",
    "update_frequency",
    "sample_fields",
    "contact_fields_available",
    "organizer_fields_available",
    "official_event_url_available",
    "procurement_information_available",
    "historical_event_available",
    "technical_grade",
    "legal_operational_grade",
    "business_value_grade",
    "implementation_priority",
    "audit_status",
    "evidence_urls",
    "existing_audit_reference",
    "audit_date",
    "notes",
]

SOURCE_ROLE = {
    "PRIMARY_OFFICIAL",
    "REGIONAL_OFFICIAL",
    "VENUE_CALENDAR",
    "ASSOCIATION_CALENDAR",
    "ORGANIZER_SOURCE",
    "PROCUREMENT_SOURCE",
    "COMMERCIAL_AGGREGATOR",
    "DISCOVERY_ONLY",
}

DATA_TYPES = {
    "MICE_EVENT",
    "MICE_TENDER",
    "MICE_SUPPORT_NOTICE",
    "MICE_OPEN_INNOVATION",
    "EXHIBITOR_RECRUITMENT",
    "BUYER_RECRUITMENT",
    "PARTICIPANT_RECRUITMENT",
    "ORGANIZER_SIGNAL",
    "SALES_LEAD",
}

TECHNICAL_GRADE = {"A", "B", "C", "D"}
LEGAL_GRADE = {"A", "B", "C", "D"}
BUSINESS_GRADE = {"A", "B", "C", "D"}
PRIORITY = {"P0", "P1", "P2", "HOLD", "EXCLUDE"}
AUDIT_STATUS = {
    "INHERITED_EXISTING_AUDIT",
    "VERIFIED_EXISTING_AUDIT",
    "NEWLY_AUDITED",
    "PARTIAL",
    "PENDING",
    "EXCLUDED",
}

SOURCE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

# Snapshot from 2026-07-15 landscape audit report (must match until YAML intentionally changes).
BASELINE_STATS = {
    "count": 38,
    "technical_grade": {"A": 12, "B": 21, "C": 3, "D": 2},
    "legal_operational_grade": {"A": 4, "B": 28, "C": 5, "D": 1},
    "implementation_priority": {
        "P0": 12,
        "P1": 13,
        "P2": 5,
        "HOLD": 6,
        "EXCLUDE": 2,
    },
    "source_category": {
        "NATIONAL_PUBLIC_MICE": 4,
        "COMMERCIAL_PLATFORM": 3,
        "VENUE": 12,
        "REGIONAL_CVB": 8,
        "ASSOCIATION": 5,
        "ORGANIZER_EXPORT": 1,
        "PROCUREMENT": 3,
        "MEDIA": 2,
    },
}


def _is_http_url(value: str) -> bool:
    try:
        p = urlparse(value)
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    if not p.netloc:
        return False
    return True


def _is_evidence_ref(value: str) -> bool:
    if not value or not isinstance(value, str):
        return False
    if _is_http_url(value):
        return True
    # Repo-relative evidence paths (docs/, logs/, README, etc.)
    if value.startswith(("docs/", "logs/", "config/", "reports/", "README")):
        return True
    return False


def load_registry(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("registry root must be a mapping")
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("registry.sources must be a non-empty list")
    return data


def validate_sources(sources: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()

    for i, src in enumerate(sources):
        if not isinstance(src, dict):
            errors.append(f"sources[{i}]: must be a mapping")
            continue
        label = src.get("source_id") or f"#{i}"

        for field in REQUIRED_FIELDS:
            if field not in src:
                errors.append(f"{label}: missing required field '{field}'")

        sid = src.get("source_id")
        if not isinstance(sid, str) or not SOURCE_ID_RE.match(sid):
            errors.append(f"{label}: invalid source_id format")
        elif sid in seen:
            errors.append(f"{label}: duplicate source_id")
        else:
            seen.add(sid)

        role = src.get("source_role")
        if role not in SOURCE_ROLE:
            errors.append(f"{label}: invalid source_role '{role}'")

        dts = src.get("data_types")
        if not isinstance(dts, list) or not dts:
            errors.append(f"{label}: data_types must be a non-empty list")
        else:
            for dt in dts:
                if dt not in DATA_TYPES:
                    errors.append(f"{label}: invalid data_type '{dt}'")

        for grade_field, allowed in (
            ("technical_grade", TECHNICAL_GRADE),
            ("legal_operational_grade", LEGAL_GRADE),
            ("business_value_grade", BUSINESS_GRADE),
        ):
            g = src.get(grade_field)
            if g not in allowed:
                errors.append(f"{label}: invalid {grade_field} '{g}'")

        prio = src.get("implementation_priority")
        if prio not in PRIORITY:
            errors.append(f"{label}: invalid implementation_priority '{prio}'")

        status = src.get("audit_status")
        if status not in AUDIT_STATUS:
            errors.append(f"{label}: invalid audit_status '{status}'")

        for bool_field in (
            "login_required",
            "contact_fields_available",
            "organizer_fields_available",
            "official_event_url_available",
            "procurement_information_available",
            "historical_event_available",
        ):
            if bool_field in src and not isinstance(src[bool_field], bool):
                errors.append(f"{label}: {bool_field} must be boolean")

        priority_n = src.get("official_source_priority")
        if not isinstance(priority_n, int) or not (1 <= priority_n <= 6):
            errors.append(f"{label}: official_source_priority must be int 1..6")

        base = src.get("base_url")
        if not isinstance(base, str) or not _is_http_url(base):
            # Allow empty only if PENDING and no working URL — still require valid or explicit empty with audit?
            # Spec: URL format validation — base_url should be http(s).
            if base not in (None, "") and not (isinstance(base, str) and _is_http_url(base)):
                errors.append(f"{label}: invalid base_url '{base}'")
            elif not isinstance(base, str) or not _is_http_url(base):
                errors.append(f"{label}: base_url must be http(s) URL")

        list_urls = src.get("list_urls", [])
        if list_urls is None:
            list_urls = []
        if not isinstance(list_urls, list):
            errors.append(f"{label}: list_urls must be a list")
        else:
            for u in list_urls:
                if not isinstance(u, str) or not _is_http_url(u):
                    errors.append(f"{label}: invalid list_url '{u}'")

        evidence = src.get("evidence_urls", [])
        if evidence is None:
            evidence = []
        if not isinstance(evidence, list):
            errors.append(f"{label}: evidence_urls must be a list")
        else:
            for u in evidence:
                if not _is_evidence_ref(u):
                    errors.append(f"{label}: invalid evidence ref '{u}'")

        for list_field in ("sample_fields",):
            v = src.get(list_field)
            if v is None:
                continue
            if not isinstance(v, list):
                errors.append(f"{label}: {list_field} must be a list")

        ref = src.get("existing_audit_reference")
        if ref is None:
            errors.append(f"{label}: existing_audit_reference missing")
        elif ref != "" and not isinstance(ref, str):
            errors.append(f"{label}: existing_audit_reference must be string")

        notes = src.get("notes")
        if notes is not None and not isinstance(notes, str):
            errors.append(f"{label}: notes must be string")

        date = src.get("audit_date")
        if not isinstance(date, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            errors.append(f"{label}: audit_date must be YYYY-MM-DD")

    return errors


def compute_stats(sources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(sources),
        "technical_grade": dict(Counter(s["technical_grade"] for s in sources)),
        "legal_operational_grade": dict(
            Counter(s["legal_operational_grade"] for s in sources)
        ),
        "implementation_priority": dict(
            Counter(s["implementation_priority"] for s in sources)
        ),
        "source_category": dict(Counter(s["source_category"] for s in sources)),
        "business_value_grade": dict(Counter(s["business_value_grade"] for s in sources)),
        "audit_status": dict(Counter(s["audit_status"] for s in sources)),
    }


def stats_match(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if actual["count"] != expected["count"]:
        errors.append(f"count: actual={actual['count']} expected={expected['count']}")
    for key in (
        "technical_grade",
        "legal_operational_grade",
        "implementation_priority",
        "source_category",
    ):
        a = actual.get(key, {})
        e = expected.get(key, {})
        if a != e:
            errors.append(f"{key}: actual={a} expected={e}")
    return errors


def write_csv(sources: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REQUIRED_FIELDS, extrasaction="ignore")
        w.writeheader()
        for src in sources:
            row = {k: src.get(k, "") for k in REQUIRED_FIELDS}
            for k in ("list_urls", "data_types", "sample_fields", "evidence_urls"):
                v = row.get(k) or []
                row[k] = "|".join(v) if isinstance(v, list) else v
            w.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-baseline",
        action="store_true",
        help="Do not enforce BASELINE_STATS snapshot match",
    )
    args = parser.parse_args()

    if not REGISTRY_PATH.is_file():
        print(f"ERROR: missing registry {REGISTRY_PATH}", file=sys.stderr)
        return 2

    registry = load_registry(REGISTRY_PATH)
    sources = registry["sources"]

    errors = validate_sources(sources)
    if errors:
        print(f"ERROR: {len(errors)} validation failure(s)", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    stats = compute_stats(sources)
    if not args.skip_baseline:
        baseline_errors = stats_match(stats, BASELINE_STATS)
        if baseline_errors:
            print("ERROR: baseline stats mismatch", file=sys.stderr)
            for e in baseline_errors:
                print(f"  - {e}", file=sys.stderr)
            return 1

    write_csv(sources, CSV_PATH)

    print("authority=config/mice-source-registry.yaml")
    print("artifact=reports/mice-source-audit.csv")
    print("source_count", stats["count"])
    print("technical_grade", stats["technical_grade"])
    print("legal_operational_grade", stats["legal_operational_grade"])
    print("business_value_grade", stats["business_value_grade"])
    print("implementation_priority", stats["implementation_priority"])
    print("source_category", stats["source_category"])
    print("audit_status", stats["audit_status"])
    print("baseline_ok", not args.skip_baseline)
    print("wrote", CSV_PATH.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
