"""Score computation from filter-rules.yaml (no LLM)."""
from __future__ import annotations

import re
from typing import Any

from app.normalizers.text_utils import haystack

HIGH_SIGNAL_GROUPS = (
    "core_mice",
    "tourism_extension",
    "program_value",
    "ops_infra",
    "event_types",
)


def _keyword_in_text(text: str, keyword: str, ascii_boundary: set[str]) -> bool:
    if not keyword:
        return False
    needle = keyword.casefold()
    # Short ASCII tokens: require word-ish boundaries to avoid Automechanika → AI
    if keyword in ascii_boundary or (keyword.isascii() and len(keyword) <= 4 and keyword.isalnum()):
        pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])"
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    return needle in text


def _find_hits(text: str, keywords: list[str], ascii_boundary: set[str]) -> list[str]:
    hits = []
    for kw in keywords:
        if _keyword_in_text(text, kw, ascii_boundary):
            hits.append(kw)
    return hits


def _group_points(hits: list[str], points_per_hit: int, max_points: int) -> tuple[int, list[str]]:
    if not hits:
        return 0, []
    uniq = list(dict.fromkeys(hits))
    pts = min(len(uniq) * points_per_hit, max_points)
    return pts, uniq


def score_opportunity(rec: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    """Return score breakdown and matched keyword groups."""
    text = haystack(
        rec.get("title"),
        rec.get("program"),
        rec.get("category"),
        rec.get("organization"),
    )
    # Tourism org names (e.g. 문화체육관광부) must not alone create tourism_extension hits
    text_no_org = haystack(
        rec.get("title"),
        rec.get("program"),
        rec.get("category"),
    )
    signals = rules.get("positive_signals") or {}
    scoring = rules.get("scoring") or {}
    weak_alone = {w.casefold() for w in (rules.get("weak_alone_words") or [])}
    ascii_boundary = set(rules.get("ascii_word_boundary_keywords") or [])

    breakdown: dict[str, Any] = {}
    positive_reasons: list[str] = []
    matched_groups: set[str] = set()
    total_bonus = 0

    for group, keywords in signals.items():
        cfg = scoring.get(group) or {}
        pph = int(cfg.get("points_per_hit", 0))
        cap = int(cfg.get("max_points", 0))
        search_text = text_no_org if group == "tourism_extension" else text
        hits = _find_hits(search_text, keywords, ascii_boundary)

        if group in ("core_mice", "technology") and hits:
            strong = [h for h in hits if h.casefold() not in weak_alone]
            if group == "core_mice" and not strong:
                hits = []

        pts, used = _group_points(hits, pph, cap)
        breakdown[group] = {"points": pts, "hits": used}
        if pts > 0 and used:
            matched_groups.add(group)
            positive_reasons.append(f"{group} 신호 확인: {', '.join(used[:6])}")
            total_bonus += pts

    # Combination bonus for co-occurring high-value groups
    configured_high = tuple(rules.get("high_signal_groups") or HIGH_SIGNAL_GROUPS)
    high_hits = [g for g in configured_high if g in matched_groups]
    if len(high_hits) >= 3:
        combo = int(scoring.get("combo_three_high_groups", 0))
        if combo:
            total_bonus += combo
            positive_reasons.append(
                f"고가치 신호 그룹 결합 가점 (+{combo}): {', '.join(high_hits)}"
            )
    elif len(high_hits) >= 2:
        combo = int(scoring.get("combo_two_high_groups", 0))
        if combo:
            total_bonus += combo
            positive_reasons.append(
                f"고가치 신호 그룹 결합 가점 (+{combo}): {', '.join(high_hits)}"
            )

    penalties_cfg = rules.get("penalties") or {}
    neg_signals = rules.get("negative_signals") or {}
    negative_reasons: list[str] = []
    penalty_total = 0
    penalty_flags: dict[str, bool] = {}

    for pname, keywords in neg_signals.items():
        hits = _find_hits(text, keywords, ascii_boundary)
        if not hits:
            continue
        pen_key = "strong_domain_mismatch" if pname == "strong_domain" else pname
        pen = penalties_cfg.get(pen_key) or {}
        pts = int(pen.get("points", 0))

        if pname == "strong_domain":
            exclusive_markers = [m.casefold() for m in (rules.get("domain_exclusive_markers") or [])]
            exclusive_in_title = any(m in (rec.get("title") or "").casefold() for m in exclusive_markers)
            multi_domain = len(hits) >= 2
            has_exclusive = any(m in text for m in exclusive_markers) or exclusive_in_title or multi_domain
            role_override = _find_hits(
                text_no_org,
                rules.get("domain_role_override_signals") or [],
                ascii_boundary,
            )
            has_sw_ops = bool(
                role_override
                or breakdown.get("event_types", {}).get("points")
                or breakdown.get("ops_infra", {}).get("points")
                or breakdown.get("core_mice", {}).get("points")
                or breakdown.get("tourism_extension", {}).get("points")
                or breakdown.get("service_build", {}).get("points")
                or breakdown.get("technology", {}).get("points")
            )
            # Industry label alone never drives strong low-fit when SW/ops/event role exists
            if has_sw_ops:
                negative_reasons.append(
                    f"산업 키워드({', '.join(hits[:3])}) 있으나 행사·플랫폼·운영·데이터 역할 신호 공존 — 제외하지 않음"
                )
                penalty_flags["soft_domain"] = True
                continue
            program_industrial = any(
                x in text
                for x in ("오픈이노베이션", "open innovation", "실증", "기술개발", "r&d", "연구개발")
            )
            if has_exclusive or program_industrial:
                # Soft penalty only; status engine requires 4-condition gate for LOW_FIT
                penalty_total += pts
                penalty_flags[pen_key] = True
                negative_reasons.append(
                    f"산업특화·전문기술 산출물 가능성: {', '.join(hits[:5])}"
                    + (" (배타적 맥락)" if has_exclusive else "")
                )
            else:
                negative_reasons.append(
                    f"산업 키워드 언급({', '.join(hits[:3])}) — 단독 제외하지 않음, 상세 확인"
                )
                penalty_flags["soft_domain"] = True
            continue

        if pname == "trainee_individual":
            eduish = any(
                x in text
                for x in ("교육생", "수강생", "부트캠프", "연수생", "개인 참가자", "교육")
            )
            if any(x in text for x in ("전시", "부스", "박람회", "상담회", "참가기업")):
                if not eduish:
                    continue
            if not eduish and any("참가자 모집" == h or "참가자 모집" in h for h in hits) and "교육" not in text:
                continue
            penalty_total += pts
            penalty_flags[pen_key] = True
            negative_reasons.append(f"교육생·개인참가 중심 신호: {', '.join(hits[:4])}")
            continue

        if pname == "space_only":
            has_value = (breakdown.get("program_value") or {}).get("points", 0) > 0
            has_mice = (breakdown.get("core_mice") or {}).get("points", 0) > 0
            if has_value or has_mice:
                negative_reasons.append(
                    f"입주·공간 키워드 있으나 다른 사업신호 공존: {', '.join(hits[:3])}"
                )
                continue
            penalty_total += pts
            penalty_flags[pen_key] = True
            negative_reasons.append(f"입주공간 중심 신호: {', '.join(hits[:4])}")
            continue

        if pname == "mentoring_only":
            has_value = (breakdown.get("program_value") or {}).get("points", 0) > 0
            if has_value:
                continue
            if any(x in text for x in ("멘토링", "컨설팅", "자문")):
                penalty_total += pts
                penalty_flags[pen_key] = True
                negative_reasons.append(f"멘토링·컨설팅 중심 신호: {', '.join(hits[:4])}")
            continue

        if pname in ("pre_startup_only", "student_only"):
            exclusive = any(x in text for x in ("만", "전용", "예비창업자", "대학생"))
            if exclusive or hits:
                penalty_total += pts
                penalty_flags[pen_key] = True
                label = "예비창업자 전용" if pname == "pre_startup_only" else "대학생 전용"
                negative_reasons.append(f"{label} 신호: {', '.join(hits[:4])}")
            continue

        penalty_total += pts
        penalty_flags[pen_key] = True
        negative_reasons.append(f"{pname}: {', '.join(hits[:4])}")

    base = int(rules.get("base_score", 30))
    score = max(0, min(100, base + total_bonus + penalty_total))

    return {
        "score": score,
        "base": base,
        "bonus": total_bonus,
        "penalty": penalty_total,
        "breakdown": breakdown,
        "matched_groups": sorted(matched_groups),
        "positive_reasons": positive_reasons,
        "negative_reasons": negative_reasons,
        "penalty_flags": penalty_flags,
    }
