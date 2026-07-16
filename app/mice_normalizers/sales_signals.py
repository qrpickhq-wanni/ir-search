"""Evidence-based sales signals vs potential QRPick service matches."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any


_PROCUREMENT_RE = re.compile(
    r"(입찰|용역\s*모집|제안\s*모집|시스템\s*구축|솔루션\s*모집|운영\s*용역|"
    r"제안서\s*접수|RFP|구매\s*공고|사업자\s*선정)",
    re.I,
)
_REG_RE = re.compile(r"(사전\s*등록|참가\s*등록|등록\s*신청|registration)", re.I)
_EXHIBITOR_RE = re.compile(r"(참가\s*기업\s*모집|부스\s*모집|전시\s*참가\s*모집|exhibitor)", re.I)
_BUYER_RE = re.compile(r"(바이어\s*모집|buyer\s*recruit|구매자\s*모집)", re.I)
_MATCH_RE = re.compile(r"(상담\s*신청|비즈\s*매칭|비즈니스\s*매칭|미팅\s*매칭|1[:：]1\s*상담)", re.I)

# Internal / low commercial value title patterns (conservative)
_LOW_VALUE_RE = re.compile(
    r"(온보딩|임직원|직원\s*특강|무료공연|공연|워크숍|설명회|학부모|"
    r"교사\s*워크|내부\s*교육|HR\s*온보딩)",
    re.I,
)


def uniq(xs: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in xs:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def infer_qrpick_service_matches(event_type: str) -> list[str]:
    """Potential QRPick capability fit from event_type only (not a sales claim)."""
    if event_type == "EXHIBITION":
        return ["REGISTRATION", "CHECKIN", "EXHIBITOR_LEAD"]
    if event_type in {
        "CONFERENCE",
        "ACADEMIC_CONFERENCE",
        "SYMPOSIUM",
        "FORUM",
        "SEMINAR",
        "CONVENTION",
    }:
        return ["REGISTRATION", "CHECKIN", "SESSION_MANAGEMENT"]
    if event_type in {"EXPORT_CONSULTATION", "BUSINESS_MATCHING"}:
        return ["BUSINESS_MATCHING", "MEETING_SCHEDULING", "REGISTRATION"]
    if event_type in {"INVESTMENT_IR", "DEMO_DAY", "OPEN_INNOVATION"}:
        return ["REGISTRATION", "PARTICIPANT_DATABASE"]
    if event_type == "NETWORKING":
        return ["REGISTRATION", "CHECKIN"]
    if event_type == "GENERAL_MEETING":
        return ["REGISTRATION", "CHECKIN", "SESSION_MANAGEMENT"]
    return []


def _haystack(event: dict[str, Any], intermediate: dict[str, Any] | None = None) -> str:
    parts = [
        event.get("title"),
        event.get("description_summary"),
        " ".join(event.get("categories") or []),
        " ".join(event.get("extracted_keywords") or []),
    ]
    if intermediate:
        parts.extend(
            [
                intermediate.get("inquiry_raw"),
                intermediate.get("description_summary"),
                intermediate.get("category_raw"),
            ]
        )
    return " ".join(str(p) for p in parts if p)


def detect_sales_signals(
    event: dict[str, Any],
    *,
    intermediate: dict[str, Any] | None = None,
) -> tuple[list[str], list[str]]:
    """Return (sales_signal_types, sales_signal_basis) from concrete fields/text only.

    Never awards signals from event_type alone.
    Never auto-adds ORGANIZER_OUTREACH for every row.
    """
    signals: list[str] = []
    basis: list[str] = []

    if event.get("registration_url"):
        signals.append("REGISTRATION")
        basis.append("registration_url")
    if event.get("exhibitor_recruitment_url"):
        signals.append("EXHIBITOR_LEAD")
        basis.append("exhibitor_recruitment_url")
    if event.get("buyer_recruitment_url"):
        signals.append("BUSINESS_MATCHING")
        basis.append("buyer_recruitment_url")
    if event.get("participant_recruitment_url"):
        signals.append("REGISTRATION")
        basis.append("participant_recruitment_url")

    if event.get("pco_organizations"):
        signals.append("PCO_PARTNERSHIP")
        basis.append("pco_name")
    if event.get("operator_organizations"):
        signals.append("ONSITE_OPERATION")
        basis.append("organizer_name")  # operator role evidence
        basis.append("operator_name")

    # Public business contact on the event record
    if event.get("contact_email"):
        signals.append("ORGANIZER_OUTREACH")
        basis.append("contact_email")
    if event.get("contact_phone"):
        signals.append("ORGANIZER_OUTREACH")
        basis.append("contact_phone")
    if event.get("contact_department") and not event.get("contact_email") and not event.get("contact_phone"):
        signals.append("ORGANIZER_OUTREACH")
        basis.append("contact_department")

    hay = _haystack(event, intermediate)
    if hay:
        if _PROCUREMENT_RE.search(hay):
            signals.append("ONSITE_OPERATION")
            basis.append("procurement_notice")
            if re.search(r"시스템|솔루션|등록\s*시스템|발권|체크인", hay, re.I):
                basis.append("system_operation_requirement")
        if _REG_RE.search(hay) and "registration_url" not in basis:
            # Text evidence of registration recruitment, not type inference
            signals.append("REGISTRATION")
            basis.append("registration_text")
        if _EXHIBITOR_RE.search(hay) and "exhibitor_recruitment_url" not in basis:
            signals.append("EXHIBITOR_LEAD")
            basis.append("exhibitor_recruitment_text")
        if _BUYER_RE.search(hay):
            signals.append("BUSINESS_MATCHING")
            basis.append("buyer_recruitment_text")
        if _MATCH_RE.search(hay):
            signals.append("BUSINESS_MATCHING")
            signals.append("MEETING_SCHEDULING")
            basis.append("business_matching_text")

    # Official event homepage alone is NOT a sales signal.
    # Host/operator names alone are not ORGANIZER_OUTREACH without contact or procurement.

    return uniq(signals), uniq(basis)


def _is_futureish(event: dict[str, Any], today: date) -> bool:
    status = event.get("event_status")
    if status == "ENDED":
        return False
    if status in {"UPCOMING", "ONGOING"}:
        return True
    start = event.get("start_date")
    end = event.get("end_date")
    try:
        if end and date.fromisoformat(end) >= today:
            return True
        if start and date.fromisoformat(start) >= today:
            return True
    except ValueError:
        pass
    # Unknown dates: treat as researchable only if not clearly past
    if not start and not end:
        return True
    return False


def _has_org(event: dict[str, Any]) -> bool:
    return bool(
        event.get("host_organizations")
        or event.get("organizer_organizations")
        or event.get("operator_organizations")
        or event.get("pco_organizations")
    )


def _has_public_contact(event: dict[str, Any]) -> bool:
    return bool(
        event.get("contact_email")
        or event.get("contact_phone")
        or event.get("contact_name")
        or event.get("contact_department")
    )


def _is_low_commercial_value(event: dict[str, Any]) -> bool:
    title = event.get("title") or ""
    if _LOW_VALUE_RE.search(title):
        return True
    return False


def _far_future(event: dict[str, Any], today: date, days: int = 365) -> bool:
    start = event.get("start_date")
    if not start:
        return False
    try:
        return date.fromisoformat(start) > today + timedelta(days=days)
    except ValueError:
        return False


def infer_sales_readiness(
    event: dict[str, Any],
    *,
    today: date,
    sales_signals: list[str],
    sales_basis: list[str],
) -> tuple[str, str]:
    """Return (sales_readiness, suggested_sales_action)."""
    status = event.get("event_status")
    future = _is_futureish(event, today)
    org = _has_org(event)
    contact = _has_public_contact(event)
    official = bool(event.get("official_event_url"))
    low = _is_low_commercial_value(event)

    if status == "ENDED" or (not future and status != "ONGOING"):
        return "NONE", "종료 행사 — 차기 회차·주최기관만 메모"
    if low and not contact and "procurement_notice" not in sales_basis:
        return "NONE", "내부·공연·교육성 행사로 영업 우선순위 낮음"

    if "procurement_notice" in sales_basis or "system_operation_requirement" in sales_basis:
        return "DIRECT_OPPORTUNITY", "입찰·용역·시스템 요구 원문 확인 후 제안 검토"

    # CONTACTABLE requires real public business contact — never homepage-only.
    if future and org and contact:
        return "CONTACTABLE", "공개 업무 연락처 기준 접촉 검토"

    if future and org and official and not contact:
        return "RESEARCH", "주최기관·공식 홈페이지 확인 — 담당/입찰 경로 추가 조사"
    if future and org and sales_basis and not contact:
        return "RESEARCH", "영업 단서는 있으나 공개 연락처 부족 — 추가 조사"
    if future and official and not org:
        return "WATCH", "공식 URL만 확인 — 주최·운영기관 확인 필요"
    if future and (not org) and (not official):
        return "WATCH", "기관·공식 URL 부족 — 일정만 모니터링"
    if future and event.get("needs_official_verification") and not start_known(event):
        return "WATCH", "일정 미확정 — 상세 확정 후 재검토"
    if future and _far_future(event, today) and not contact:
        return "WATCH", "일정이 상당히 남음 — 일정 근접 시 재검토"
    if future and org:
        return "RESEARCH", "주최기관 확인 — 공식 문의·입찰 경로 조사"
    return "NONE", "출처 정보 부족으로 즉시 행동 어려움"


def start_known(event: dict[str, Any]) -> bool:
    return bool(event.get("start_date"))


def apply_sales_layer(
    event: dict[str, Any],
    *,
    today: date,
    intermediate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mutate/return event with service matches, evidence signals, readiness."""
    event_type = event.get("event_type") or "OTHER"
    event["qrpick_service_matches"] = infer_qrpick_service_matches(event_type)
    signals, basis = detect_sales_signals(event, intermediate=intermediate)
    readiness, action = infer_sales_readiness(
        event, today=today, sales_signals=signals, sales_basis=basis
    )
    # Readiness evidence for CSV filtering — not the same as inventing REGISTRATION etc.
    if readiness in {"DIRECT_OPPORTUNITY", "CONTACTABLE", "RESEARCH", "WATCH"}:
        if event.get("host_organizations") or event.get("organizer_organizations"):
            basis.append("organizer_name")
        if event.get("operator_organizations"):
            basis.append("operator_name")
        if event.get("pco_organizations"):
            basis.append("pco_name")
        if event.get("official_event_url"):
            basis.append("official_inquiry_url")
    event["sales_signal_types"] = signals
    event["sales_signal_basis"] = uniq(basis)
    event["sales_readiness"] = readiness
    event["suggested_sales_action"] = action
    return event
