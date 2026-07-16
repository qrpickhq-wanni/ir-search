"""Match current procurements to previous-year same programs."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.procurement_normalizers.notice_normalizer import strip_year_title


_YEAR_RE = re.compile(r"(19|20)\d{2}")


def _year_of(rec: dict[str, Any]) -> int | None:
    for key in ("announcement_date", "proposal_deadline", "award_date", "contract_date"):
        v = rec.get(key)
        if v and str(v)[:4].isdigit():
            return int(str(v)[:4])
    title = str(rec.get("title") or "")
    m = _YEAR_RE.search(title)
    return int(m.group(0)) if m else None


def _same_org(a: dict[str, Any], b: dict[str, Any]) -> bool:
    for key in ("ordering_organization", "demand_organization"):
        av = str(a.get(key) or "").strip()
        bv = str(b.get(key) or "").strip()
        if av and bv and av == bv:
            return True
    return False


def _core_tokens(title_core: str) -> set[str]:
    parts = [p for p in re.split(r"[\s|/·ㆍ\-_,.()]+", title_core) if len(p) >= 2]
    return set(parts)


def match_previous_cycles(
    current_records: list[dict[str, Any]],
    historical_records: list[dict[str, Any]],
    *,
    today: date | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Annotate current records with previous-cycle matches.

    STRONG: same org + year-stripped title core equality (or containment both ways)
    MEDIUM: same org + high token overlap (>=0.6) and year = current-1
    WEAK: title similarity only → stored but excluded from ops queue
    """
    today = today or date.today()
    current_year = today.year
    stats = {"STRONG": 0, "MEDIUM": 0, "WEAK": 0, "NONE": 0}

    hist_by_year: dict[int, list[dict[str, Any]]] = {}
    for h in historical_records:
        y = _year_of(h)
        if y is None:
            continue
        hist_by_year.setdefault(y, []).append(h)

    out: list[dict[str, Any]] = []
    for rec in current_records:
        y = _year_of(rec) or current_year
        candidates = list(hist_by_year.get(y - 1, []))
        if not candidates:
            candidates = list(hist_by_year.get(y - 2, []))  # biennial / missing prior year only
        best = None
        best_conf = "NONE"
        core = strip_year_title(rec.get("title"))
        core_tokens = _core_tokens(core)

        for h in candidates:
            h_core = strip_year_title(h.get("title"))
            same_org = _same_org(rec, h)
            if same_org and core and h_core and (core == h_core or core in h_core or h_core in core):
                conf = "STRONG"
            elif same_org and core_tokens:
                h_tokens = _core_tokens(h_core)
                if not h_tokens:
                    continue
                overlap = len(core_tokens & h_tokens) / max(1, len(core_tokens | h_tokens))
                conf = "MEDIUM" if overlap >= 0.6 else "WEAK"
            elif core and h_core and (core == h_core):
                conf = "WEAK"
            else:
                continue
            rank = {"STRONG": 3, "MEDIUM": 2, "WEAK": 1, "NONE": 0}
            if rank[conf] > rank[best_conf]:
                best_conf = conf
                best = h

        annotated = dict(rec)
        annotated["previous_cycle_confidence"] = best_conf
        if best and best_conf != "NONE":
            annotated["matched_previous_procurement_ids"] = [best.get("procurement_id")]
            annotated["previous_awardees"] = list(best.get("awardee_organizations") or [])
            annotated["previous_cycle_summary"] = {
                "previous_notice_number": best.get("notice_number"),
                "previous_proposal_deadline": best.get("proposal_deadline"),
                "previous_award_date": best.get("award_date"),
                "previous_awardees": list(best.get("awardee_organizations") or []),
                "previous_contract_amount": best.get("contract_amount"),
                "previous_title": best.get("title"),
                "confidence": best_conf,
            }
            stats[best_conf] += 1
        else:
            annotated["matched_previous_procurement_ids"] = []
            annotated["previous_awardees"] = []
            annotated["previous_cycle_summary"] = {}
            stats["NONE"] += 1
        out.append(annotated)
    return out, stats
