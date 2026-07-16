"""Showda · QRPick direct / consortium / partner bid assessment.

Conservative list-stage rules:
- Never set VERIFIED_ELIGIBLE or GO without attachment/detail verification.
- Never exclude DIRECT routes solely because an industry name appears in the title.
- Multiple opportunity_routes may apply independently.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.evaluators.scoring import _find_hits
from app.normalizers.text_utils import haystack


OPPORTUNITY_ROUTES = (
    "DIRECT_PRIME_BID",
    "CONSORTIUM_BID",
    "SUBCONTRACT_OR_SOLUTION_PARTNER",
    "AWARD_WINNER_SALES",
)

DIRECT_BID_FIT_PATHS = (
    "QRPICK_STANDARD_SERVICE",
    "QRPICK_PLUS_OPERATION",
    "SHOWDA_CUSTOM_BUILD",
    "SHOWDA_PLATFORM_AND_DATA",
    "CONSORTIUM_REQUIRED",
    "PARTNER_SPECIALIST_REQUIRED",
    "NO_REALISTIC_DIRECT_BID_PATH",
)

BID_ROLES = (
    "PRIME",
    "JOINT_CONTRACTOR",
    "CONSORTIUM_MEMBER",
    "SUBCONTRACTOR",
    "SOLUTION_SUPPLIER",
    "NONE",
)

ELIGIBILITY_STATUSES = (
    "VERIFIED_ELIGIBLE",
    "LIKELY_ELIGIBLE",
    "UNKNOWN_NEEDS_DOCUMENT_REVIEW",
    "PARTIALLY_ELIGIBLE",
    "NOT_ELIGIBLE",
)

BID_READINESS = (
    "ACTION_NOW",
    "QUALIFICATION_CHECK",
    "PARTNER_SEARCH",
    "WATCH",
    "NO_BID",
)

BID_GO_NO_GO = (
    "GO",
    "CONDITIONAL_GO",
    "HOLD",
    "NO_GO",
    "UNKNOWN",
)

SALES_WINDOWS = (
    "DIRECT_BID_WINDOW",
    "CONSORTIUM_PARTNER_WINDOW",
)

ACTION_NOW_GATES = (
    "announcement_and_proposal_deadline",
    "mandatory_bid_qualifications",
    "regional_or_sme_restrictions",
    "performance_requirements",
    "joint_contract_allowed_known",
    "qrpick_showda_role_scope",
    "delivery_period",
    "budget_or_estimated_amount",
    "internal_delivery_capacity",
)


def empty_bid_fields() -> dict[str, Any]:
    return {
        "bid_assessment_applicable": False,
        "bid_assessment_scope_reason": None,
        "opportunity_routes": [],
        "direct_bid_fit_path": None,
        "bid_role": None,
        "eligibility_status": None,
        "eligibility_evidence": [],
        "mandatory_qualification_requirements": [],
        "qualification_match_results": [],
        "missing_qualifications": [],
        "performance_requirements": [],
        "performance_match_status": None,
        "required_business_registration_codes": [],
        "regional_restriction": None,
        "sme_restriction": None,
        "direct_production_certificate_required": None,
        "software_business_registration_required": None,
        "joint_contract_allowed": None,
        "subcontract_allowed": None,
        "required_personnel": [],
        "required_certifications": [],
        "required_onsite_staff": None,
        "proposal_presentation_required": None,
        "estimated_internal_delivery_capacity": None,
        "estimated_partner_dependency": None,
        "bid_participation_readiness": None,
        "bid_blocking_reasons": [],
        "bid_go_no_go": None,
        "bid_review_deadline": None,
        "recommended_bid_action": None,
        "sales_windows": [],
        "bid_priority_band": None,
        "qrpick_showda_delivery_scope": [],
        "partner_needed_scope": [],
        "bid_gate_checklist": {},
        "bid_assessment_basis": [],
        "source_scope": None,
        "primary_route": None,
    }


def determine_bid_assessment_applicability(
    text: str,
    bid_rules: dict[str, Any],
    *,
    opportunity_type: str | None,
    ascii_boundary: set[str],
    title_text: str | None = None,
) -> tuple[bool, str]:
    """Decide whether bid assessment should run on this notice.

    Scope signals are evaluated primarily on the title. Legacy classifier labels
    such as opportunity_kind='입찰·용역' must not invent procurement scope.
    """
    title = title_text or text
    positive = _hits(title, bid_rules.get("bid_scope_positive_signals"), ascii_boundary)
    negative = _hits(title, bid_rules.get("bid_scope_negative_signals"), ascii_boundary)
    override = _hits(title, bid_rules.get("bid_scope_override_positive"), ascii_boundary)
    tender = _hits(title, bid_rules.get("procurement_or_tender_signals"), ascii_boundary)

    otype = opportunity_type or "OTHER"

    # Title negatives without strong operator override → out of scope
    if negative and not override:
        return False, "non_contract_notice:" + ",".join(negative[:4])

    if negative and override:
        return True, "negative_overridden_by_operator_selection:" + ",".join(override[:4])

    if positive or tender:
        return True, "contract_counterparty_signals:" + ",".join((positive or tender)[:5])

    if otype == "PROCUREMENT_OR_BUILD":
        if any(k in title for k in ("용역", "입찰", "RFP", "조달", "위탁", "사업자 선정", "수행기관")):
            return True, "opportunity_type_PROCUREMENT_OR_BUILD+contract_token"
        return False, "opportunity_type_PROCUREMENT_OR_BUILD_without_contract_token"

    if otype in {"EDUCATION", "SPACE_OR_INCUBATION", "SUPPORT_PROGRAM", "NETWORKING"}:
        return False, f"opportunity_type_out_of_scope:{otype}"

    if otype in {"EXHIBITION_OR_MARKET_ACCESS", "SALES_SIGNAL"}:
        if override or tender:
            return True, "exhibition_with_operator_selection"
        return False, "exhibition_or_sales_signal_not_bid"

    return False, "no_contract_counterparty_signal"


def _not_applicable_result(reason: str) -> dict[str, Any]:
    out = empty_bid_fields()
    out["bid_assessment_applicable"] = False
    out["bid_assessment_scope_reason"] = reason
    out["bid_assessment_basis"] = [f"scope_excluded:{reason}"]
    return out


def _hits(text: str, keys: list[str] | None, ascii_boundary: set[str]) -> list[str]:
    return _find_hits(text, keys or [], ascii_boundary)


def _has_attachments(rec: dict[str, Any]) -> bool:
    atts = rec.get("attachment_urls") or []
    return bool(atts)


def _detail_verified(rec: dict[str, Any]) -> bool:
    return str(rec.get("detail_verification_status") or "").upper() == "VERIFIED"


def _parse_deadline(rec: dict[str, Any]) -> date | None:
    raw = rec.get("deadline") or rec.get("application_end")
    if not raw:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    s = str(raw)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _dday(rec: dict[str, Any], today: date) -> int | None:
    """Return days remaining until deadline (negative if past).

    Accepts numeric dday or Korean display strings: D-7, D-Day, D+3.
    """
    raw = rec.get("dday")
    if raw is not None:
        if isinstance(raw, int):
            return raw
        s = str(raw).strip()
        try:
            return int(s)
        except ValueError:
            pass
        upper = s.upper().replace(" ", "")
        if upper in {"D-DAY", "DDAY"}:
            return 0
        if upper.startswith("D-") and upper[2:].isdigit():
            return int(upper[2:])
        if upper.startswith("D+") and upper[2:].isdigit():
            return -int(upper[2:])
    dl = _parse_deadline(rec)
    if not dl:
        return None
    return (dl - today).days


def assess_bid_opportunity(
    rec: dict[str, Any],
    bid_rules: dict[str, Any],
    *,
    profile: dict[str, Any] | None = None,
    asset_fit: dict[str, Any] | None = None,
    today: date | None = None,
    ascii_boundary: set[str] | None = None,
) -> dict[str, Any]:
    """Return bid-assessment fields to merge onto an opportunity record."""
    today = today or date.today()
    ascii_boundary = ascii_boundary or set()
    profile = profile or {}
    asset_fit = asset_fit or {}
    out = empty_bid_fields()

    text = haystack(
        rec.get("title"),
        rec.get("program"),
        rec.get("category"),
        rec.get("organization"),
        rec.get("support_type"),
        rec.get("applicant_summary"),
        # Do NOT include opportunity_kind — legacy label '입찰·용역' invents false tender hits
    )
    # Prefer body/detail excerpts when present (never invent)
    for extra in ("detail_text", "body_excerpt", "description_summary"):
        if rec.get(extra):
            text = haystack(text, rec.get(extra))

    title_text = str(rec.get("title") or "")

    otype = asset_fit.get("opportunity_type") or rec.get("opportunity_type")
    primary = asset_fit.get("primary_asset_fit_path") or rec.get("primary_asset_fit_path")
    families = list(asset_fit.get("matched_asset_families") or rec.get("matched_asset_families") or [])
    usable_q = list(asset_fit.get("usable_qrpick_features") or rec.get("usable_qrpick_features") or [])
    partner_scope = list(asset_fit.get("partner_required_scope") or rec.get("partner_required_scope") or [])

    applicable, scope_reason = determine_bid_assessment_applicability(
        text,
        bid_rules,
        opportunity_type=otype,
        ascii_boundary=ascii_boundary,
        title_text=title_text,
    )
    if not applicable:
        return _not_applicable_result(scope_reason)

    out["bid_assessment_applicable"] = True
    out["bid_assessment_scope_reason"] = scope_reason
    out["source_scope"] = "PHASE2_PROCUREMENT_LIKE_NOT_G2B_COLLECTOR"

    tender = _hits(text, bid_rules.get("procurement_or_tender_signals"), ascii_boundary)
    std = _hits(text, bid_rules.get("qrpick_standard_signals"), ascii_boundary)
    ops = _hits(text, bid_rules.get("qrpick_ops_signals"), ascii_boundary)
    custom = _hits(text, bid_rules.get("showda_custom_build_signals"), ascii_boundary)
    platform = _hits(text, bid_rules.get("showda_platform_data_signals"), ascii_boundary)
    consortium = _hits(text, bid_rules.get("consortium_or_joint_signals"), ascii_boundary)
    subcontract = _hits(text, bid_rules.get("subcontract_or_partner_signals"), ascii_boundary)
    award = _hits(text, bid_rules.get("award_winner_sales_signals"), ascii_boundary)
    production = _hits(text, bid_rules.get("event_production_partner_signals"), ascii_boundary)
    specialist = _hits(text, bid_rules.get("specialist_partner_signals"), ascii_boundary)
    qual_hints = _hits(text, bid_rules.get("qualification_hint_keywords"), ascii_boundary)

    # Role evidence must come from keywords / usable features / event-ops family —
    # not from asset_fit primary path alone (CUSTOM_BUILD_SERVICE is often over-assigned).
    sw_ops_role = bool(
        std
        or ops
        or custom
        or platform
        or usable_q
        or "QRPICK_EVENT_OPERATIONS" in families
    )

    # Contract-like evidence from title/body — never from opportunity_kind
    strong_contract = bool(
        tender
        or any(
            k in title_text
            for k in (
                "용역",
                "입찰",
                "RFP",
                "조달",
                "위탁",
                "사업자 선정",
                "수행기관",
                "운영사업자",
                "구축용역",
            )
        )
    )

    basis: list[str] = [f"scope:{scope_reason}"]
    if tender:
        basis.append("tender_signals:" + ",".join(tender[:5]))
    if std:
        basis.append("qrpick_standard:" + ",".join(std[:5]))
    if ops:
        basis.append("qrpick_ops:" + ",".join(ops[:5]))
    if custom:
        basis.append("showda_build:" + ",".join(custom[:5]))
    if platform:
        basis.append("showda_platform:" + ",".join(platform[:5]))

    routes: list[str] = []
    # Direct prime only with SW/ops/platform role — never industry-name exclusion alone
    production_heavy = bool(production) and not (std or ops or custom or platform)
    if strong_contract and sw_ops_role and not production_heavy:
        routes.append("DIRECT_PRIME_BID")
        basis.append("route:DIRECT_PRIME_BID(sw_ops_role+contract)")
    elif strong_contract and (std or ops or custom or platform) and not production_heavy:
        routes.append("DIRECT_PRIME_BID")
        basis.append("route:DIRECT_PRIME_BID(keyword)")

    if consortium or production or primary == "PARTNER_CONSORTIUM":
        if sw_ops_role or custom or platform or std or production:
            routes.append("CONSORTIUM_BID")
            basis.append("route:CONSORTIUM_BID")

    if subcontract or (strong_contract and sw_ops_role):
        routes.append("SUBCONTRACT_OR_SOLUTION_PARTNER")
        basis.append("route:SUBCONTRACT_OR_SOLUTION_PARTNER")

    if award:
        routes.append("AWARD_WINNER_SALES")
        basis.append("route:AWARD_WINNER_SALES")

    # Deduplicate preserve order
    routes = list(dict.fromkeys(routes))

    # Fit path
    if specialist and not (std or ops or custom) and not sw_ops_role:
        fit_path = "PARTNER_SPECIALIST_REQUIRED"
    elif (production or consortium) and sw_ops_role and not (std or ops) and not custom:
        fit_path = "CONSORTIUM_REQUIRED"
    elif (production or consortium) and sw_ops_role and (std or ops or custom):
        # Can still bid as system lead inside consortium
        if custom or platform:
            fit_path = "SHOWDA_CUSTOM_BUILD" if custom else "SHOWDA_PLATFORM_AND_DATA"
        elif ops:
            fit_path = "QRPICK_PLUS_OPERATION"
        else:
            fit_path = "CONSORTIUM_REQUIRED"
    elif platform and not std and not ops:
        fit_path = "SHOWDA_PLATFORM_AND_DATA"
    elif custom:
        fit_path = "SHOWDA_CUSTOM_BUILD"
    elif ops and std:
        fit_path = "QRPICK_PLUS_OPERATION"
    elif ops:
        fit_path = "QRPICK_PLUS_OPERATION"
    elif std:
        fit_path = "QRPICK_STANDARD_SERVICE"
    elif routes:
        # Has route but weak path signal — still allow consortium/partner paths
        if "CONSORTIUM_BID" in routes and "DIRECT_PRIME_BID" not in routes:
            fit_path = "CONSORTIUM_REQUIRED"
        elif "SUBCONTRACT_OR_SOLUTION_PARTNER" in routes and "DIRECT_PRIME_BID" not in routes:
            fit_path = "PARTNER_SPECIALIST_REQUIRED"
        else:
            fit_path = "SHOWDA_CUSTOM_BUILD" if strong_contract else "NO_REALISTIC_DIRECT_BID_PATH"
    else:
        fit_path = "NO_REALISTIC_DIRECT_BID_PATH"

    if specialist and fit_path in {
        "QRPICK_STANDARD_SERVICE",
        "QRPICK_PLUS_OPERATION",
        "SHOWDA_CUSTOM_BUILD",
        "SHOWDA_PLATFORM_AND_DATA",
    }:
        # Keep primary path but note specialist dependency
        out["estimated_partner_dependency"] = "HIGH"
        partner_scope = list(dict.fromkeys(partner_scope + specialist[:5]))

    out["direct_bid_fit_path"] = fit_path
    out["opportunity_routes"] = routes

    # Bid role
    if "DIRECT_PRIME_BID" in routes and fit_path in {
        "QRPICK_STANDARD_SERVICE",
        "QRPICK_PLUS_OPERATION",
        "SHOWDA_CUSTOM_BUILD",
        "SHOWDA_PLATFORM_AND_DATA",
    }:
        bid_role = "PRIME"
    elif "CONSORTIUM_BID" in routes:
        bid_role = "CONSORTIUM_MEMBER" if fit_path == "CONSORTIUM_REQUIRED" else "JOINT_CONTRACTOR"
    elif "SUBCONTRACT_OR_SOLUTION_PARTNER" in routes:
        bid_role = "SOLUTION_SUPPLIER"
    elif "AWARD_WINNER_SALES" in routes:
        bid_role = "SOLUTION_SUPPLIER"
    else:
        bid_role = "NONE"
    out["bid_role"] = bid_role

    # Soft restriction flags from keyword hints only
    regional = _hits(text, bid_rules.get("regional_restriction_hints"), ascii_boundary)
    sme = _hits(text, bid_rules.get("sme_restriction_hints"), ascii_boundary)
    sw_reg = _hits(text, bid_rules.get("software_biz_reg_hints"), ascii_boundary)
    direct_prod = _hits(text, bid_rules.get("direct_production_hints"), ascii_boundary)
    joint_ok = _hits(text, bid_rules.get("joint_allowed_hints"), ascii_boundary)
    joint_no = _hits(text, bid_rules.get("joint_disallowed_hints"), ascii_boundary)
    sub_ok = _hits(text, bid_rules.get("subcontract_allowed_hints"), ascii_boundary)
    sub_no = _hits(text, bid_rules.get("subcontract_disallowed_hints"), ascii_boundary)
    present = _hits(text, bid_rules.get("presentation_hints"), ascii_boundary)

    out["regional_restriction"] = "HINT_PRESENT" if regional else None
    out["sme_restriction"] = "HINT_PRESENT" if sme else None
    out["software_business_registration_required"] = True if sw_reg else None
    out["direct_production_certificate_required"] = True if direct_prod else None
    if joint_ok and not joint_no:
        out["joint_contract_allowed"] = True
    elif joint_no and not joint_ok:
        out["joint_contract_allowed"] = False
    else:
        out["joint_contract_allowed"] = None
    if sub_ok and not sub_no:
        out["subcontract_allowed"] = True
    elif sub_no and not sub_ok:
        out["subcontract_allowed"] = False
    else:
        out["subcontract_allowed"] = None
    out["proposal_presentation_required"] = True if present else None

    if qual_hints:
        out["mandatory_qualification_requirements"] = qual_hints[:12]
        out["eligibility_evidence"].append("qualification_hints:" + ",".join(qual_hints[:6]))

    # Delivery scope summaries
    delivery: list[str] = []
    if std:
        delivery.append("QRPick 표준(등록·체크인·매칭 등): " + ", ".join(std[:4]))
    if ops:
        delivery.append("운영·현장: " + ", ".join(ops[:4]))
    if custom:
        delivery.append("쇼다 구축·시스템: " + ", ".join(custom[:4]))
    if platform:
        delivery.append("플랫폼·데이터: " + ", ".join(platform[:4]))
    out["qrpick_showda_delivery_scope"] = delivery or usable_q[:6]
    out["partner_needed_scope"] = list(
        dict.fromkeys((partner_scope or []) + production[:4] + specialist[:4])
    )

    if production or specialist or fit_path in {"CONSORTIUM_REQUIRED", "PARTNER_SPECIALIST_REQUIRED"}:
        out["estimated_partner_dependency"] = out.get("estimated_partner_dependency") or "HIGH"
    elif "CONSORTIUM_BID" in routes:
        out["estimated_partner_dependency"] = "MEDIUM"
    elif routes:
        out["estimated_partner_dependency"] = "LOW"
    else:
        out["estimated_partner_dependency"] = "NONE"

    out["estimated_internal_delivery_capacity"] = "UNKNOWN"  # never invent capacity

    # Gate checklist — list stage almost always incomplete
    has_deadline = _parse_deadline(rec) is not None
    has_budget = bool(rec.get("support_amount") or rec.get("budget") or rec.get("estimated_amount"))
    has_period = bool(rec.get("application_start") or "수행기간" in text or "계약기간" in text)
    role_clear = bool(delivery) or bool(std or ops or custom or platform)
    attachments = _has_attachments(rec)
    verified = _detail_verified(rec)

    gates = {
        "announcement_and_proposal_deadline": has_deadline,
        "mandatory_bid_qualifications": bool(verified and attachments),
        "regional_or_sme_restrictions": bool(verified),
        "performance_requirements": bool(verified and attachments),
        "joint_contract_allowed_known": out["joint_contract_allowed"] is not None and verified,
        "qrpick_showda_role_scope": role_clear,
        "delivery_period": has_period and verified,
        "budget_or_estimated_amount": has_budget,
        "internal_delivery_capacity": False,  # never auto-confirm capacity from list
    }

    out["bid_gate_checklist"] = gates
    missing_gates = [g for g, ok in gates.items() if not ok]

    blocking: list[str] = []
    for g in missing_gates:
        blocking.append(f"gate_unconfirmed:{g}")

    company = profile.get("company") or {}
    if str(company.get("verification_status", "")).upper() == "INTERNAL_COMPANY_PROFILE_ONLY":
        blocking.append("company_profile_not_officially_verified")
        out["missing_qualifications"].append("공식 사업자·업력·소재지 원본 미검증")

    if not attachments:
        blocking.append("attachments_not_fetched")
        out["missing_qualifications"].append("제안요청서·과업지시서 미확보")

    if not verified:
        blocking.append("detail_not_verified")

    dday = _dday(rec, today)
    out["bid_review_deadline"] = rec.get("deadline")

    # Eligibility = qualification conditions only (never from deadline alone).
    # List stage without attachments/detail: keep UNKNOWN_NEEDS_DOCUMENT_REVIEW.
    # Role/path absence drives readiness/go, not eligibility.
    if not attachments or not verified:
        eligibility = "UNKNOWN_NEEDS_DOCUMENT_REVIEW"
        out["eligibility_evidence"].append(
            "첨부·상세 미검증 — 자격 확정 금지 (마감과 무관)"
        )
        if not routes or fit_path == "NO_REALISTIC_DIRECT_BID_PATH":
            readiness = "NO_BID" if not routes else "WATCH"
            go = "NO_GO" if not routes else "UNKNOWN"
            action = "입찰 경로 없음 — 영업·관찰만 검토" if not routes else "문서 확보 후 입찰 경로 재평가"
        else:
            readiness = "QUALIFICATION_CHECK"
            if "CONSORTIUM_BID" in routes and "DIRECT_PRIME_BID" not in routes:
                readiness = "PARTNER_SEARCH"
            go = "UNKNOWN"
            action = "제안요청서·과업지시서 확보 후 자격·역할·공동수급 검토"
    else:
        # Attachments + verified detail present — still conservative without full gate clear
        if not routes or fit_path == "NO_REALISTIC_DIRECT_BID_PATH":
            # Docs present but no realistic Showda/QRPick bid role — not a qualification fail
            eligibility = "UNKNOWN_NEEDS_DOCUMENT_REVIEW"
            readiness = "NO_BID" if not routes else "WATCH"
            go = "NO_GO" if not routes else "UNKNOWN"
            action = "입찰 경로 없음 — 영업·관찰만 검토" if not routes else "문서 확보 후 입찰 경로 재평가"
        elif missing_gates:
            eligibility = "PARTIALLY_ELIGIBLE" if sw_ops_role else "UNKNOWN_NEEDS_DOCUMENT_REVIEW"
            readiness = "QUALIFICATION_CHECK"
            go = "CONDITIONAL_GO" if len(missing_gates) <= 3 and has_deadline else "HOLD"
            action = "상세 자격·실적·공동수급 조건 대조 후 응찰 결정"
        else:
            eligibility = "VERIFIED_ELIGIBLE"
            readiness = "ACTION_NOW"
            go = "GO"
            action = "직접 입찰 준비(제안서·공동수급 서류)"

    # Hard safety: never allow VERIFIED/GO/ACTION_NOW without attachments+verified
    if eligibility == "VERIFIED_ELIGIBLE" and (not attachments or not verified):
        eligibility = "UNKNOWN_NEEDS_DOCUMENT_REVIEW"
        readiness = "QUALIFICATION_CHECK"
        go = "UNKNOWN"
        blocking.append("safety_block:verified_without_documents")
    if readiness == "ACTION_NOW" and (not attachments or not verified or missing_gates):
        readiness = "QUALIFICATION_CHECK"
        if go == "GO":
            go = "CONDITIONAL_GO" if attachments and verified else "UNKNOWN"
        blocking.append("safety_block:action_now_gates_incomplete")
    if go == "GO" and (not attachments or not verified):
        go = "UNKNOWN"
        blocking.append("safety_block:go_without_documents")

    # Expired → readiness/go only; do NOT change eligibility_status
    if dday is not None and dday < 0:
        readiness = "NO_BID"
        go = "NO_GO"
        action = "제안 마감 경과 — 낙찰 후 영업(AWARD_WINNER_SALES)만 검토"
        if "AWARD_WINNER_SALES" not in routes and award:
            routes.append("AWARD_WINNER_SALES")
        blocking.append("deadline_passed_readiness_only")

    out["eligibility_status"] = eligibility
    out["bid_participation_readiness"] = readiness
    out["bid_go_no_go"] = go
    out["recommended_bid_action"] = action
    out["bid_blocking_reasons"] = list(dict.fromkeys(blocking))
    out["performance_match_status"] = "UNKNOWN"
    out["qualification_match_results"] = [
        "list_stage_keyword_hints_only — not an official qualification decision"
    ]
    out["primary_route"] = primary_opportunity_route(routes)
    out["opportunity_routes"] = routes

    # sales_windows
    windows: list[str] = []
    if (
        "DIRECT_PRIME_BID" in routes
        and fit_path != "NO_REALISTIC_DIRECT_BID_PATH"
        and dday is not None
        and dday >= 0
        and readiness in {"ACTION_NOW", "QUALIFICATION_CHECK", "PARTNER_SEARCH"}
    ):
        windows.append("DIRECT_BID_WINDOW")
    if (
        "CONSORTIUM_BID" in routes
        and dday is not None
        and dday >= 0
        and out["joint_contract_allowed"] is not False
        and fit_path
        in {
            "CONSORTIUM_REQUIRED",
            "SHOWDA_CUSTOM_BUILD",
            "SHOWDA_PLATFORM_AND_DATA",
            "QRPICK_PLUS_OPERATION",
            "QRPICK_STANDARD_SERVICE",
        }
    ):
        windows.append("CONSORTIUM_PARTNER_WINDOW")
    out["sales_windows"] = windows

    # Priority band (informational)
    p0_min = int(bid_rules.get("p0_deadline_days_min", 3))
    p0_max = int(bid_rules.get("p0_deadline_days_max", 21))
    if (
        "DIRECT_BID_WINDOW" in windows
        and dday is not None
        and p0_min <= dday <= p0_max
        and has_budget
        and readiness in {"ACTION_NOW", "QUALIFICATION_CHECK"}
    ):
        out["bid_priority_band"] = "P0_IMMEDIATE"
    elif "CONSORTIUM_PARTNER_WINDOW" in windows or (
        "DIRECT_BID_WINDOW" in windows and dday is not None and dday > p0_max
    ):
        out["bid_priority_band"] = "P1_HIGH"
    elif routes:
        out["bid_priority_band"] = "P2_WATCH"
    else:
        out["bid_priority_band"] = None

    out["bid_assessment_basis"] = basis
    out["eligibility_evidence"] = list(dict.fromkeys(out["eligibility_evidence"]))
    return out


def primary_opportunity_route(routes: list[str] | None) -> str | None:
    """Prefer direct → consortium → partner → award when multiple routes apply."""
    if not routes:
        return None
    for preferred in (
        "DIRECT_PRIME_BID",
        "CONSORTIUM_BID",
        "SUBCONTRACT_OR_SOLUTION_PARTNER",
        "AWARD_WINNER_SALES",
    ):
        if preferred in routes:
            return preferred
    return routes[0]


def is_direct_bid_candidate(rec: dict[str, Any]) -> bool:
    if not rec.get("bid_assessment_applicable"):
        return False
    routes = rec.get("opportunity_routes") or []
    path = rec.get("direct_bid_fit_path")
    return "DIRECT_PRIME_BID" in routes and path not in {None, "NO_REALISTIC_DIRECT_BID_PATH"}


def is_consortium_candidate(rec: dict[str, Any]) -> bool:
    if not rec.get("bid_assessment_applicable"):
        return False
    routes = rec.get("opportunity_routes") or []
    return "CONSORTIUM_BID" in routes


def is_solution_partner_candidate(rec: dict[str, Any]) -> bool:
    if not rec.get("bid_assessment_applicable"):
        return False
    routes = rec.get("opportunity_routes") or []
    return "SUBCONTRACT_OR_SOLUTION_PARTNER" in routes
