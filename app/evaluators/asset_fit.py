"""Asset-fit paths, confidence, opportunity type, and action queues (no LLM).

Separates business relevance from recommended next action.
"""
from __future__ import annotations

from typing import Any

from app.evaluators.scoring import _find_hits
from app.normalizers.text_utils import haystack


ASSET_FIT_PATHS = (
    "QRPICK_DIRECT",
    "QRPICK_EXTENSION",
    "SHOWDA_ASSET_REUSE",
    "CUSTOM_BUILD_SERVICE",
    "PARTNER_CONSORTIUM",
    "SALES_LEAD",
    "NO_REALISTIC_PATH",
)

FIT_CONFIDENCE = ("STRONG", "MEDIUM", "WEAK", "NONE")

OPPORTUNITY_TYPES = (
    "SUPPORT_PROGRAM",
    "DEMAND_CHALLENGE",
    "PROCUREMENT_OR_BUILD",
    "SALES_SIGNAL",
    "EXHIBITION_OR_MARKET_ACCESS",
    "NETWORKING",
    "EDUCATION",
    "SPACE_OR_INCUBATION",
    "CONSULTING_SUPPORT",
    "OTHER",
)

ACTION_QUEUES = (
    "ACTION_NOW",
    "QUALIFICATION_CHECK",
    "SALES_OUTREACH",
    "WATCHLIST",
    "NO_ACTION",
    "CLOSED",
)


def _hits(text: str, keys: list[str], ascii_boundary: set[str]) -> list[str]:
    return _find_hits(text, keys or [], ascii_boundary)


def _match_families(
    text: str,
    families: dict[str, list[str]],
    ascii_boundary: set[str],
    generic_forbidden: set[str],
) -> tuple[list[str], dict[str, list[str]]]:
    """Return family ids with non-generic evidence hits."""
    matched: list[str] = []
    evidence: dict[str, list[str]] = {}
    for fam, kws in (families or {}).items():
        fam_hits = _hits(text, kws, ascii_boundary)
        # Drop hits that are only generic forbidden words
        concrete = [h for h in fam_hits if h.casefold() not in generic_forbidden]
        if concrete:
            matched.append(fam)
            evidence[fam] = concrete[:8]
    return matched, evidence


def _classify_opportunity_type(text: str, rules: dict[str, Any], ascii_boundary: set[str]) -> str:
    cfg = rules.get("opportunity_type_keywords") or {}
    # Priority order matters
    order = (
        "EDUCATION",
        "SPACE_OR_INCUBATION",
        "PROCUREMENT_OR_BUILD",
        "DEMAND_CHALLENGE",
        "EXHIBITION_OR_MARKET_ACCESS",
        "SALES_SIGNAL",
        "NETWORKING",
        "CONSULTING_SUPPORT",
        "SUPPORT_PROGRAM",
    )
    for otype in order:
        if _hits(text, cfg.get(otype) or [], ascii_boundary):
            return otype
    return "OTHER"


