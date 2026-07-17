"""Lightweight final-stage adapters and common ranking for product-wide opportunities."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


PRIORITY_ORDER = {
    "P0_IMMEDIATE": 0,
    "P1_THIS_WEEK": 1,
    "P2_REVIEW": 2,
    "P3_WATCH": 3,
    "NO_ACTION": 4,
}

DOMAIN_ORDER = {
    "SUPPORT_PROGRAM": 0,
    "MICE_EVENT": 1,
    "PRE_NOTICE": 2,
    "BID_NOTICE": 3,
    "AWARD_WINNER_OUTREACH": 4,
    "CONTRACT_RECURRING": 5,
}

EXECUTABLE_ROUTES = {
    "DIRECT_PRIME_BID",
    "CONSORTIUM_BID",
    "SUBCONTRACT_OR_SOLUTION_PARTNER",
    "AWARD_WINNER_SALES",
    "QRPICK_DIRECT",
    "QRPICK_EXTENSION",
    "SHOWDA_ASSET_REUSE",
    "CUSTOM_BUILD_SERVICE",
    "PARTNER_CONSORTIUM",
    "SALES_LEAD",
    "DIRECT_SERVICE_PROPOSAL",
    "ORGANIZER_OUTREACH",
    "NEXT_CYCLE_SALES",
}

NO_PATH_VALUES = {
    "",
    "NO_REALISTIC_PATH",
    "NO_REALISTIC_DIRECT_BID_PATH",
    "NONE",
    "NO_ACTION",
}


def _list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def _unique(values: Iterable[Any]) -> list[Any]:
    out: list[Any] = []
    seen: set[str] = set()
    for value in values:
        if value in (None, "", []):
            continue
        marker = str(value)
        if marker not in seen:
            seen.add(marker)
            out.append(value)
    return out


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    raw = str(value).strip()
    for candidate in (raw[:10], raw[:8]):
        try:
            if len(candidate) == 8 and candidate.isdigit():
                return datetime.strptime(candidate, "%Y%m%d").date()
            return date.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def _amount(record: dict[str, Any]) -> Decimal | None:
    for key in (
        "estimated_amount",
        "contract_amount",
        "base_amount",
        "support_amount",
        "budget",
        "estimated_price",
    ):
        value = record.get(key)
        if value in (None, ""):
            continue
        raw = re.sub(r"[^0-9.\-]", "", str(value))
        try:
            amount = Decimal(raw)
        except (InvalidOperation, ValueError):
            continue
        if amount > 0:
            return amount
    return None


def _urls(record: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in (
        "url",
        "detail_url",
        "source_url",
        "official_event_url",
        "contact_source_url",
        "registration_url",
        "recruitment_url",
        "application_url",
        "attachment_urls",
        "request_for_proposal_urls",
    ):
        values.extend(_list(record.get(key)))
    return [str(value) for value in _unique(values) if str(value).startswith(("http://", "https://"))]


def _source_ids(record: dict[str, Any], domain_type: str) -> list[str]:
    values: list[str] = []
    for key in (
        "canonical_id",
        "opportunity_id",
        "canonical_event_id",
        "event_id",
        "procurement_id",
        "lifecycle_group_id",
        "notice_number",
        "source_id",
    ):
        if record.get(key):
            values.append(f"{key}:{record[key]}")
    for occurrence in _list(record.get("source_occurrences")):
        if isinstance(occurrence, dict):
            source = occurrence.get("source") or occurrence.get("source_id")
            source_id = occurrence.get("source_id") or occurrence.get("id")
            if source or source_id:
                values.append(f"occurrence:{source or ''}:{source_id or ''}")
    return [f"{domain_type}:{value}" for value in _unique(values)]


def _organization(record: dict[str, Any], domain_type: str) -> str:
    if domain_type == "SUPPORT_PROGRAM":
        return str(record.get("organization") or "")
    if domain_type == "MICE_EVENT":
        for key in (
            "organizer_organizations",
            "host_organizations",
            "operator_organizations",
            "pco_organizations",
        ):
            values = _list(record.get(key))
            if values:
                return " | ".join(str(value) for value in values)
        return ""
    if domain_type == "AWARD_WINNER_OUTREACH":
        values = _list(record.get("awardee_organizations"))
        if values:
            return " | ".join(str(value) for value in values)
    return str(record.get("ordering_organization") or record.get("demand_organization") or "")


def _domain_type(record: dict[str, Any], source_domain: str) -> str:
    if source_domain == "support":
        return "SUPPORT_PROGRAM"
    if source_domain == "mice":
        return "MICE_EVENT"
    stage = str(record.get("procurement_stage") or "").upper()
    return {
        "PRE_NOTICE": "PRE_NOTICE",
        "BID_NOTICE": "BID_NOTICE",
        "AWARD_RESULT": "AWARD_WINNER_OUTREACH",
        "CONTRACT_RESULT": "CONTRACT_RECURRING",
    }.get(stage, "CONTRACT_RECURRING")


def _routes(record: dict[str, Any], domain_type: str) -> tuple[str, list[str]]:
    routes = [str(value) for value in _list(record.get("opportunity_routes")) if value]
    primary = str(
        record.get("primary_opportunity_route")
        or record.get("primary_route")
        or record.get("primary_asset_fit_path")
        or ""
    )
    routes.extend(str(value) for value in _list(record.get("secondary_opportunity_routes")))
    routes.extend(str(value) for value in _list(record.get("secondary_asset_fit_paths")))

    if domain_type == "MICE_EVENT" and not primary:
        readiness = str(record.get("sales_readiness") or "")
        primary = {
            "DIRECT_OPPORTUNITY": "DIRECT_SERVICE_PROPOSAL",
            "CONTACTABLE": "ORGANIZER_OUTREACH",
            "RESEARCH": "QUALIFICATION_RESEARCH",
            "WATCH": "WATCH",
        }.get(readiness, "")
    if domain_type == "AWARD_WINNER_OUTREACH" and "AWARD_WINNER_WINDOW" in _list(
        record.get("sales_windows")
    ):
        primary = "AWARD_WINNER_SALES"
    if domain_type == "CONTRACT_RECURRING" and "NEXT_CYCLE_WINDOW" in _list(
        record.get("sales_windows")
    ):
        primary = "NEXT_CYCLE_SALES"

    routes = [str(value) for value in _unique([primary, *routes]) if str(value) not in NO_PATH_VALUES]
    primary = primary if primary and primary not in NO_PATH_VALUES else (routes[0] if routes else "")
    return primary, [route for route in routes if route != primary]


def _evidence(record: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in (
        "fit_evidence",
        "positive_reasons",
        "review_reasons",
        "sales_signal_basis",
        "sales_signal_types",
        "mice_relevance_evidence",
        "eligibility_evidence",
        "bid_assessment_basis",
        "route_selection_reasons",
        "direct_bid_evidence",
        "partner_participation_evidence",
    ):
        values.extend(_list(record.get(key)))
    return [str(value) for value in _unique(values)]


def _blocking_unknowns(record: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in (
        "blocking_unknowns",
        "bid_blocking_reasons",
        "review_blocking_unknowns",
        "actionability_gate_reasons",
    ):
        values.extend(_list(record.get(key)))
    if str(record.get("detail_verification_status") or "").upper() not in {"VERIFIED", ""}:
        values.append("DETAIL_NOT_VERIFIED")
    if record.get("needs_official_verification"):
        values.append("OFFICIAL_SOURCE_VERIFICATION_REQUIRED")
    return [str(value) for value in _unique(values)]


def _expected_role(record: dict[str, Any], primary_route: str) -> list[str]:
    values: list[Any] = []
    for key in (
        "priority_role_scope",
        "usable_qrpick_features",
        "qrpick_service_matches",
        "matched_asset_families",
        "direct_bid_evidence",
        "partner_participation_evidence",
        "qrpick_showda_delivery_scope",
    ):
        values.extend(_list(record.get(key)))
    if not values:
        values.append("상세 과업에서 QRPick·쇼다 역할 확인 필요")
    return [str(value) for value in _unique(values)]


def _posted_and_deadline(record: dict[str, Any], domain_type: str) -> tuple[str | None, str | None]:
    if domain_type == "SUPPORT_PROGRAM":
        return record.get("posted_at"), record.get("deadline")
    if domain_type == "MICE_EVENT":
        return record.get("posted_at") or record.get("collected_at"), record.get("start_date")
    if domain_type == "AWARD_WINNER_OUTREACH":
        return record.get("award_date") or record.get("announcement_date"), record.get("event_date")
    if domain_type == "CONTRACT_RECURRING":
        return record.get("contract_date") or record.get("announcement_date"), record.get("event_date")
    return record.get("announcement_date"), record.get("proposal_deadline")


def _action(record: dict[str, Any], domain_type: str, primary_route: str) -> str:
    if domain_type == "AWARD_WINNER_OUTREACH":
        existing = str(record.get("recommended_next_action") or "")
        if "낙찰" in existing:
            return existing
        return "낙찰사 공개 연락경로와 시스템 공급사 상태를 확인 후 QRPick 역할을 제안"
    if domain_type == "CONTRACT_RECURRING":
        return "계약·전년도 사업 근거로 차기 회차 일정과 발주기관을 추적"
    for key in (
        "recommended_review_action",
        "recommended_next_action",
        "recommended_bid_action",
        "suggested_sales_action",
    ):
        if record.get(key):
            return str(record[key])
    defaults = {
        "SUPPORT_PROGRAM": "상세 공고에서 자격·지원범위·QRPick 활용 과제를 확인",
        "MICE_EVENT": "공식 주최·문의 경로를 확인하고 QRPick 적용 역할을 검토",
        "PRE_NOTICE": "상세·첨부와 본공고 일정을 확인해 주·보조 경로를 재검토",
        "BID_NOTICE": "첨부·자격·마감·수행범위를 확인하고 입찰 또는 파트너 경로를 결정",
        "AWARD_WINNER_OUTREACH": "낙찰사 공개 연락경로와 시스템 공급사 상태를 확인 후 제안",
        "CONTRACT_RECURRING": "계약·전년도 사업 근거로 차기 회차 일정과 발주기관을 추적",
    }
    return defaults.get(domain_type, f"{primary_route or '기회'} 상세 확인")


def _deadline_days(deadline: Any, today: date) -> int | None:
    parsed = _parse_date(deadline)
    return (parsed - today).days if parsed else None


def _urgency_score(record: dict[str, Any], domain_type: str, deadline: Any, today: date) -> int:
    days = _deadline_days(deadline, today)
    windows = set(str(value) for value in _list(record.get("sales_windows")))
    action_queue = str(record.get("action_queue") or "")
    readiness = str(record.get("sales_readiness") or "")

    if days is not None and days < 0:
        return 0
    if windows & {"DIRECT_BID_WINDOW", "AWARD_WINNER_WINDOW"}:
        if days is not None and days <= 14:
            return 100
        return 80
    if days is not None:
        if days <= 2:
            return 100
        if days <= 7:
            return 90
        if days <= 14:
            return 80
        if days <= 45:
            return 65
        if days <= 120:
            return 45
        return 25
    if windows & {
        "PRE_NOTICE_DIRECT_REVIEW",
        "PRE_NOTICE_PARTNER_OUTREACH",
        "PRE_REGISTRATION_WINDOW",
        "BID_PARTNER_WINDOW",
    }:
        return 60
    if action_queue in {"ACTION_NOW", "QUALIFICATION_CHECK"}:
        return 60
    if action_queue == "SALES_OUTREACH" or readiness in {"DIRECT_OPPORTUNITY", "CONTACTABLE"}:
        return 55
    if domain_type in {"PRE_NOTICE", "CONTRACT_RECURRING"}:
        return 35
    return 20


def _business_fit_score(
    record: dict[str, Any],
    domain_type: str,
    primary_route: str,
    secondary_routes: list[str],
    evidence: list[str],
) -> int:
    routes = {primary_route, *secondary_routes} - {""}
    direct_evidence = _list(record.get("direct_bid_evidence"))
    explicit_features = _unique(
        [
            *_list(record.get("priority_role_scope")),
            *_list(record.get("usable_qrpick_features")),
            *_list(record.get("qrpick_service_matches")),
            *_list(record.get("matched_asset_families")),
            *_list(record.get("qrpick_showda_delivery_scope")),
            *direct_evidence,
        ]
    )
    sales_signals = _list(record.get("sales_signal_types"))
    evidence_text = " ".join(str(value) for value in evidence)

    if "DIRECT_PRIME_BID" in routes and (direct_evidence or explicit_features):
        return 100
    if domain_type == "SUPPORT_PROGRAM":
        if (
            routes & {"QRPICK_DIRECT", "SHOWDA_ASSET_REUSE", "CUSTOM_BUILD_SERVICE"}
            and explicit_features
        ):
            return 80
        if routes & {"SALES_LEAD", "PARTNER_CONSORTIUM", "QRPICK_EXTENSION"} and any(
            token in evidence_text
            for token in ("MICE", "행사", "전시", "박람", "상담회", "등록", "매칭", "관광")
        ):
            return 65
        return 35 if evidence else 0
    if domain_type == "MICE_EVENT":
        if sales_signals and explicit_features:
            return 80
        if sales_signals:
            return 65
        return 35 if explicit_features else 0
    if routes & {
        "CONSORTIUM_BID",
        "SUBCONTRACT_OR_SOLUTION_PARTNER",
        "AWARD_WINNER_SALES",
        "NEXT_CYCLE_SALES",
    } and (explicit_features or evidence):
        return 80
    if explicit_features or evidence:
        return 50
    if routes:
        return 25
    return 0


def _revenue_score(record: dict[str, Any]) -> int:
    amount = _amount(record)
    if amount is not None:
        if amount >= Decimal("100000000"):
            return 100
        if amount >= Decimal("50000000"):
            return 75
        return 50
    if any(
        record.get(key)
        for key in ("expected_participants", "expected_exhibitors", "expected_booths")
    ):
        return 25
    return 0


def _contactability_score(record: dict[str, Any], organization: str, urls: list[str]) -> int:
    email = record.get("public_contact_email") or record.get("contact_email")
    phone = record.get("public_contact_phone") or record.get("contact_phone")
    source = record.get("contact_source_url")
    confidence = str(record.get("contact_confidence") or "").upper()
    if (email or phone) and source and confidence in {"HIGH", "VERIFIED", "STRONG"}:
        return 100
    if email or phone:
        return 75
    if (
        record.get("public_contact_name")
        or record.get("contact_name")
        or record.get("public_contact_department")
        or record.get("contact_department")
    ):
        return 50
    if organization and urls:
        return 25
    return 0


def _completeness_score(
    source_ids: list[str],
    title: str,
    organization: str,
    posted_at: Any,
    deadline: Any,
    urls: list[str],
    routes: list[str],
    evidence: list[str],
    blockers: list[str],
    detail_verification_status: Any,
) -> int:
    groups = (
        bool(source_ids),
        bool(title),
        bool(organization),
        bool(posted_at or deadline),
        bool(urls),
        bool(routes or evidence),
    )
    count = sum(groups)
    score = {6: 100, 5: 75, 4: 50, 3: 50, 2: 25, 1: 25, 0: 0}[count]
    verification = str(detail_verification_status or "").upper()
    if verification and verification != "VERIFIED":
        score -= 25
    if len(blockers) >= 5:
        score -= 25
    elif blockers:
        score -= 10
    return max(0, score)


def _deadline_risk_score(deadline: Any, domain_type: str, today: date) -> int:
    days = _deadline_days(deadline, today)
    if days is None:
        return 25 if domain_type == "PRE_NOTICE" else 0
    if days < 0 or days <= 2:
        return 100
    if days <= 7:
        return 75
    if days <= 14:
        return 50
    if days <= 30:
        return 25
    return 0


def _recency_score(posted_at: Any, today: date) -> int:
    posted = _parse_date(posted_at)
    if not posted:
        return 0
    age = (today - posted).days
    if age < 0:
        return 0
    if age <= 7:
        return 100
    if age <= 30:
        return 75
    if age <= 90:
        return 50
    if age <= 365:
        return 25
    return 0


def _strict_p0_gate(
    record: dict[str, Any],
    routes: list[str],
    blockers: list[str],
    deadline: Any,
    contactability_score: int,
    today: date,
) -> bool:
    checklist = record.get("bid_gate_checklist") or {}
    required_gates_clear = bool(checklist) and all(bool(value) for value in checklist.values())
    attachments = _list(record.get("attachment_urls")) + _list(
        record.get("request_for_proposal_urls")
    )
    days = _deadline_days(deadline, today)
    return all(
        (
            str(record.get("detail_verification_status") or "").upper() == "VERIFIED",
            str(record.get("eligibility_status") or "").upper() == "VERIFIED_ELIGIBLE",
            record.get("actionability_verified") is True,
            bool(attachments),
            required_gates_clear,
            not blockers,
            str(record.get("bid_go_no_go") or "").upper() == "GO",
            str(record.get("bid_participation_readiness") or "").upper() == "ACTION_NOW",
            days is not None and days >= 0,
            bool(set(routes) & EXECUTABLE_ROUTES),
            contactability_score >= 50,
        )
    )


def _native_no_action(record: dict[str, Any], domain_type: str, deadline: Any, today: date) -> bool:
    if _deadline_days(deadline, today) is not None and _deadline_days(deadline, today) < 0:
        if domain_type not in {"AWARD_WINNER_OUTREACH", "CONTRACT_RECURRING"}:
            return True
    if domain_type == "SUPPORT_PROGRAM":
        return str(record.get("action_queue") or "") in {"NO_ACTION", "CLOSED"} or str(
            record.get("first_pass_status") or ""
        ) in {"LOW_FIT", "EXPIRED"}
    if domain_type == "MICE_EVENT":
        return str(record.get("sales_readiness") or "") == "NONE" or str(
            record.get("event_status") or ""
        ) == "ENDED"
    if domain_type == "PRE_NOTICE":
        return not bool(record.get("sales_queue_eligible")) or str(
            record.get("pre_notice_priority") or ""
        ) == "NO_ACTION"
    if domain_type == "BID_NOTICE":
        return not bool(record.get("mice_relevant")) or not bool(
            record.get("bid_assessment_applicable")
        )
    if domain_type == "AWARD_WINNER_OUTREACH":
        return not (
            record.get("mice_relevant")
            and "AWARD_WINNER_WINDOW" in _list(record.get("sales_windows"))
            and _list(record.get("awardee_organizations"))
        )
    if domain_type == "CONTRACT_RECURRING":
        return not (
            "NEXT_CYCLE_WINDOW" in _list(record.get("sales_windows"))
            and str(record.get("previous_cycle_confidence") or "") in {"STRONG", "MEDIUM"}
        )
    return True


def _dedupe_key(record: dict[str, Any], domain_type: str) -> str:
    if domain_type == "SUPPORT_PROGRAM":
        identity = (
            record.get("canonical_id")
            or record.get("opportunity_id")
            or f"{record.get('source')}:{record.get('source_id')}"
        )
        return f"support:{identity}"
    if domain_type == "MICE_EVENT":
        identity = record.get("canonical_event_id") or record.get("event_id")
        return f"mice:{identity}"
    lifecycle = record.get("lifecycle_group_id")
    if lifecycle and domain_type != "PRE_NOTICE":
        return f"procurement-lifecycle:{lifecycle}"
    identity = record.get("procurement_id") or (
        f"{record.get('notice_number')}:{record.get('notice_revision') or ''}"
    )
    return f"procurement:{identity}"


def adapt_record(
    record: dict[str, Any],
    *,
    source_domain: str,
    today: date,
) -> dict[str, Any]:
    """Adapt one domain record and compute common scores from facts, not native scores."""
    domain_type = _domain_type(record, source_domain)
    title = str(record.get("title") or "")
    organization = _organization(record, domain_type)
    primary_route, secondary_routes = _routes(record, domain_type)
    evidence = _evidence(record)
    role = _expected_role(record, primary_route)
    blockers = _blocking_unknowns(record)
    posted_at, deadline = _posted_and_deadline(record, domain_type)
    urls = _urls(record)
    source_ids = _source_ids(record, domain_type)
    routes = [value for value in [primary_route, *secondary_routes] if value]

    urgency = _urgency_score(record, domain_type, deadline, today)
    business_fit = _business_fit_score(
        record,
        domain_type,
        primary_route,
        secondary_routes,
        evidence,
    )
    revenue = _revenue_score(record)
    contactability = _contactability_score(record, organization, urls)
    completeness = _completeness_score(
        source_ids,
        title,
        organization,
        posted_at,
        deadline,
        urls,
        routes,
        evidence,
        blockers,
        record.get("detail_verification_status"),
    )
    deadline_risk = _deadline_risk_score(deadline, domain_type, today)
    recency = _recency_score(posted_at, today)
    unified_score = round(
        urgency * 0.20
        + business_fit * 0.25
        + revenue * 0.15
        + contactability * 0.10
        + completeness * 0.15
        + recency * 0.10
        + (100 - deadline_risk) * 0.05,
        2,
    )

    native_no_action = _native_no_action(record, domain_type, deadline, today)
    p0 = _strict_p0_gate(record, routes, blockers, deadline, contactability, today)
    if native_no_action or not title:
        band = "NO_ACTION"
    elif p0:
        band = "P0_IMMEDIATE"
    elif unified_score >= 65 and urgency >= 50 and business_fit >= 50:
        band = "P1_THIS_WEEK"
    elif unified_score >= 45 and business_fit >= 50:
        band = "P2_REVIEW"
    else:
        band = "P3_WATCH"

    dedupe_key = _dedupe_key(record, domain_type)
    unified_id = "uop:" + hashlib.sha1(dedupe_key.encode("utf-8")).hexdigest()[:20]
    return {
        "unified_opportunity_id": unified_id,
        "domain_type": domain_type,
        "source_record_ids": source_ids,
        "title": title,
        "organization": organization,
        "opportunity_stage": str(
            record.get("procurement_stage")
            or record.get("event_status")
            or record.get("first_pass_status")
            or domain_type
        ),
        "primary_opportunity_route": primary_route,
        "secondary_opportunity_routes": secondary_routes,
        "priority_band": band,
        "urgency_score": urgency,
        "business_fit_score": business_fit,
        "revenue_potential_score": revenue,
        "contactability_score": contactability,
        "information_completeness_score": completeness,
        "deadline_risk_score": deadline_risk,
        "unified_priority_score": unified_score,
        "relevance_reasons": evidence,
        "expected_qrpick_role": role,
        "recommended_next_action": _action(record, domain_type, primary_route),
        "blocking_unknowns": blockers,
        "posted_at": str(posted_at) if posted_at else None,
        "deadline": str(deadline) if deadline else None,
        "source_urls": urls,
        "_dedupe_key": dedupe_key,
        "_recency_score": recency,
        "_strict_p0_gate": p0,
    }


def unified_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    deadline = _parse_date(record.get("deadline"))
    posted = _parse_date(record.get("posted_at"))
    return (
        PRIORITY_ORDER.get(str(record.get("priority_band")), 99),
        -float(record.get("unified_priority_score") or 0),
        -int(record.get("urgency_score") or 0),
        -int(record.get("business_fit_score") or 0),
        -int(record.get("revenue_potential_score") or 0),
        -int(record.get("contactability_score") or 0),
        -int(record.get("information_completeness_score") or 0),
        int(record.get("deadline_risk_score") or 0),
        -int(record.get("_recency_score") or 0),
        deadline.toordinal() if deadline else 9999999,
        -(posted.toordinal() if posted else 0),
        DOMAIN_ORDER.get(str(record.get("domain_type")), 99),
        str(record.get("unified_opportunity_id") or ""),
    )


def merge_unified_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Merge only strong canonical/lifecycle identities and preserve every source reference."""
    merged: dict[str, dict[str, Any]] = {}
    duplicate_count = 0
    for record in sorted(records, key=unified_sort_key):
        key = str(record.get("_dedupe_key") or record.get("unified_opportunity_id"))
        if key not in merged:
            merged[key] = dict(record)
            continue
        duplicate_count += 1
        current = merged[key]
        current["source_record_ids"] = _unique(
            _list(current.get("source_record_ids")) + _list(record.get("source_record_ids"))
        )
        current["source_urls"] = _unique(
            _list(current.get("source_urls")) + _list(record.get("source_urls"))
        )
        current["relevance_reasons"] = _unique(
            _list(current.get("relevance_reasons")) + _list(record.get("relevance_reasons"))
        )
        current["blocking_unknowns"] = _unique(
            _list(current.get("blocking_unknowns")) + _list(record.get("blocking_unknowns"))
        )
        current["expected_qrpick_role"] = _unique(
            _list(current.get("expected_qrpick_role"))
            + _list(record.get("expected_qrpick_role"))
        )
        routes = _unique(
            [
                current.get("primary_opportunity_route"),
                *_list(current.get("secondary_opportunity_routes")),
                record.get("primary_opportunity_route"),
                *_list(record.get("secondary_opportunity_routes")),
            ]
        )
        primary = current.get("primary_opportunity_route") or (routes[0] if routes else "")
        current["primary_opportunity_route"] = primary
        current["secondary_opportunity_routes"] = [route for route in routes if route != primary]
    return sorted(merged.values(), key=unified_sort_key), duplicate_count


def public_record(record: dict[str, Any]) -> dict[str, Any]:
    """Remove internal ranking helpers from persisted output."""
    return {key: value for key, value in record.items() if not key.startswith("_")}
