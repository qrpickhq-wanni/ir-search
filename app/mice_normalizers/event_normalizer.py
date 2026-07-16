"""Map intermediate collector fields + raw rows into MICE event schema."""
from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any

from app.mice_normalizers.date_utils import in_collection_window, parse_mice_date_range
from app.mice_normalizers.sales_signals import apply_sales_layer
from app.mice_normalizers.schema import new_event
from app.mice_normalizers.text_utils import (
    collapse_whitespace,
    extract_email,
    extract_phone,
    normalize_title,
    normalize_venue,
    split_org_list,
)


_TYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("EXPORT_CONSULTATION", ("수출상담", "수출 상담")),
    ("BUSINESS_MATCHING", ("비즈니스 매칭", "비즈매칭", "buyer matching", "상담회", "매칭데이")),
    ("INVESTMENT_IR", ("투자설명", "ir 데이", "ir데이", "데모데이")),
    ("DEMO_DAY", ("데모데이", "demo day")),
    ("OPEN_INNOVATION", ("오픈이노베이션", "open innovation")),
    ("ACADEMIC_CONFERENCE", ("학술대회", "학술회의", "학회")),
    ("SYMPOSIUM", ("심포지엄", "symposium")),
    ("FORUM", ("포럼", "forum")),
    ("SEMINAR", ("세미나", "seminar")),
    ("GENERAL_MEETING", ("총회", "정기총회")),
    ("CONVENTION", ("컨벤션", "convention")),
    ("CONFERENCE", ("콘퍼런스", "컨퍼런스", "conference", "congress")),
    ("EXHIBITION", ("전시회", "박람회", "엑스포", "엑어", "expo", "fair", "전시")),
    ("FESTIVAL", ("페스티벌", "festival", "축제")),
    ("NETWORKING", ("네트워킹", "networking")),
]


def infer_event_type(title: str | None, category: str | None = None) -> tuple[str, list[str]]:
    """Pick one primary type; extra keyword hits go to extracted_keywords."""
    hay = f"{title or ''} {category or ''}".casefold()
    hits: list[str] = []
    primary: str | None = None
    for etype, kws in _TYPE_RULES:
        if any(kw.casefold() in hay for kw in kws):
            hits.append(etype)
            if primary is None:
                primary = etype
    if primary is None and category:
        c = category.strip()
        if c in {"전시", "박람회"}:
            primary = "EXHIBITION"
        elif c in {"컨퍼런스", "학술"}:
            primary = "CONFERENCE"
        elif c in {"세미나"}:
            primary = "SEMINAR"
        elif c in {"회의", "기타"}:
            primary = "OTHER"
    return primary or "OTHER", hits[1:]


def _event_id(source_id: str, source_event_id: str | None, title: str | None, start: str | None) -> str:
    base = f"{source_id}|{source_event_id or ''}|{title or ''}|{start or ''}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    sid = (source_event_id or "na").replace(" ", "")[:24]
    return f"{source_id}:{sid}:{digest}"


