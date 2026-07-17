"""Apply bid assessment + G2B sales window / priority rules."""
from __future__ import annotations

from datetime import date
from typing import Any

from app.evaluators.bid_assessment import assess_bid_opportunity, primary_opportunity_route


def _parse_day(raw: Any) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def apply_sales_windows(
    rec: dict[str, Any],
    *,
    config: dict[str, Any],
    bid_rules: dict[str, Any],
    profile: dict[str, Any] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    out = dict(rec)

    # Bid assessment expects deadline/title/org fields
    if not out.get("deadline"):
        out["deadline"] = out.get("proposal_deadline")
    if out.get("days_to_deadline") is not None:
        out["dday"] = out["days_to_deadline"]
    elif out.get("proposal_deadline"):
        dl = _parse_day(out["proposal_deadline"])
        if dl:
            out["dday"] = (dl - today).days
            out["days_to_deadline"] = out["dday"]

    bid = assess_bid_opportunity(
        out,
        bid_rules,
        profile=profile,
        asset_fit={
            "opportunity_type": "PROCUREMENT_OR_BUILD",
            "matched_asset_families": ["QRPICK_EVENT_OPERATIONS"]
            if _has_qrpick_signal(out)
            else [],
            "usable_qrpick_features": _qrpick_features(out),
        },
        today=today,
    )
    out.update(bid)
    out["source_scope"] = "G2B_OFFICIAL_OPENAPI"
    if out.get("opportunity_routes"):
        out["primary_route"] = primary_opportunity_route(out["opportunity_routes"])

    sw_cfg = config.get("sales_windows") or {}
    windows: list[str] = list(out.get("sales_windows") or [])

    dday = out.get("days_to_deadline")
    if isinstance(dday, int) and dday >= int(sw_cfg.get("direct_bid_min_days_to_deadline", 3)):
        if "DIRECT_PRIME_BID" in (out.get("opportunity_routes") or []):
            if "DIRECT_BID_WINDOW" not in windows:
                windows.append("DIRECT_BID_WINDOW")
        if _has_qrpick_signal(out) and dday >= 0:
            if "BID_PARTNER_WINDOW" not in windows:
                windows.append("BID_PARTNER_WINDOW")
            if "CONSORTIUM_BID" in (out.get("opportunity_routes") or []):
                if "CONSORTIUM_PARTNER_WINDOW" not in windows:
                    windows.append("CONSORTIUM_PARTNER_WINDOW")

    award_day = _parse_day(out.get("award_date"))
    event_day = _parse_day(out.get("event_date"))
    if award_day and out.get("awardee_organizations"):
        days_since_award = (today - award_day).days
        max_award = int(sw_cfg.get("award_winner_days_after_award", 30))
        prep_ok = True
        if event_day:
            out["days_to_event"] = (event_day - today).days
            out["prep_days_award_to_event"] = (event_day - award_day).days
            prep_ok = event_day > today
        if 0 <= days_since_award <= max_award and prep_ok:
            windows.append("AWARD_WINNER_WINDOW")
        if prep_ok and out.get("registration_open_status") in {None, "UNKNOWN", "NOT_FOUND"}:
            min_days = int(sw_cfg.get("pre_registration_min_days_to_event", 45))
            if event_day is None or (event_day - today).days >= min_days:
                windows.append("PRE_REGISTRATION_WINDOW")
        if event_day and 0 <= (event_day - today).days <= int(
            sw_cfg.get("late_event_max_days_to_event", 21)
        ):
            windows.append("LATE_EVENT_WINDOW")

    conf = out.get("previous_cycle_confidence")
    if conf in {"STRONG", "MEDIUM"}:
        if dday is None or (isinstance(dday, int) and dday < 0) or out.get("procurement_stage") in {
            "AWARD_RESULT",
            "CONTRACT_RESULT",
        }:
            windows.append("NEXT_CYCLE_WINDOW")
        elif isinstance(dday, int) and dday > 60:
            windows.append("NEXT_CYCLE_WINDOW")

    if not windows:
        if out.get("bid_assessment_applicable") is False:
            windows.append("NO_ACTION")
        elif isinstance(dday, int) and dday < 0 and not out.get("awardee_organizations"):
            windows.append("CLOSED")
        else:
            windows.append("RESEARCH")

    out["sales_windows"] = list(dict.fromkeys(windows))
    out["sales_priority"] = _priority(out, config, today)
    out["recommended_next_action"] = out.get("recommended_bid_action") or _default_action(out)
    if out.get("system_supplier_status") is None:
        out["system_supplier_status"] = "UNKNOWN"
    if out.get("registration_open_status") is None:
        out["registration_open_status"] = "UNKNOWN"
    blockers = list(out.get("bid_blocking_reasons") or [])
    if out.get("system_supplier_status") == "UNKNOWN":
        blockers.append("system_supplier_unknown")
    if out.get("registration_open_status") == "UNKNOWN":
        blockers.append("registration_open_status_unknown")
    out["blocking_unknowns"] = list(dict.fromkeys(blockers))
    return out


def has_qrpick_showda_role_evidence(rec: dict[str, Any]) -> bool:
    """QRPick/Showda delivery role evidence (not mere event-hosting nouns)."""
    if _has_qrpick_signal(rec) or _qrpick_features(rec):
        return True
    if rec.get("usable_qrpick_features"):
        return True
    families = rec.get("matched_asset_families") or []
    if "QRPICK_EVENT_OPERATIONS" in families:
        return True
    evidence = " ".join(str(x) for x in (rec.get("mice_relevance_evidence") or []))
    role_tokens = (
        "등록",
        "체크인",
        "명찰",
        "배지",
        "홈페이지",
        "운영시스템",
        "매칭",
        "플랫폼",
        "세션 운영",
        "참가자",
        "QR",
    )
    if any(t in evidence for t in role_tokens):
        return True
    text = " ".join(str(rec.get(k) or "") for k in ("title", "title_normalized"))
    ops_role = (
        "행사 운영",
        "행사운영",
        "운영 대행",
        "운영대행",
        "행사 대행",
        "현장 운영",
        "세션 운영",
        "참가자 등록",
        "사전등록",
        "체크인",
        "명찰",
        "배지",
        "행사 홈페이지",
        "운영시스템",
        "비즈니스 매칭",
        "상담 매칭",
    )
    return any(t in text for t in ops_role)


def apply_pre_notice_sales_windows(rec: dict[str, Any]) -> dict[str, Any]:
    """Add PRE_NOTICE review/outreach windows after mice_relevant is known.

    Missing proposal deadline alone must not block these windows.
    Never promotes to ACTION_NOW / GO without detail verification.
    """
    out = dict(rec)
    if out.get("procurement_stage") != "PRE_NOTICE":
        return out
    if not out.get("mice_relevant"):
        return out

    windows = list(out.get("sales_windows") or [])
    routes = out.get("opportunity_routes") or []
    role = has_qrpick_showda_role_evidence(out)
    verified = str(out.get("detail_verification_status") or "").upper() == "VERIFIED"

    if "DIRECT_PRIME_BID" in routes and role:
        if "PRE_NOTICE_DIRECT_REVIEW" not in windows:
            windows.append("PRE_NOTICE_DIRECT_REVIEW")
        # Strip immediate bid windows that require a live deadline.
        windows = [w for w in windows if w not in {"DIRECT_BID_WINDOW"}]
        out["bid_participation_readiness"] = "QUALIFICATION_CHECK"
        if not verified:
            out["bid_go_no_go"] = "UNKNOWN"
            if out.get("eligibility_status") in {None, "VERIFIED_ELIGIBLE"}:
                out["eligibility_status"] = "UNKNOWN_NEEDS_DOCUMENT_REVIEW"
        out["recommended_next_action"] = (
            "사전규격 기준 직접입찰 사전검토 — 과업·자격·역할 확인 후 본공고 추적"
        )
        out["track_formal_notice"] = True

    partner_routes = {"CONSORTIUM_BID", "SUBCONTRACT_OR_SOLUTION_PARTNER"}
    if partner_routes.intersection(routes) and role:
        if "PRE_NOTICE_PARTNER_OUTREACH" not in windows:
            windows.append("PRE_NOTICE_PARTNER_OUTREACH")
        if out.get("recommended_next_action") in {None, "", "문서·자격 추가 확인"} or (
            "PRE_NOTICE_DIRECT_REVIEW" not in windows
        ):
            # Keep direct-review action if both apply; else partner outreach action.
            if "PRE_NOTICE_DIRECT_REVIEW" not in windows:
                out["recommended_next_action"] = (
                    "기획사·PCO 파트너 선제 접촉 — 구성·견적 준비 및 본공고 추적"
                )
        out["track_formal_notice"] = True
        if out.get("bid_participation_readiness") in {None, "NO_BID", "WATCH"}:
            out["bid_participation_readiness"] = "PARTNER_SEARCH"

    # Drop NO_ACTION when we now have a pre-notice path.
    if any(
        w in windows for w in ("PRE_NOTICE_DIRECT_REVIEW", "PRE_NOTICE_PARTNER_OUTREACH")
    ):
        windows = [w for w in windows if w != "NO_ACTION"]

    out["sales_windows"] = list(dict.fromkeys(windows))
    if "PRE_NOTICE_DIRECT_REVIEW" in out["sales_windows"] or "PRE_NOTICE_PARTNER_OUTREACH" in out[
        "sales_windows"
    ]:
        # Pre-notice queues are P2 watch — not immediate bid.
        if out.get("sales_priority") in {None, "P3"}:
            out["sales_priority"] = "P2"
    return out


def classify_sales_action_types(rec: dict[str, Any]) -> dict[str, Any]:
    """Split queue behavior into explicit action types (multi-label)."""
    windows = set(rec.get("sales_windows") or [])
    types: list[str] = []

    immediate = bool(
        windows & {"DIRECT_BID_WINDOW", "AWARD_WINNER_WINDOW"}
        or rec.get("bid_participation_readiness") == "ACTION_NOW"
    )
    if immediate and str(rec.get("detail_verification_status") or "").upper() == "VERIFIED":
        types.append("IMMEDIATE_ACTION")
    elif immediate:
        # Unverified detail cannot be IMMEDIATE_ACTION.
        if "DIRECT_BID_WINDOW" in windows:
            types.append("PRE_NOTICE_REVIEW" if rec.get("procurement_stage") == "PRE_NOTICE" else "RESEARCH")

    if "PRE_NOTICE_DIRECT_REVIEW" in windows:
        types.append("PRE_NOTICE_REVIEW")
    if "PRE_NOTICE_PARTNER_OUTREACH" in windows or "BID_PARTNER_WINDOW" in windows:
        types.append("PARTNER_OUTREACH")
    if "CONSORTIUM_PARTNER_WINDOW" in windows and "PARTNER_OUTREACH" not in types:
        types.append("PARTNER_OUTREACH")

    if not types:
        if windows & {"RESEARCH", "NEXT_CYCLE_WINDOW", "PRE_REGISTRATION_WINDOW"}:
            types.append("RESEARCH")
        elif windows <= {"NO_ACTION", "CLOSED"} or not windows:
            types.append("NO_ACTION")
        else:
            types.append("RESEARCH")

    types = list(dict.fromkeys(types))
    # Primary: prefer immediate → pre review → partner → research → no action
    primary = "NO_ACTION"
    for pref in ("IMMEDIATE_ACTION", "PRE_NOTICE_REVIEW", "PARTNER_OUTREACH", "RESEARCH", "NO_ACTION"):
        if pref in types:
            primary = pref
            break
    return {
        "sales_action_types": types,
        "sales_action_type": primary,
    }


def _has_qrpick_signal(rec: dict[str, Any]) -> bool:
    text = " ".join(str(rec.get(k) or "") for k in ("title", "title_normalized"))
    # Legal exercise phrases are not event-ops role evidence.
    if any(p in text for p in ("구상권 행사", "권리 행사", "권한 행사", "채권 행사")):
        text_for_ops = text
        for p in ("구상권 행사 운영", "권리 행사 운영", "권한 행사 운영", "채권 행사 운영", "권 행사 운영"):
            text_for_ops = text_for_ops.replace(p, " ")
        text = text_for_ops
    keys = (
        "등록",
        "체크인",
        "명찰",
        "배지",
        "발권",
        "매칭",
        "홈페이지",
        "플랫폼",
        "운영시스템",
        "QR",
        "대시보드",
        "CRM",
        "다국어",
        "행사 운영",
        "운영 대행",
        "세션 운영",
        "참가자",
    )
    return any(k in text for k in keys)


def _qrpick_features(rec: dict[str, Any]) -> list[str]:
    text = str(rec.get("title") or "")
    feats = []
    mapping = {
        "등록": "등록",
        "체크인": "체크인",
        "명찰": "명찰",
        "매칭": "매칭",
        "홈페이지": "홈페이지",
        "플랫폼": "플랫폼",
        "QR": "QR",
        "운영시스템": "운영시스템",
        "세션": "세션운영",
    }
    for k, v in mapping.items():
        if k in text:
            feats.append(v)
    return feats


def _priority(rec: dict[str, Any], config: dict[str, Any], today: date) -> str:
    del today
    cfg = config.get("sales_priority") or {}
    windows = set(rec.get("sales_windows") or [])
    dday = rec.get("days_to_deadline")
    if "DIRECT_BID_WINDOW" in windows and isinstance(dday, int):
        if 0 <= dday <= int(cfg.get("P0_days_to_deadline_max", 14)):
            return "P0"
        if dday <= int(cfg.get("P1_days_to_deadline_max", 45)):
            return "P1"
    if "AWARD_WINNER_WINDOW" in windows or "BID_PARTNER_WINDOW" in windows:
        return "P1"
    if "PRE_NOTICE_DIRECT_REVIEW" in windows or "PRE_NOTICE_PARTNER_OUTREACH" in windows:
        return "P2"
    if "PRE_REGISTRATION_WINDOW" in windows or "NEXT_CYCLE_WINDOW" in windows:
        return "P2"
    if "RESEARCH" in windows:
        return "P3"
    return "P3"


def _default_action(rec: dict[str, Any]) -> str:
    windows = rec.get("sales_windows") or []
    if "PRE_NOTICE_DIRECT_REVIEW" in windows:
        return "사전규격 기준 직접입찰 사전검토 — 과업·자격·역할 확인 후 본공고 추적"
    if "PRE_NOTICE_PARTNER_OUTREACH" in windows:
        return "기획사·PCO 파트너 선제 접촉 — 구성·견적 준비 및 본공고 추적"
    if "DIRECT_BID_WINDOW" in windows:
        return "제안요청서 확보 후 직접입찰 자격·역할 검토"
    if "BID_PARTNER_WINDOW" in windows:
        return "입찰 예정사에 QRPick 구성·견적 제안"
    if "AWARD_WINNER_WINDOW" in windows:
        return "낙찰기업 공개연락처로 시스템·운영 공급 제안 (공급사 미정)"
    if "NEXT_CYCLE_WINDOW" in windows:
        return "전년도 동일사업 기준으로 차기 회차 사전 영업 준비"
    if "PRE_REGISTRATION_WINDOW" in windows:
        return "등록·홈페이지 오픈 여부 확인 후 사전등록 제안"
    return "문서·자격 추가 확인"
