"""Shared opportunity record helpers."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any

from app.normalizers.date_utils import dday_from_deadline, parse_date
from app.normalizers.text_utils import normalize_organization, normalize_title


EMPTY_LIST_FIELDS = (
    "source_occurrences",
    "attachment_urls",
    "positive_reasons",
    "negative_reasons",
    "review_reasons",
    "asset_fit_reasons",
    "usable_qrpick_features",
    "usable_showda_assets",
    "new_development_scope",
    "partner_required_scope",
)


def empty_record() -> dict[str, Any]:
    return {
        "opportunity_id": None,
        "canonical_id": None,
        "source": None,
        "source_id": None,
        "source_occurrences": [],
        "title": None,
        "title_normalized": None,
        "program": None,
        "organization": None,
        "organization_normalized": None,
        "agency_type": None,
        "category": None,
        "category_normalized": None,
        "posted_at": None,
        "application_start": None,
        "deadline": None,
        "deadline_text": None,
        "dday": None,
        "region": None,
        "support_type": None,
        "support_amount": None,
        "applicant_summary": None,
        "url": None,
        "detail_url": None,
        "attachment_urls": [],
        "collected_at": None,
        "raw_file": None,
        "duplicate_group_id": None,
        "duplicate_count": 1,
        "first_pass_status": None,
        "first_pass_score": None,
        "positive_reasons": [],
        "negative_reasons": [],
        "review_reasons": [],
        "needs_detail_review": False,
        "asset_fit_path": None,
        "primary_asset_fit_path": None,
        "secondary_asset_fit_paths": [],
        "commercialization_path": None,
        "matched_asset_families": [],
        "fit_confidence": None,
        "fit_evidence": [],
        "evidence_source": None,
        "opportunity_type": None,
        "action_queue": None,
        "recommended_next_action": None,
        "detail_verification_status": "NOT_FETCHED",
        "actionability_verified": False,
        "actionability_gate_reasons": [],
        "blocking_unknowns": [],
        "action_promotion_source": "RULE",
        "asset_fit_reasons": [],
        "usable_qrpick_features": [],
        "usable_showda_assets": [],
        "new_development_scope": [],
        "partner_required_scope": [],
        "opportunity_kind": None,
        "next_action": None,
    }


def make_opportunity_id(source: str, source_id: str) -> str:
    return f"{source}:{source_id}"


def make_occurrence(source: str, source_id: str, url: str | None, raw_file: str) -> dict[str, Any]:
    return {
        "source": source,
        "source_id": source_id,
        "url": url,
        "raw_file": raw_file,
    }


def finalize_text_keys(rec: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    rec["title_normalized"] = normalize_title(rec.get("title"))
    rec["organization_normalized"] = normalize_organization(rec.get("organization"))
    cat = rec.get("category")
    rec["category_normalized"] = normalize_title(cat) if cat else None
    if not rec.get("dday"):
        rec["dday"] = dday_from_deadline(rec.get("deadline"), today=today)
    if not rec.get("detail_url"):
        rec["detail_url"] = rec.get("url")
    if not rec.get("collected_at"):
        rec["collected_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return rec


def richness_score(rec: dict[str, Any]) -> int:
    """Prefer records with denser non-empty scalar fields as merge representatives."""
    keys = (
        "title",
        "program",
        "organization",
        "agency_type",
        "category",
        "posted_at",
        "application_start",
        "deadline",
        "region",
        "url",
        "detail_url",
        "support_type",
        "applicant_summary",
    )
    score = 0
    for k in keys:
        v = rec.get(k)
        if v not in (None, "", [], {}):
            score += 1
            if isinstance(v, str):
                score += min(len(v), 40) // 20
    return score


def merge_fill_blanks(base: dict[str, Any], other: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fill empty fields from other; record conflicts without overwriting."""
    out = deepcopy(base)
    conflicts: list[dict[str, Any]] = []
    skip = {
        "opportunity_id",
        "canonical_id",
        "source",
        "source_id",
        "source_occurrences",
        "duplicate_group_id",
        "duplicate_count",
        "first_pass_status",
        "first_pass_score",
        "positive_reasons",
        "negative_reasons",
        "review_reasons",
        "needs_detail_review",
        "title_normalized",
        "organization_normalized",
        "category_normalized",
    }
    for key, oval in other.items():
        if key in skip:
            continue
        bval = out.get(key)
        empty_b = bval in (None, "", [], {})
        empty_o = oval in (None, "", [], {})
        if empty_b and not empty_o:
            out[key] = deepcopy(oval)
        elif not empty_b and not empty_o and bval != oval:
            # Prefer longer string for title/program; else conflict note
            if key in ("title", "program", "organization") and isinstance(bval, str) and isinstance(oval, str):
                if len(oval) > len(bval) + 5:
                    conflicts.append({"field": key, "kept": bval, "alternate": oval, "action": "kept_longer_base"})
                elif len(bval) > len(oval) + 5:
                    pass
                elif bval != oval:
                    conflicts.append({"field": key, "kept": bval, "alternate": oval, "action": "conflict_kept_base"})
            elif bval != oval:
                conflicts.append({"field": key, "kept": bval, "alternate": oval, "action": "conflict_kept_base"})
    out["title_normalized"] = normalize_title(out.get("title"))
    out["organization_normalized"] = normalize_organization(out.get("organization"))
    return out, conflicts


def coerce_date_fields(
    *,
    application_start_raw: str | None = None,
    deadline_raw: str | None = None,
    posted_raw: str | None = None,
) -> dict[str, Any]:
    deadline_text = deadline_raw
    return {
        "application_start": parse_date(application_start_raw),
        "deadline": parse_date(deadline_raw),
        "deadline_text": deadline_text,
        "posted_at": parse_date(posted_raw),
    }
