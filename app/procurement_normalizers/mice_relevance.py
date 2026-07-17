"""MICE / QRPick relevance scoring — separate from procurement record preservation."""
from __future__ import annotations

from typing import Any


# Strong: event ops / registration / platform task evidence (not notice-title hardcodes).
STRONG_SIGNALS: tuple[str, ...] = (
    "행사 운영",
    "행사운영",
    "국제회의",
    "국제행사",
    "컨벤션",
    "컨퍼런스",
    "포럼",
    "세미나",
    "심포지엄",
    "학술대회",
    "박람회",
    "전시회",
    "상담회",
    "비즈니스 매칭",
    "비즈매칭",
    "투자상담회",
    "수출상담회",
    "구매상담회",
    "참가자 등록",
    "참가등록",
    "사전등록",
    "현장등록",
    "체크인",
    "QR 체크인",
    "명찰",
    "배지",
    "비표",
    "행사 홈페이지",
    "행사홈페이지",
    "세션 운영",
    "세션운영",
    "행사 운영시스템",
    "행사운영시스템",
    "참가자 관리",
    "참가자관리",
    "참가자 DB",
    "참가자DB",
    "현장 운영",
    "현장운영",
    "행사 대행",
    "행사대행",
    "페스티벌",
    "페스타",
)

# Strong only when paired with an event-domain token (avoids 회계 '운영 대행').
CONDITIONAL_STRONG: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "운영 대행",
        (
            "행사",
            "박람",
            "전시",
            "포럼",
            "회의",
            "컨벤션",
            "페스타",
            "페스티벌",
            "축제",
            "공연",
            "상담회",
            "세미나",
            "등록",
            "세션",
            "개막",
            "시상식",
            "컨퍼런스",
        ),
    ),
    (
        "운영대행",
        (
            "행사",
            "박람",
            "전시",
            "포럼",
            "회의",
            "컨벤션",
            "페스타",
            "페스티벌",
            "축제",
            "공연",
            "상담회",
            "세미나",
            "등록",
            "세션",
            "개막",
            "시상식",
            "컨퍼런스",
        ),
    ),
)

WEAK_SIGNALS: tuple[str, ...] = (
    "행사",
    "개최",
    "주최",
    "주관",
    "행사장",
    "개최지",
    "참가자",
    "부스",
    "상담",
    "세션",
    "등록",
    "전시",
    "공연",
    "축제",
    "네트워킹",
    "설명회",
    "데모데이",
)

# Domain exclusions / low-signal tasks unrelated to MICE ops.
NEGATIVE_SIGNALS: tuple[tuple[str, str], ...] = (
    ("시설공사", "GENERAL_CONSTRUCTION"),
    ("도로개설", "GENERAL_CONSTRUCTION"),
    ("도시계획도로", "GENERAL_CONSTRUCTION"),
    ("보완설계", "GENERAL_CONSTRUCTION"),
    ("건축공사", "GENERAL_CONSTRUCTION"),
    ("토목공사", "GENERAL_CONSTRUCTION"),
    ("물품구매", "SIMPLE_GOODS_PURCHASE"),
    ("물품 구입", "SIMPLE_GOODS_PURCHASE"),
    ("장비 유지보수", "EQUIPMENT_MAINTENANCE"),
    ("유지보수", "EQUIPMENT_MAINTENANCE"),
    ("사무용품", "OFFICE_SUPPLIES"),
    ("학교급식", "NON_MICE_SERVICE"),
    ("급식 일부위탁", "NON_MICE_SERVICE"),
    ("급식위탁", "NON_MICE_SERVICE"),
    ("회계검증", "NON_MICE_SERVICE"),
    ("정산컨설팅", "NON_MICE_SERVICE"),
    ("조세", "NON_MICE_SERVICE"),
    ("BEPS", "NON_MICE_SERVICE"),
    ("연구용역", "GENERIC_RESEARCH"),
    ("교육용역", "GENERIC_EDUCATION"),
    ("원격) 심사평가", "GENERIC_EDUCATION"),
)


def flatten_search_keywords(config: dict[str, Any] | None) -> list[str]:
    """Legacy helper — search keywords are not used as mice_relevant truth."""
    sk = (config or {}).get("search_keywords") or {}
    out: list[str] = []
    for group in sk.values():
        if isinstance(group, list):
            out.extend(str(x) for x in group if x)
    return list(dict.fromkeys(out))


def _haystack(rec: dict[str, Any]) -> str:
    parts = [
        rec.get("title"),
        rec.get("title_normalized"),
        rec.get("ordering_organization"),
        rec.get("demand_organization"),
        rec.get("contract_method"),
        rec.get("event_name"),
    ]
    return " ".join(str(p) for p in parts if p)


