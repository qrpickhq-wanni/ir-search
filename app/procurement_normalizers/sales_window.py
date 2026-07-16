"""Apply bid assessment + G2B sales window / priority rules."""
from __future__ import annotations

from datetime import date, datetime
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
        # Before this year's notice or when still early
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

    # Deduplicate preserve order
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


def _has_qrpick_signal(rec: dict[str, Any]) -> bool:
    text = " ".join(
        str(rec.get(k) or "")
        for k in ("title", "title_normalized")
    )
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
    }
    for k, v in mapping.items():
        if k in text:
            feats.append(v)
    return feats


def _priority(rec: dict[str, Any], config: dict[str, Any], today: date) -> str:
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
    if "PRE_REGISTRATION_WINDOW" in windows or "NEXT_CYCLE_WINDOW" in windows:
        return "P2"
    if "RESEARCH" in windows:
        return "P3"
    return "P3"


def _default_action(rec: dict[str, Any]) -> str:
    windows = rec.get("sales_windows") or []
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