def assess_asset_fit(
    rec: dict[str, Any],
    rules: dict[str, Any],
    profile: dict[str, Any] | None,
    scored: dict[str, Any],
    *,
    is_expired: bool = False,
) -> dict[str, Any]:
    profile = profile or {}
    cfg = rules.get("asset_fit") or {}
    ascii_boundary = set(rules.get("ascii_word_boundary_keywords") or [])
    generic_forbidden = {g.casefold() for g in (cfg.get("generic_alone_forbidden") or [])}

    text = haystack(
        rec.get("title"),
        rec.get("program"),
        rec.get("category"),
        rec.get("organization"),
    )
    text_no_org = haystack(rec.get("title"), rec.get("program"), rec.get("category"))

    matched_groups = set(scored.get("matched_groups") or [])
    breakdown = scored.get("breakdown") or {}

    direct_hits = _hits(text_no_org, cfg.get("direct_feature_keywords") or [], ascii_boundary)
    extension_hits = _hits(text_no_org, cfg.get("extension_keywords") or [], ascii_boundary)
    sales_hits = _hits(text, cfg.get("sales_lead_keywords") or [], ascii_boundary)
    build_hits = _hits(text, cfg.get("custom_build_required_keywords") or [], ascii_boundary)
    partner_hits = _hits(text, cfg.get("partner_keywords") or [], ascii_boundary)
    industrial_core = _hits(text_no_org, cfg.get("industrial_tech_core_keywords") or [], ascii_boundary)

    families, family_evidence = _match_families(
        text_no_org,
        cfg.get("asset_families") or {},
        ascii_boundary,
        generic_forbidden,
    )

    # Domain role for industrial override (concrete role, not generic-only)
    role_override = _hits(text_no_org, rules.get("domain_role_override_signals") or [], ascii_boundary)
    concrete_role_hits = [h for h in role_override if h.casefold() not in generic_forbidden]
    has_sw_ops_role = bool(
        concrete_role_hits
        or direct_hits
        or extension_hits
        or families
        or (matched_groups & {"ops_infra", "core_mice", "tourism_extension"})
    )

    opportunity_type = _classify_opportunity_type(text, rules, ascii_boundary)

    # Legacy opportunity_kind (Korean label for CSV compat)
    if opportunity_type == "PROCUREMENT_OR_BUILD":
        opportunity_kind = "입찰·용역"
    elif opportunity_type in ("EXHIBITION_OR_MARKET_ACCESS", "SALES_SIGNAL"):
        opportunity_kind = "영업단서"
    elif opportunity_type in ("SUPPORT_PROGRAM", "DEMAND_CHALLENGE"):
        opportunity_kind = "지원사업"
    elif opportunity_type == "EDUCATION":
        opportunity_kind = "교육"
    else:
        opportunity_kind = "기타"

    # --- Path candidates (multi-path) ---
    candidates: list[str] = []
    fit_evidence: list[str] = []
    evidence_source = "title_program_category_list_fields"

    edu_like = opportunity_type == "EDUCATION"
    space_like = opportunity_type == "SPACE_OR_INCUBATION"
    exhibition_sales = opportunity_type in ("EXHIBITION_OR_MARKET_ACCESS", "SALES_SIGNAL") or bool(sales_hits)

    if direct_hits or "QRPICK_EVENT_OPERATIONS" in families:
        candidates.append("QRPICK_DIRECT")
        fit_evidence.append(
            "직접적용 근거: "
            + ", ".join((direct_hits or family_evidence.get("QRPICK_EVENT_OPERATIONS") or [])[:5])
        )
    elif "B2B_MATCHING_OR_COMMERCE" in families and any(
        k in text_no_org for k in ("매칭 시스템", "등록 시스템", "운영시스템", "운영 시스템", "체크인")
    ):
        candidates.append("QRPICK_DIRECT")
        fit_evidence.append(
            "매칭·운영시스템 근거: "
            + ", ".join(family_evidence.get("B2B_MATCHING_OR_COMMERCE", [])[:5])
        )
    if extension_hits or "tourism_extension" in matched_groups:
        candidates.append("QRPICK_EXTENSION")
        fit_evidence.append("확장 근거: " + ", ".join((extension_hits or (breakdown.get("tourism_extension") or {}).get("hits") or [])[:5]))

    if build_hits and not edu_like and not space_like:
        strong_build = any(
            k in text
            for k in (
                "구축",
                "용역",
                "입찰",
                "운영대행",
                "유지관리",
                "정보화",
                "운영시스템",
                "운영 시스템",
                "플랫폼 구축",
                "시스템 구축",
                "플랫폼 제작",
            )
        )
        # Exhibition/OI participant calls are not automatic CUSTOM_BUILD
        if opportunity_type in ("EXHIBITION_OR_MARKET_ACCESS", "SALES_SIGNAL", "NETWORKING") and not strong_build:
            pass
        elif opportunity_type == "DEMAND_CHALLENGE" and not strong_build and "고도화" not in text:
            pass
        else:
            candidates.append("CUSTOM_BUILD_SERVICE")
            fit_evidence.append("구축·용역 근거: " + ", ".join(build_hits[:5]))

    if families and not edu_like:
        # SHOWDA only with explicit families; never generic-alone
        # Prefer not if we already have stronger primary candidates only as secondary
        candidates.append("SHOWDA_ASSET_REUSE")
        fam_bits = [f"{f}:{','.join(family_evidence.get(f, [])[:3])}" for f in families]
        fit_evidence.append("자산군 근거: " + " | ".join(fam_bits))

    if partner_hits and (industrial_core or not has_sw_ops_role):
        candidates.append("PARTNER_CONSORTIUM")
        fit_evidence.append("파트너 근거: " + ", ".join(partner_hits[:5]))

    # SALES as path candidate but prefer secondary / opportunity_type
    if exhibition_sales and not edu_like:
        candidates.append("SALES_LEAD")
        fit_evidence.append("영업단서 근거: " + ", ".join((sales_hits or ["전시·참가·판로 신호"])[:5]))

    # De-dupe preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered.append(c)

    # Primary path priority
    priority = [
        "QRPICK_DIRECT",
        "CUSTOM_BUILD_SERVICE",
        "QRPICK_EXTENSION",
        "SHOWDA_ASSET_REUSE",
        "PARTNER_CONSORTIUM",
        "SALES_LEAD",
    ]
    primary = None
    for p in priority:
        if p in ordered:
            # Prefer not SHOWDA as primary when only weak families without build/direct/sales
            if p == "SHOWDA_ASSET_REUSE" and not families:
                continue
            if p == "SALES_LEAD" and any(x in ordered for x in ("QRPICK_DIRECT", "CUSTOM_BUILD_SERVICE", "QRPICK_EXTENSION")):
                continue
            primary = p
            break

    secondary = [p for p in ordered if p != primary]

    # If exhibition sales only → primary can be SALES_LEAD, secondary may include QRPICK_DIRECT weakly
    if primary is None and exhibition_sales:
        primary = "SALES_LEAD"
        if "SALES_LEAD" not in ordered:
            ordered.append("SALES_LEAD")
        secondary = [p for p in ordered if p != primary]

    if primary is None:
        if industrial_core and not has_sw_ops_role and not build_hits and not exhibition_sales and not families:
            primary = "NO_REALISTIC_PATH"
            fit_evidence.append("전문산업 핵심 + SW/운영/구축/영업/자산군 연결 없음")
        elif edu_like or space_like:
            primary = "NO_REALISTIC_PATH"
            fit_evidence.append("교육생·입주 중심 — 사업 자산 적용 경로 약함(목록 기준)")
        else:
            primary = "NO_REALISTIC_PATH"
            fit_evidence.append("명시적 자산군·직접기능·구축 근거 부족 → NO_REALISTIC_PATH")

    # Confidence
    if primary in ("QRPICK_DIRECT", "CUSTOM_BUILD_SERVICE") and (direct_hits or build_hits):
        fit_confidence = "STRONG"
    elif primary in ("QRPICK_EXTENSION", "SALES_LEAD") and (extension_hits or sales_hits):
        fit_confidence = "MEDIUM" if primary == "SALES_LEAD" else "STRONG"
    elif primary == "SHOWDA_ASSET_REUSE" and families:
        fit_confidence = "MEDIUM" if len(families) >= 2 else "WEAK"
    elif primary == "PARTNER_CONSORTIUM":
        fit_confidence = "WEAK"
    elif primary == "NO_REALISTIC_PATH":
        fit_confidence = "NONE"
    else:
        fit_confidence = "WEAK"

    # --- Provisional action queue (list-stage; never final ACTION_NOW here) ---
    if is_expired:
        provisional_queue = "CLOSED"
        recommended = "마감 종료 — 신규 공고만 모니터링"
    elif opportunity_type == "EDUCATION" and not exhibition_sales:
        provisional_queue = "NO_ACTION"
        recommended = "개인·교육생 모집 — 우선 검토 제외"
    elif space_like and not build_hits and not families:
        provisional_queue = "NO_ACTION"
        recommended = "입주공간 중심 — 사업화 대기열에서 제외"
    elif opportunity_type == "CONSULTING_SUPPORT" and not build_hits and not families:
        provisional_queue = "NO_ACTION"
        recommended = "멘토링·자문 중심 — 제품/구축 기회 약함"
    elif primary in ("QRPICK_DIRECT", "CUSTOM_BUILD_SERVICE") or (
        build_hits and (direct_hits or families or "ops_infra" in matched_groups)
    ):
        # 구축·등록·매칭 시스템 수요는 참가모집보다 자격확인 우선 (목록단계)
        linked = bool(
            families or direct_hits or extension_hits or concrete_role_hits
            or (matched_groups & {"ops_infra", "core_mice", "tourism_extension"})
        )
        if primary == "CUSTOM_BUILD_SERVICE" and not linked and not direct_hits:
            provisional_queue = "WATCHLIST"
            recommended = "구축 키워드만 있고 SW/행사/자산군 연결 약함 — 관찰"
        else:
            provisional_queue = "QUALIFICATION_CHECK"
            recommended = "목록상 직접·구축·운영시스템 신호 — 상세공고·자격·과업 확인 후 승격 검토"
    elif primary == "QRPICK_EXTENSION":
        if any(k in text for k in ("융자", "상환", "기금", "대출", "보증")) and not direct_hits and not families:
            provisional_queue = "QUALIFICATION_CHECK"
            recommended = "관광 키워드만 강하고 디지털 과업 불명 — 상세 확인"
        else:
            provisional_queue = "QUALIFICATION_CHECK"
            recommended = "목록상 관광·MICE 확장 신호 — 상세에서 디지털 과업·자격 확인"
    elif exhibition_sales or primary == "SALES_LEAD" or opportunity_type in (
        "EXHIBITION_OR_MARKET_ACCESS",
        "SALES_SIGNAL",
    ):
        provisional_queue = "SALES_OUTREACH"
        recommended = "참가·부스·판로 영업단서 — 상세·비용·효익 확인 후 아웃리치 여부 판단"
    elif primary == "PARTNER_CONSORTIUM" or (
        industrial_core and build_hits and not has_sw_ops_role
    ):
        provisional_queue = "QUALIFICATION_CHECK"
        recommended = "전문 도메인 구축·파트너 가능 — 상세에서 역할·컨소시엄 확인"
        if "PARTNER_CONSORTIUM" not in secondary and primary != "PARTNER_CONSORTIUM":
            secondary = list(secondary) + ["PARTNER_CONSORTIUM"]
    elif opportunity_type == "DEMAND_CHALLENGE" or (
        "오픈이노베이션" in text or "open innovation" in text
    ):
        provisional_queue = "QUALIFICATION_CHECK"
        recommended = "OI/실증·수요과제 — 상세공고·자격·매칭 조건 확인"
    elif families and fit_confidence in ("STRONG", "MEDIUM"):
        provisional_queue = "QUALIFICATION_CHECK"
        recommended = "목록상 자산군 신호 — 상세공고·자격·과업 확인 후 승격 검토"
    elif primary == "SHOWDA_ASSET_REUSE" and families:
        provisional_queue = "QUALIFICATION_CHECK" if fit_confidence == "MEDIUM" else "WATCHLIST"
        recommended = "자산군 연결은 있으나 상세 확인 전 — 자격·과업 확인 또는 관찰"
    elif opportunity_type == "NETWORKING":
        provisional_queue = "WATCHLIST"
        recommended = "네트워킹성 행사 — 주최기관 영업단서만 관찰"
    elif primary == "NO_REALISTIC_PATH" and fit_confidence == "NONE":
        provisional_queue = "NO_ACTION"
        recommended = "현실적 진입경로 없음(목록 기준)"
    else:
        provisional_queue = "WATCHLIST"
        recommended = "관련성 약한 관찰 대상"

    # Ops keywords on list → still QUALIFICATION_CHECK only (not ACTION_NOW)
    if (
        provisional_queue in ("WATCHLIST",)
        and opportunity_type not in ("EDUCATION",)
        and (direct_hits or "ops_infra" in matched_groups)
        and (build_hits or direct_hits)
    ):
        provisional_queue = "QUALIFICATION_CHECK"
        recommended = "행사 운영·등록·매칭·시스템 신호 — 상세공고 확인 후 승격 검토"

    # --- Detail verification / ACTION_NOW gate ---
    detail_verification_status = str(
        rec.get("detail_verification_status") or "NOT_FETCHED"
    ).upper()
    if detail_verification_status not in ("NOT_FETCHED", "PARTIAL", "VERIFIED"):
        detail_verification_status = "NOT_FETCHED"

    promotion_source = str(rec.get("action_promotion_source") or "RULE").upper()
    if promotion_source not in ("RULE", "DETAIL_REVIEW", "MANUAL"):
        promotion_source = "RULE"

    blocking_unknowns: list[str] = []
    if detail_verification_status != "VERIFIED":
        blocking_unknowns.extend(
            ["신청자격", "지원내용·과업산출물", "지원주체", "과업범위", "컨소시엄 필요 여부"]
        )
    company = (profile or {}).get("company") or {}
    soft_company_unknowns: list[str] = []
    if str(company.get("verification_status", "")).upper() == "INTERNAL_COMPANY_PROFILE_ONLY":
        soft_company_unknowns.extend(["소재지(공식검증 전)", "업력(공식검증 전)"])
    if is_expired:
        blocking_unknowns.append("마감·일정")
    blocking_unknowns = list(dict.fromkeys(blocking_unknowns))

    actionability_gate_reasons: list[str] = []
    actionability_verified = False
    action_queue = provisional_queue

    manual_promote = promotion_source == "MANUAL" and bool(rec.get("actionability_verified"))
    # DETAIL_REVIEW promotion: VERIFIED detail + no list/detail blockers (company official docs remain soft)
    detail_promote = (
        detail_verification_status == "VERIFIED"
        and promotion_source in ("DETAIL_REVIEW", "RULE")
        and provisional_queue in ("QUALIFICATION_CHECK", "SALES_OUTREACH", "WATCHLIST")
        and primary in ("QRPICK_DIRECT", "CUSTOM_BUILD_SERVICE", "QRPICK_EXTENSION")
        and fit_confidence in ("STRONG", "MEDIUM")
        and not is_expired
        and not blocking_unknowns
        and bool(rec.get("actionability_verified"))
    )

    if manual_promote:
        action_queue = "ACTION_NOW"
        actionability_verified = True
        actionability_gate_reasons = list(rec.get("actionability_gate_reasons") or []) or [
            "수동 승인(MANUAL)으로 ACTION_NOW 승격"
        ]
        promotion_source = "MANUAL"
        recommended = rec.get("recommended_next_action") or "수동 승인된 즉시 실행 과제"
        blocking_unknowns = []
    elif detail_promote:
        # Phase-3 path: only when VERIFIED and no blocking unknowns
        action_queue = "ACTION_NOW"
        actionability_verified = True
        actionability_gate_reasons = [
            "detail_verification_status=VERIFIED",
            f"primary_asset_fit_path={primary}",
            f"fit_confidence={fit_confidence}",
            "신청자격·과업·역할이 상세에서 확인됨(호출측 전제)",
            "마감 전이며 다음 행동 가능",
        ]
        promotion_source = "DETAIL_REVIEW"
        recommended = "상세검증 완료 — 제안·신청·입찰 등 즉시 실행"
    else:
        actionability_verified = False
        if provisional_queue == "ACTION_NOW":
            # Safety: never keep ACTION_NOW without gate
            action_queue = "QUALIFICATION_CHECK"
            recommended = "목록 데이터만으로는 ACTION_NOW 불가 — 상세검토 후 승격"
        actionability_gate_reasons = [
            "ACTION_NOW 미부여: detail_verification_status != VERIFIED (현재 "
            + detail_verification_status
            + ")"
        ]
        if blocking_unknowns:
            actionability_gate_reasons.append(
                "blocking_unknowns: " + ", ".join(blocking_unknowns[:8])
            )
        if soft_company_unknowns:
            actionability_gate_reasons.append(
                "soft_company_unknowns: " + ", ".join(soft_company_unknowns)
            )
        promotion_source = "RULE"

    # Annotations for report fields
    usable_qrpick: list[str] = []
    if primary in ("QRPICK_DIRECT", "QRPICK_EXTENSION") or "QRPICK_DIRECT" in secondary:
        if direct_hits or "QRPICK_EVENT_OPERATIONS" in families:
            usable_qrpick.append("QR 체크인·등록·발권·부스·매칭 등 행사운영 모듈")
        if primary == "QRPICK_EXTENSION" or extension_hits:
            usable_qrpick.append("관광·Bleisure·Destination 확장 모듈")

    usable_showda: list[str] = []
    fam_labels = {
        "QRPICK_EVENT_OPERATIONS": "행사운영 SaaS·현장서비스",
        "AI_PUBLIC_INFORMATION_SERVICE": "공공정보·안내 AI/WebApp",
        "CONTENT_CURATION_PLATFORM": "콘텐츠 큐레이션 플랫폼",
        "B2B_MATCHING_OR_COMMERCE": "B2B 매칭·상담 운영",
        "MOBILE_MARKETING_AND_COUPON": "모바일 마케팅·쿠폰",
        "DATA_CRM_AND_DASHBOARD": "데이터·CRM·대시보드",
        "WEB_SAAS_SERVICE_PLANNING": "웹/SaaS·정보화 기획·구축",
    }
    for f in families:
        usable_showda.append(fam_labels.get(f, f))

    new_dev: list[str] = []
    partner_scope: list[str] = []
    if primary == "CUSTOM_BUILD_SERVICE" or "CUSTOM_BUILD_SERVICE" in secondary:
        new_dev.append("과업 명세 기준 맞춤 시스템·플랫폼 구축/고도화")
    if primary == "QRPICK_DIRECT":
        new_dev.append("표준 기능 중심, 연동·브랜딩만 추가될 수 있음")
    if primary == "PARTNER_CONSORTIUM" or partner_hits:
        partner_scope.extend(partner_hits[:6] or ["전문 산업·하드웨어 파트너"])
    if primary == "SALES_LEAD" or action_queue == "SALES_OUTREACH":
        new_dev.append("제품개발보다 참가·노출·리드 확보 우선")

    asset_fit_path = primary
    commercialization_path = primary

    return {
        "asset_fit_path": asset_fit_path,
        "primary_asset_fit_path": primary,
        "secondary_asset_fit_paths": secondary,
        "commercialization_path": commercialization_path,
        "matched_asset_families": families,
        "fit_confidence": fit_confidence,
        "fit_evidence": fit_evidence,
        "evidence_source": evidence_source,
        "opportunity_type": opportunity_type,
        "action_queue": action_queue,
        "recommended_next_action": recommended,
        "next_action": recommended,
        "asset_fit_reasons": fit_evidence,
        "usable_qrpick_features": usable_qrpick,
        "usable_showda_assets": usable_showda,
        "new_development_scope": new_dev,
        "partner_required_scope": partner_scope,
        "opportunity_kind": opportunity_kind,
        "has_sw_ops_role": has_sw_ops_role,
        "strong_low_fit_candidate": bool(
            industrial_core and not has_sw_ops_role and not build_hits and not exhibition_sales and not families
        ),
        "detail_floor_hit": bool(
            matched_groups & set(rules.get("detail_review_floor_groups") or [])
            or families
            or direct_hits
            or build_hits
            or exhibition_sales
        ),
        "family_evidence": family_evidence,
        "detail_verification_status": detail_verification_status,
        "actionability_verified": actionability_verified,
        "actionability_gate_reasons": actionability_gate_reasons,
        "blocking_unknowns": blocking_unknowns,
        "action_promotion_source": promotion_source,
        "provisional_action_queue": provisional_queue,
        "soft_company_unknowns": soft_company_unknowns,
    }


def out_deadline_ok(rec: dict[str, Any], expired_flag: bool) -> bool:
    if expired_flag:
        return False
    return True
