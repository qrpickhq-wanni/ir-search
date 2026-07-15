"""Normalize multi-source (bizinfo/nipa/kocca/smtech) list records."""
from __future__ import annotations

from datetime import date
from typing import Any

from app.normalizers.base import (
    coerce_date_fields,
    empty_record,
    finalize_text_keys,
    make_occurrence,
    make_opportunity_id,
)

ALLOWED_SOURCES = {"bizinfo", "nipa", "kocca", "smtech"}


def normalize_sources_row(row: dict[str, Any], *, raw_file: str, today: date | None = None) -> dict[str, Any]:
    source = str(row.get("source") or "").strip().lower()
    if source not in ALLOWED_SOURCES:
        raise ValueError(f"unsupported source: {source!r}")

    source_id = str(row.get("id") or "").strip()
    if not source_id:
        raise ValueError("missing id")

    title = row.get("title")
    if not title or not str(title).strip():
        raise ValueError("missing title")

    dates = coerce_date_fields(
        application_start_raw=row.get("apply_start"),
        deadline_raw=row.get("apply_end"),
        posted_raw=row.get("reg_date"),
    )

    rec = empty_record()
    rec.update(
        {
            "source": source,
            "source_id": source_id,
            "opportunity_id": make_opportunity_id(source, source_id),
            "canonical_id": make_opportunity_id(source, source_id),
            "title": str(title).strip(),
            "program": (str(row["field"]).strip() if row.get("field") else None),
            "organization": (str(row["org"]).strip() if row.get("org") else None),
            "agency_type": None,
            "category": (str(row["field"]).strip() if row.get("field") else None),
            "posted_at": dates["posted_at"],
            "application_start": dates["application_start"],
            "deadline": dates["deadline"],
            "deadline_text": dates["deadline_text"] or row.get("apply_end"),
            "url": row.get("url"),
            "detail_url": row.get("url"),
            "raw_file": raw_file,
            "source_occurrences": [
                make_occurrence(source, source_id, row.get("url"), raw_file)
            ],
        }
    )
    return finalize_text_keys(rec, today=today)
