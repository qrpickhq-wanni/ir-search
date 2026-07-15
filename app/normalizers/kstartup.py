"""Normalize K-Startup list records into the standard schema."""
from __future__ import annotations

from datetime import date
from typing import Any

from app.normalizers.base import (
    empty_record,
    finalize_text_keys,
    make_occurrence,
    make_opportunity_id,
    coerce_date_fields,
)


SOURCE = "kstartup"


def normalize_kstartup_row(row: dict[str, Any], *, raw_file: str, today: date | None = None) -> dict[str, Any]:
    source_id = str(row.get("pbancSn") or "").strip()
    if not source_id:
        raise ValueError("missing pbancSn")

    title = row.get("title")
    if not title or not str(title).strip():
        raise ValueError("missing title")

    dates = coerce_date_fields(
        application_start_raw=row.get("start"),
        deadline_raw=row.get("deadline"),
        posted_raw=None,
    )

    rec = empty_record()
    rec.update(
        {
            "source": SOURCE,
            "source_id": source_id,
            "opportunity_id": make_opportunity_id(SOURCE, source_id),
            "canonical_id": make_opportunity_id(SOURCE, source_id),
            "title": str(title).strip(),
            "program": (str(row["program"]).strip() if row.get("program") else None),
            "organization": (str(row["org"]).strip() if row.get("org") else None),
            "agency_type": (str(row["agency_type"]).strip() if row.get("agency_type") else None),
            "category": (str(row["category"]).strip() if row.get("category") else None),
            "application_start": dates["application_start"],
            "deadline": dates["deadline"],
            "deadline_text": dates["deadline_text"] or row.get("deadline"),
            "dday": (str(row["dday"]).strip() if row.get("dday") else None),
            "url": row.get("url"),
            "detail_url": row.get("url"),
            "raw_file": raw_file,
            "source_occurrences": [
                make_occurrence(SOURCE, source_id, row.get("url"), raw_file)
            ],
        }
    )
    return finalize_text_keys(rec, today=today)
