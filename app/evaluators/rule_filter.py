"""Rule-based first-pass status + asset-fit + action queues (no LLM)."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any

from app.evaluators.asset_fit import assess_asset_fit
from app.evaluators.scoring import score_opportunity
from app.normalizers.date_utils import is_expired as deadline_expired
from app.normalizers.text_utils import haystack


ASSET_FIELDS = (
    "asset_fit_path",
    "primary_asset_fit_path",
    "secondary_asset_fit_paths",
    "commercialization_path",
    "matched_asset_families",
    "fit_confidence",
    "fit_evidence",
    "evidence_source",
    "opportunity_type",
    "action_queue",
    "recommended_next_action",
    "next_action",
    "asset_fit_reasons",
    "usable_qrpick_features",
    "usable_showda_assets",
    "new_development_scope",
    "partner_required_scope",
    "opportunity_kind",
    "detail_verification_status",
    "actionability_verified",
    "actionability_gate_reasons",
    "blocking_unknowns",
    "action_promotion_source",
    "provisional_action_queue",
)


def _status_from_queue(action_queue: str, score: int, path: str) -> str:
    """Map action queue to legacy first_pass_status for compatibility."""
    if action_queue == "CLOSED":
        return "EXPIRED"
    if action_queue == "ACTION_NOW":
        return "HIGH_PRIORITY" if score >= 55 or path in ("QRPICK_DIRECT", "CUSTOM_BUILD_SERVICE", "QRPICK_EXTENSION") else "REVIEW"
    if action_queue == "SALES_OUTREACH":
        return "REVIEW"
    if action_queue == "QUALIFICATION_CHECK":
        return "DETAIL_REVIEW"
    if action_queue == "WATCHLIST":
        return "DETAIL_REVIEW" if score < 50 else "REVIEW"
    if action_queue == "NO_ACTION":
        return "LOW_FIT"
    return "DETAIL_REVIEW"


def apply_first_pass(
    rec: dict[str, Any],
    rules: dict[str, Any],
    profile: dict[str, Any] | None = None,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    out = deepcopy(rec)
    today = today or date.today()
    profile = profile or {}
    review_reasons: list[str] = []
    needs_detail = False

    if not out.get("title") or not out.get("source"):
        out["first_pass_status"] = "UNKNOWN"
        out["first_pass_score"] = 0
        out["positive_reasons"] = []
        out["negative_reasons"] = ["필수 필드 부족(title/source)"]
        out["review_reasons"] = ["파싱·정규화 데이터 부족"]
        out["needs_detail_review"] = True
        out["asset_fit_path"] = "NO_REALISTIC_PATH"
        out["primary_asset_fit_path"] = "NO_REALISTIC_PATH"
        out["secondary_asset_fit_paths"] = []
        out["matched_asset_families"] = []
        out["fit_confidence"] = "NONE"
        out["fit_evidence"] = ["필수 필드 부족"]
        out["evidence_source"] = "missing"
        out["opportunity_type"] = "OTHER"
        out["action_queue"] = "NO_ACTION"
        out["recommended_next_action"] = "원본 데이터 오류 확인"
        out["next_action"] = out["recommended_next_action"]
        return out

    expired = deadline_expired(out.get("deadline"), today=today)
    scored = score_opportunity(out, rules)
    fit = assess_asset_fit(out, rules, profile, scored, is_expired=expired)
    for k in ASSET_FIELDS:
        if k in fit:
            out[k] = fit[k]

    score = scored["score"]
    pos = list(scored["positive_reasons"]) + list(fit.get("fit_evidence") or [])
    neg = list(scored["negative_reasons"])

    company = profile.get("company") or {}
    if str(company.get("verification_status", "")).upper() == "INTERNAL_COMPANY_PROFILE_ONLY":
        review_reasons.append(
            "회사정보(설립일·소재지·대표)는 내부 프로필만 반영 — 사업자등록증·등기부 검증 전이라 공식 자격판정에 사용하지 않음"
        )
    if str(company.get("headquarters_region", "TODO")).upper() in ("TODO", "UNKNOWN", ""):
        review_reasons.append("회사 소재지 미확정 — 지역요건 공식 판정 불가")
        needs_detail = True

    status = _status_from_queue(fit["action_queue"], score, fit["primary_asset_fit_path"])

    # Soft override notes
    aq = fit["action_queue"]
    if aq == "ACTION_NOW":
        review_reasons.append(f"행동대기열 ACTION_NOW — 경로 {fit['primary_asset_fit_path']}")
        needs_detail = True
    elif aq == "QUALIFICATION_CHECK":
        review_reasons.append("행동대기열 QUALIFICATION_CHECK — 자격·과제 상세 확인")
        needs_detail = True
    elif aq == "SALES_OUTREACH":
        review_reasons.append("행동대기열 SALES_OUTREACH — 영업·참가 효익 확인")
        needs_detail = True
    elif aq == "WATCHLIST":
        review_reasons.append("행동대기열 WATCHLIST — 관찰(즉시 실행 아님)")
    elif aq == "NO_ACTION":
        review_reasons.append("행동대기열 NO_ACTION — 우선 검토 제외")
    elif aq == "CLOSED":
        review_reasons.append("마감 종료")
        neg = neg + [f"마감일 {out.get('deadline')} 이 실행일 {today.isoformat()} 이전"]

    # Education / trainee penalty alignment
    flags = scored.get("penalty_flags") or {}
    if flags.get("trainee_individual") and aq != "CLOSED":
        if aq not in ("NO_ACTION",):
            # keep assess decision; just annotate
            review_reasons.append("교육생·개인참가 신호 있음")

    out["first_pass_status"] = status
    out["first_pass_score"] = score
    out["positive_reasons"] = list(dict.fromkeys(pos))
    out["negative_reasons"] = neg
    out["review_reasons"] = list(dict.fromkeys(review_reasons))
    out["needs_detail_review"] = bool(
        needs_detail or aq in ("ACTION_NOW", "QUALIFICATION_CHECK", "SALES_OUTREACH")
    )
    return out


def apply_first_pass_batch(
    records: list[dict[str, Any]],
    rules: dict[str, Any],
    profile: dict[str, Any] | None = None,
    *,
    today: date | None = None,
) -> list[dict[str, Any]]:
    return [apply_first_pass(r, rules, profile, today=today) for r in records]