def _parse_participants(text: str | None) -> int | None:
    if not text or text in {"-", "—"}:
        return None
    m = re.search(r"(\d[\d,]*)", str(text))
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def normalize_intermediate(
    intermediate: dict[str, Any],
    *,
    source_id: str,
    raw_file: str,
    today: date,
    past_days: int,
    future_days: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return (event, error_message).

    outside_date_window: drop (filter, not a parse failure).
    date parse failure with valid title: keep with null dates + needs_official_verification.
    """
    title = collapse_whitespace(intermediate.get("title")) or None
    if not title:
        return None, "missing_title"

    start, end, date_text = parse_mice_date_range(
        intermediate.get("start_date_raw"),
        intermediate.get("end_date_raw"),
        intermediate.get("date_text"),
    )
    date_parse_failed = bool(
        (intermediate.get("start_date_raw") or intermediate.get("end_date_raw") or intermediate.get("date_text"))
        and not start
        and not end
    )

    if not in_collection_window(
        start,
        end,
        today=today,
        past_days=past_days,
        future_days=future_days,
    ):
        # Unknown dates (null,null) are kept by in_collection_window; dated-out events drop.
        return None, "outside_date_window"

    event_type, extra_types = infer_event_type(title, intermediate.get("category_raw"))

    host = split_org_list(intermediate.get("host_raw"))
    organizer = split_org_list(intermediate.get("organizer_raw"))
    operator = split_org_list(intermediate.get("operator_raw"))
    pco = split_org_list(intermediate.get("pco_raw"))

    needs_verify = bool(date_parse_failed)
    host_raw = intermediate.get("host_raw")
    if host_raw and any(k in str(host_raw) for k in ("주최", "주관", "운영")) and not organizer:
        needs_verify = True
    if intermediate.get("needs_host_role_check"):
        needs_verify = True

    email = intermediate.get("contact_email") or extract_email(intermediate.get("inquiry_raw"))
    phone = intermediate.get("contact_phone") or extract_phone(intermediate.get("inquiry_raw"))
    # Never invent email from name
    contact_conf = None
    contact_source = None
    if email or phone or intermediate.get("contact_department") or intermediate.get("contact_name"):
        contact_source = intermediate.get("source_url")
        if email or phone:
            contact_conf = "VERIFIED_PUBLIC_OFFICIAL_SOURCE"
        elif intermediate.get("contact_department"):
            contact_conf = "DEPARTMENT_ONLY"
        else:
            contact_conf = "GENERAL_CONTACT"

    venue_name = collapse_whitespace(intermediate.get("venue_name")) or None
    if venue_name in {"-", "—"}:
        venue_name = None

    categories: list[str] = []
    if intermediate.get("category_raw"):
        categories.append(str(intermediate["category_raw"]).strip())
    keywords = list(extra_types)
    if intermediate.get("location_raw"):
        keywords.append(f"location:{intermediate['location_raw']}")

    source_event_id = intermediate.get("source_event_id")
    if source_event_id is not None:
        source_event_id = str(source_event_id)

    eid = _event_id(source_id, source_event_id, title, start)
    occurrence = {
        "source_id": source_id,
        "source_event_id": source_event_id,
        "source_url": intermediate.get("source_url"),
        "collected_at": intermediate.get("collected_at"),
        "occurrence_uid": eid,
    }

    status = None
    try:
        if end and date.fromisoformat(end) < today:
            status = "ENDED"
        elif start and date.fromisoformat(start) > today:
            status = "UPCOMING"
        elif start and end:
            status = "ONGOING"
        elif date_parse_failed:
            status = None
    except ValueError:
        status = None

    official = intermediate.get("official_event_url") or intermediate.get("homepage")
    if official in {"-", "—", ""}:
        official = None

    reg_url = intermediate.get("registration_url")
    exhib_url = intermediate.get("exhibitor_recruitment_url")
    buyer_url = intermediate.get("buyer_recruitment_url")
    part_url = intermediate.get("participant_recruitment_url")

    event = new_event(
        event_id=eid,
        canonical_event_id=eid,
        source_id=source_id,
        source_event_id=source_event_id,
        source_occurrences=[occurrence],
        title=title,
        title_en=collapse_whitespace(intermediate.get("title_en")) or None,
        title_normalized=normalize_title(title),
        event_type=event_type,
        event_status=status,
        start_date=start,
        end_date=end,
        date_text=date_text,
        venue_name=venue_name,
        venue_normalized=normalize_venue(venue_name) or None,
        venue_address=collapse_whitespace(intermediate.get("venue_address")) or None,
        city=collapse_whitespace(intermediate.get("city")) or None,
        region=collapse_whitespace(intermediate.get("region")) or None,
        country=intermediate.get("country") or "KR",
        host_organizations=host,
        organizer_organizations=organizer,
        operator_organizations=operator,
        pco_organizations=pco,
        official_event_url=official,
        source_url=intermediate.get("source_url"),
        registration_url=reg_url,
        exhibitor_recruitment_url=exhib_url,
        buyer_recruitment_url=buyer_url,
        participant_recruitment_url=part_url,
        categories=categories,
        extracted_keywords=keywords,
        description_summary=collapse_whitespace(intermediate.get("description_summary")) or None,
        expected_participants=_parse_participants(intermediate.get("expected_participants_raw")),
        contact_department=intermediate.get("contact_department"),
        contact_name=intermediate.get("contact_name"),
        contact_email=email,
        contact_phone=phone,
        contact_source_url=contact_source,
        contact_confidence=contact_conf,
        needs_official_verification=needs_verify,
        collected_at=intermediate.get("collected_at"),
        raw_file=raw_file,
    )
    apply_sales_layer(event, today=today, intermediate=intermediate)
    return event, None
