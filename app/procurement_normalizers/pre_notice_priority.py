"""Human-review priority and primary route selection for G2B pre-notices."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any


PRIORITY_ORDER = {
    "P0_DETAIL_REVIEW": 0,
    "P1_PARTNER_OUTREACH": 1,
    "P2_QUALIFICATION_RESEARCH": 2,
    "P3_WATCH": 3,
    "NO_ACTION": 4,
}

DIRECT_ROLE_TOKENS = (
    "참가자 등록",
    "참가등록",
    "사전등록",
    "현장등록",
    "체크인",
    "명찰",
    "배지",
    "비표",
    "발권",
    "행사 홈페이지",
    "홈페이지",
    "운영시스템",
    "플랫폼",
    "매칭",
    "참가자 DB",
    "참가자DB",
    "대시보드",
    "CRM",
    "다국어",
    "QR",
)

PARTNER_LEAD_TOKENS = (
    "행사 운영",
    "행사운영",
    "운영 대행",
    "운영대행",
    "행사 대행",
    "기획",
    "연출",
    "무대",
    "공연",
    "축제",
    "페스티벌",
    "페스타",
    "개막식",
    "시상식",
    "홍보관",
    "전시장",
    "현장 운영",
)

PARTNER_ROUTES = ("CONSORTIUM_BID", "SUBCONTRACT_OR_SOLUTION_PARTNER")
ALLOWED_PRIORITIES = frozenset(PRIORITY_ORDER)


def _text(rec: dict[str, Any]) -> str:
    return " ".join(
        str(rec.get(key) or "")
        for key in ("title", "title_normalized", "mice_relevance_evidence")
    )


def _hits(text: str, tokens: tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(token for token in tokens if token in text))


def _money(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    raw = str(value).replace(",", "").replace("원", "").strip()
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    return amount if amount > 0 else None


def _day(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _route_selection(
    rec: dict[str, Any],
    *,
    direct_hits: list[str],
    partner_hits: list[str],
) -> tuple[str | None, list[str], list[str]]:
    routes = list(dict.fromkeys(str(route) for route in (rec.get("opportunity_routes") or []) if route))
    direct_available = "DIRECT_PRIME_BID" in routes and bool(direct_hits)
    partner_available = any(route in routes for route in PARTNER_ROUTES)
    reasons: list[str] = []

    if direct_available:
        primary = "DIRECT_PRIME_BID"
        reasons.append("DIRECT_ROLE_EXPLICIT:" + ",".join(direct_hits[:5]))
    elif partner_available and partner_hits:
        primary = (
            "CONSORTIUM_BID"
            if "CONSORTIUM_BID" in routes
            else "SUBCONTRACT_OR_SOLUTION_PARTNER"
        )
        reasons.append("FULL_EVENT_DELIVERY_PARTNER_LED:" + ",".join(partner_hits[:5]))
    elif partner_available:
        primary = next(route for route in PARTNER_ROUTES if route in routes)
        reasons.append("PARTNER_ROUTE_AVAILABLE_WITHOUT_DIRECT_SCOPE")
    elif "DIRECT_PRIME_BID" in routes:
        primary = "DIRECT_PRIME_BID"
        reasons.append("DIRECT_ROUTE_REQUIRES_SCOPE_CONFIRMATION")
    else:
        primary = routes[0] if routes else None
        reasons.append("NO_EXECUTABLE_ROUTE" if not routes else "FALLBACK_EXISTING_ROUTE")

    secondary = [route for route in routes if route != primary]
    if direct_available and partner_available:
        reasons.append("DIRECT_AND_PARTNER_ROUTES_PRESERVED")
    return primary, secondary, reasons


def _blocking_unknowns(rec: dict[str, Any], today: date) -> list[str]:
    blockers = list(rec.get("blocking_unknowns") or [])
    if str(rec.get("detail_verification_status") or "").upper() != "VERIFIED":
        blockers.append("DETAIL_NOT_VERIFIED")
    if not rec.get("attachment_urls"):
        blockers.append("ATTACHMENTS_NOT_REVIEWED")
    if _money(rec.get("estimated_amount")) is None:
        blockers.append("BUDGET_UNKNOWN")
    if not rec.get("proposal_deadline"):
        blockers.append("FORMAL_NOTICE_DEADLINE_UNKNOWN")
    if not rec.get("mandatory_qualification_requirements"):
        blockers.append("QUALIFICATION_REQUIREMENTS_UNKNOWN")
    published = _day(rec.get("announcement_date"))
    if published is None:
        blockers.append("PRE_NOTICE_PUBLICATION_DATE_UNKNOWN")
    elif published > today:
        blockers.append("PUBLICATION_DATE_IN_FUTURE")
    return list(dict.fromkeys(blockers))


def _review_deadline(priority: str, today: date) -> str | None:
    offsets = {
        "P0_DETAIL_REVIEW": 2,
        "P1_PARTNER_OUTREACH": 5,
        "P2_QUALIFICATION_RESEARCH": 10,
        "P3_WATCH": 21,
    }
    days = offsets.get(priority)
    return (today + timedelta(days=days)).isoformat() if days is not None else None


def assess_pre_notice_priority(
    rec: dict[str, Any],
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Assign deterministic review priority without deleting any candidate."""
    today = today or date.today()
    out = dict(rec)
    text = _text(out)
    routes = list(out.get("opportunity_routes") or [])
    direct_hits = _hits(text, DIRECT_ROLE_TOKENS)
    partner_hits = _hits(text, PARTNER_LEAD_TOKENS)
    primary, secondary, route_reasons = _route_selection(
        out,
        direct_hits=direct_hits,
        partner_hits=partner_hits,
    )

    published = _day(out.get("announcement_date"))
    age_days = (today - published).days if published else None
    recent = age_days is not None and 0 <= age_days <= 45
    budget_known = _money(out.get("estimated_amount")) is not None
    strong_mice = out.get("mice_relevance_confidence") == "STRONG"
    direct_available = "DIRECT_PRIME_BID" in routes and bool(direct_hits)
    partner_available = any(route in routes for route in PARTNER_ROUTES)
    role_evidence = bool(direct_hits or partner_hits)
    blockers = _blocking_unknowns(out, today)
    reasons = list(route_reasons)

    if out.get("procurement_stage") != "PRE_NOTICE" or not out.get("mice_relevant"):
        priority = "NO_ACTION"
        reasons.append("NOT_MICE_RELEVANT_PRE_NOTICE")
    elif not role_evidence or not routes:
        priority = "P3_WATCH"
        reasons.append("INSUFFICIENT_ROLE_OR_ROUTE_EVIDENCE")
    else:
        p0_support = sum((budget_known, recent, strong_mice))
        if direct_available and len(direct_hits) >= 1 and p0_support >= 2:
            priority = "P0_DETAIL_REVIEW"
            reasons.append("DIRECT_SCOPE_WITH_SCALE_OR_RECENCY")
        elif partner_available and partner_hits and p0_support >= 2:
            priority = "P1_PARTNER_OUTREACH"
            reasons.append("PARTNER_LED_EVENT_DELIVERY_WITH_TIMING_OR_SCALE")
        elif direct_available or partner_available:
            priority = "P2_QUALIFICATION_RESEARCH"
            reasons.append("MICE_ROUTE_REQUIRES_QUALIFICATION_RESEARCH")
        else:
            priority = "P3_WATCH"
            reasons.append("MICE_RELEVANT_BUT_INFORMATION_THIN")

    if priority == "P0_DETAIL_REVIEW":
        action = "상세·첨부를 우선 확인하고 직접 수행범위·예산·자격을 본공고 전에 검토"
    elif priority == "P1_PARTNER_OUTREACH":
        action = "기획사·PCO 후보를 선별해 역할 구성·견적 초안을 준비하고 선제 접촉"
    elif priority == "P2_QUALIFICATION_RESEARCH":
        action = "첨부·자격·예산·일정을 조사하고 직접/파트너 경로를 재판정"
    elif priority == "P3_WATCH":
        action = "본공고 게시와 과업 구체화를 추적하고 반복사업 여부를 확인"
    else:
        action = "영업 대기열 제외; 조달 원본만 보존"

    if priority == "NO_ACTION":
        # Preserve route candidates for audit, but do not present an executable primary route.
        secondary = list(dict.fromkeys(routes))
        primary = None
        reasons.append("PRIMARY_ROUTE_SUPPRESSED_FOR_NO_ACTION")

    out.update(
        {
            "pre_notice_priority": priority,
            "primary_opportunity_route": primary,
            "secondary_opportunity_routes": secondary,
            "route_selection_reasons": list(dict.fromkeys(reasons)),
            "review_deadline": _review_deadline(priority, today),
            "review_blocking_unknowns": blockers,
            "recommended_review_action": action,
            "priority_role_scope": list(dict.fromkeys(direct_hits + partner_hits)),
            "direct_bid_evidence": direct_hits,
            "partner_participation_evidence": partner_hits,
            "contact_path_verified": bool(
                out.get("public_contact_phone") or out.get("public_contact_email")
            ),
            "pre_notice_priority_signals": {
                "direct_role_evidence": direct_hits,
                "partner_role_evidence": partner_hits,
                "budget_known": budget_known,
                "publication_recent_45d": recent,
                "publication_age_days": age_days,
                "strong_mice_confidence": strong_mice,
            },
        }
    )
    return out


def priority_sort_key(rec: dict[str, Any]) -> tuple[Any, ...]:
    """Operator order: priority, recency, confidence, direct evidence, budget, contact."""
    published = _day(rec.get("announcement_date"))
    published_ordinal = published.toordinal() if published else 0
    confidence_order = {"STRONG": 0, "MEDIUM": 1, "WEAK": 2, "NONE": 3}
    direct_evidence = rec.get("direct_bid_evidence") or []
    budget_known = _money(rec.get("estimated_amount")) is not None
    contact_verified = bool(
        rec.get("contact_path_verified")
        or rec.get("public_contact_phone")
        or rec.get("public_contact_email")
    )
    return (
        PRIORITY_ORDER.get(str(rec.get("pre_notice_priority")), 99),
        -published_ordinal,
        confidence_order.get(str(rec.get("mice_relevance_confidence") or "NONE"), 4),
        -len(direct_evidence),
        -int(budget_known),
        -int(contact_verified),
        str(rec.get("title") or ""),
    )
