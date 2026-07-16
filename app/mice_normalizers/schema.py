"""Canonical MICE event schema helpers."""
from __future__ import annotations

from typing import Any


RECORD_DOMAIN = "MICE_EVENT"

EVENT_TYPES = frozenset(
    {
        "EXHIBITION",
        "CONVENTION",
        "CONFERENCE",
        "FORUM",
        "SEMINAR",
        "ACADEMIC_CONFERENCE",
        "SYMPOSIUM",
        "GENERAL_MEETING",
        "FESTIVAL",
        "EXPORT_CONSULTATION",
        "BUSINESS_MATCHING",
        "INVESTMENT_IR",
        "OPEN_INNOVATION",
        "DEMO_DAY",
        "NETWORKING",
        "OTHER",
    }
)

CONTACT_CONFIDENCE = frozenset(
    {
        "VERIFIED_PUBLIC_EVENT_PAGE",
        "VERIFIED_PUBLIC_OFFICIAL_SOURCE",
        "DEPARTMENT_ONLY",
        "GENERAL_CONTACT",
        "UNKNOWN",
    }
)

SALES_SIGNAL_TYPES = frozenset(
    {
        "REGISTRATION",
        "CHECKIN",
        "BADGE_PRINTING",
        "ACCESS_CONTROL",
        "EVENT_WEBSITE",
        "ONLINE_BOOTH",
        "EXHIBITOR_LEAD",
        "BUSINESS_MATCHING",
        "MEETING_SCHEDULING",
        "SESSION_MANAGEMENT",
        "PARTICIPANT_DATABASE",
        "MESSAGE_NOTIFICATION",
        "MULTILINGUAL",
        "DASHBOARD_REPORT",
        "ONSITE_OPERATION",
        "TOURISM_EXTENSION",
        "ORGANIZER_OUTREACH",
        "PCO_PARTNERSHIP",
    }
)

SALES_READINESS = frozenset(
    {
        "DIRECT_OPPORTUNITY",
        "CONTACTABLE",
        "RESEARCH",
        "WATCH",
        "NONE",
    }
)

EMPTY_EVENT: dict[str, Any] = {
    "event_id": None,
    "canonical_event_id": None,
    "record_domain": RECORD_DOMAIN,
    "source_id": None,
    "source_event_id": None,
    "source_occurrences": [],
    "title": None,
    "title_en": None,
    "title_normalized": None,
    "event_type": None,
    "event_status": None,
    "start_date": None,
    "end_date": None,
    "date_text": None,
    "venue_name": None,
    "venue_normalized": None,
    "venue_address": None,
    "city": None,
    "region": None,
    "country": None,
    "host_organizations": [],
    "organizer_organizations": [],
    "operator_organizations": [],
    "pco_organizations": [],
    "official_event_url": None,
    "source_url": None,
    "registration_url": None,
    "exhibitor_recruitment_url": None,
    "buyer_recruitment_url": None,
    "participant_recruitment_url": None,
    "industries": [],
    "categories": [],
    "extracted_keywords": [],
    "description_summary": None,
    "expected_participants": None,
    "expected_exhibitors": None,
    "expected_booths": None,
    "contact_department": None,
    "contact_name": None,
    "contact_role": None,
    "contact_email": None,
    "contact_phone": None,
    "contact_source_url": None,
    "contact_confidence": None,
    "sales_signal_types": [],
    "sales_signal_basis": [],
    "sales_readiness": "NONE",
    "qrpick_service_matches": [],
    "suggested_sales_action": None,
    "needs_official_verification": False,
    "duplicate_group_id": None,
    "duplicate_count": 1,
    "collected_at": None,
    "raw_file": None,
}


def new_event(**overrides: Any) -> dict[str, Any]:
    row = {k: (list(v) if isinstance(v, list) else v) for k, v in EMPTY_EVENT.items()}
    row.update(overrides)
    row["record_domain"] = RECORD_DOMAIN
    return row