def _find_hits(text: str, signals: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for sig in signals:
        if not sig or sig not in text:
            continue
        # Legal "권리/구상권 행사" is not MICE event ops.
        if sig == "행사 운영":
            if _is_legal_exercise_ops(text):
                continue
        hits.append(sig)
    return hits


def _is_legal_exercise_ops(text: str) -> bool:
    """True when '행사 운영' is a legal/financial exercise phrase, not an event."""
    if "행사 운영" not in text:
        return False
    legal_prefixes = ("구상권 행사", "권리 행사", "권한 행사", "채권 행사", "형성권 행사")
    if any(p in text for p in legal_prefixes):
        return True
    # Pattern: …권 행사 운영 (지침/방안/연구)
    if "권 행사 운영" in text and any(t in text for t in ("지침", "방안", "연구", "개정", "법률")):
        return True
    return False


def assess_mice_relevance(rec: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score MICE/event-ops relevance. Does not decide whether to keep the procurement row."""
    del config  # reserved for future config-driven thresholds
    text = _haystack(rec)
    strong = _find_hits(text, STRONG_SIGNALS)
    for phrase, needs in CONDITIONAL_STRONG:
        if phrase in text and any(n in text for n in needs):
            if phrase not in strong:
                strong.append(phrase)
    weak = _find_hits(text, WEAK_SIGNALS)
    # Avoid double-counting weak tokens already covered by strong phrases.
    weak = [w for w in weak if not any(w in s for s in strong)]

    neg_hits: list[str] = []
    neg_codes: list[str] = []
    for phrase, code in NEGATIVE_SIGNALS:
        if phrase in text:
            neg_hits.append(phrase)
            if code not in neg_codes:
                neg_codes.append(code)

    score = 2 * len(strong) + len(weak) - 3 * len(neg_codes)
    reasons: list[str] = []
    evidence: list[str] = []
    if strong:
        reasons.append("STRONG_EVENT_OPS_SIGNAL")
        evidence.extend(f"strong:{s}" for s in strong[:8])
    if weak:
        reasons.append("WEAK_CONTEXT_SIGNAL")
        evidence.extend(f"weak:{w}" for w in weak[:6])
    if neg_codes:
        reasons.append("NEGATIVE_DOMAIN_SIGNAL")
        evidence.extend(f"negative:{n}" for n in neg_hits[:6])

    # School / road / tax “컨벤션” false friends: strong hit only on 컨벤션 + negative → demote.
    convention_only = strong == ["컨벤션"] or (set(strong) <= {"컨벤션"} and not any(
        s for s in strong if s != "컨벤션"
    ))
    if convention_only and neg_codes:
        score -= 4
        reasons.append("CONVENTION_FALSE_FRIEND")
    if convention_only and not any(
        t in text for t in ("행사", "운영", "개최", "등록", "세션", "박람", "전시", "포럼", "회의")
    ):
        # Bare place/school name without event-ops verbs.
        score -= 2
        reasons.append("CONVENTION_TOKEN_WITHOUT_OPS")

    # Research/education alone without event ops → not relevant.
    if neg_codes and not strong:
        score = min(score, -1)
        reasons.append("NEGATIVE_WITHOUT_STRONG_OPS")

    if score >= 4 and strong:
        confidence = "STRONG"
        relevant = True
    elif score >= 2 and strong:
        confidence = "MEDIUM"
        relevant = True
    elif score >= 1 and (strong or (weak and not neg_codes)):
        confidence = "WEAK"
        # Weak-only or borderline: not sales-grade mice_relevant.
        relevant = bool(strong) and not neg_codes
        if not relevant:
            reasons.append("WEAK_ONLY_OR_CONFLICTED")
    else:
        confidence = "NONE"
        relevant = False
        if not reasons:
            reasons.append("NO_MICE_SIGNAL")

    if relevant and "MICE_TASK_EVIDENCE" not in reasons:
        reasons.insert(0, "MICE_TASK_EVIDENCE")

    return {
        "mice_relevant": relevant,
        "mice_relevance_score": score,
        "mice_relevance_reasons": reasons,
        "mice_relevance_evidence": evidence,
        "mice_relevance_confidence": confidence,
    }


def is_mice_relevant(rec: dict[str, Any], keywords: list[str] | None = None) -> bool:
    """Back-compat boolean API. Ignores flat keyword lists (over-broad)."""
    del keywords
    return bool(assess_mice_relevance(rec).get("mice_relevant"))


_ACTIONABLE_WINDOWS = frozenset(
    {
        "DIRECT_BID_WINDOW",
        "BID_PARTNER_WINDOW",
        "CONSORTIUM_PARTNER_WINDOW",
        "AWARD_WINNER_WINDOW",
        "PRE_REGISTRATION_WINDOW",
        "NEXT_CYCLE_WINDOW",
        "PRE_NOTICE_DIRECT_REVIEW",
        "PRE_NOTICE_PARTNER_OUTREACH",
        "RESEARCH",
    }
)
_NON_ACTION_WINDOWS = frozenset({"NO_ACTION", "CLOSED"})
_PRE_NOTICE_QUEUE_WINDOWS = frozenset(
    {"PRE_NOTICE_DIRECT_REVIEW", "PRE_NOTICE_PARTNER_OUTREACH"}
)


def assess_sales_queue_eligibility(rec: dict[str, Any]) -> dict[str, Any]:
    """Queue eligibility after mice + pre-notice windows are applied.

    Missing proposal deadline alone must NOT yield NO_ACTIONABLE_SALES_WINDOW.
    """
    from app.procurement_normalizers.sales_window import has_qrpick_showda_role_evidence

    exclusions: list[str] = []
    if not rec.get("mice_relevant"):
        exclusions.append("NOT_MICE_RELEVANT")

    routes = [r for r in (rec.get("opportunity_routes") or []) if r]
    windows = [w for w in (rec.get("sales_windows") or []) if w]
    role = has_qrpick_showda_role_evidence(rec)
    action_types = rec.get("sales_action_types") or []

    if not role and rec.get("procurement_stage") == "PRE_NOTICE":
        exclusions.append("NO_ROLE_EVIDENCE")
    if not routes and not (_PRE_NOTICE_QUEUE_WINDOWS.intersection(windows)):
        exclusions.append("NO_OPPORTUNITY_ROUTE")

    # Actionable if pre-notice review/outreach OR classic windows (deadline not required).
    has_pre_notice_path = bool(_PRE_NOTICE_QUEUE_WINDOWS.intersection(windows))
    has_classic_path = bool(set(windows) & (_ACTIONABLE_WINDOWS - {"RESEARCH"}))
    has_research_only = set(windows) <= {"RESEARCH"} or (
        "RESEARCH" in windows and not has_pre_notice_path and not has_classic_path
    )

    if set(windows) <= _NON_ACTION_WINDOWS or not windows:
        # Only when truly no path — not merely missing deadline.
        if not has_pre_notice_path and not routes:
            exclusions.append("NO_ACTIONABLE_SALES_WINDOW")

    if has_research_only and not has_pre_notice_path and not routes:
        # Pure research without routes stays out of sales queue.
        if "NO_ACTIONABLE_SALES_WINDOW" not in exclusions:
            exclusions.append("RESEARCH_ONLY_WITHOUT_ROUTE")

    # Explicit queue membership by action type.
    queueable_types = {"IMMEDIATE_ACTION", "PRE_NOTICE_REVIEW", "PARTNER_OUTREACH"}
    if action_types and not queueable_types.intersection(action_types):
        if "NOT_QUEUEABLE_ACTION_TYPE" not in exclusions:
            exclusions.append("NOT_QUEUEABLE_ACTION_TYPE")

    eligible = bool(rec.get("mice_relevant")) and not any(
        x in exclusions
        for x in (
            "NOT_MICE_RELEVANT",
            "NO_ROLE_EVIDENCE",
            "NO_OPPORTUNITY_ROUTE",
            "NO_ACTIONABLE_SALES_WINDOW",
            "RESEARCH_ONLY_WITHOUT_ROUTE",
            "NOT_QUEUEABLE_ACTION_TYPE",
        )
    )
    # Must have at least one queueable action type or pre-notice window.
    if eligible and not (
        queueable_types.intersection(action_types) or has_pre_notice_path or has_classic_path
    ):
        eligible = False
        exclusions.append("NO_QUEUEABLE_SIGNAL")

    return {
        "sales_queue_eligible": eligible,
        "sales_queue_exclusion_reasons": list(dict.fromkeys(exclusions)),
    }


def apply_mice_and_sales_fields(
    rec: dict[str, Any],
    config: dict[str, Any] | None = None,
    *,
    today: Any = None,
) -> dict[str, Any]:
    from app.procurement_normalizers.pre_notice_priority import assess_pre_notice_priority
    from app.procurement_normalizers.sales_window import (
        apply_pre_notice_sales_windows,
        classify_sales_action_types,
    )

    out = dict(rec)
    out.update(assess_mice_relevance(out, config))
    out = apply_pre_notice_sales_windows(out)
    out.update(classify_sales_action_types(out))
    out.update(assess_sales_queue_eligibility(out))
    out = assess_pre_notice_priority(out, today=today)
    return out
