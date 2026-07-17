"""Write G2B MICE procurement sales reports (UTF-8 BOM CSVs + markdown)."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluators.bid_assessment import (
    is_consortium_candidate,
    is_direct_bid_candidate,
    is_solution_partner_candidate,
)
from app.io_utils import ensure_dir, project_root, read_jsonl, write_mapped_csv_bom
from app.procurement_normalizers.pre_notice_priority import priority_sort_key


SALES_QUEUE_COLUMNS = [
    ("영업우선순위", "sales_priority"),
    ("영업가능시점", "sales_windows"),
    ("기회경로", "opportunity_routes"),
    ("대표경로", "primary_route"),
    ("현재조달단계", "procurement_stage"),
    ("사업명", "title"),
    ("발주기관", "ordering_organization"),
    ("수요기관", "demand_organization"),
    ("공고번호", "notice_number"),
    ("공고일", "announcement_date"),
    ("제안마감일", "proposal_deadline"),
    ("마감까지남은일수", "days_to_deadline"),
    ("낙찰일", "award_date"),
    ("낙찰기업", "awardee_organizations"),
    ("계약일", "contract_date"),
    ("계약금액", "contract_amount"),
    ("행사명", "event_name"),
    ("행사일", "event_date"),
    ("행사까지남은일수", "days_to_event"),
    ("등록오픈상태", "registration_open_status"),
    ("전년도동일사업", "previous_cycle_confidence"),
    ("전년도낙찰기업", "previous_awardees"),
    ("QRPick적합서비스", "direct_bid_fit_path"),
    ("입찰자격상태", "eligibility_status"),
    ("차단요인", "blocking_unknowns"),
    ("권장다음행동", "recommended_next_action"),
    ("공개연락처", "public_contact_phone"),
    ("공개이메일", "public_contact_email"),
    ("원문URL", "url"),
]

PROCUREMENT_COLUMNS = [
    ("procurement_id", "procurement_id"),
    ("lifecycle_group_id", "lifecycle_group_id"),
    ("stage", "procurement_stage"),
    ("title", "title"),
    ("notice_number", "notice_number"),
    ("ordering_organization", "ordering_organization"),
    ("demand_organization", "demand_organization"),
    ("proposal_deadline", "proposal_deadline"),
    ("award_date", "award_date"),
    ("awardee_organizations", "awardee_organizations"),
    ("contract_amount", "contract_amount"),
    ("opportunity_routes", "opportunity_routes"),
    ("sales_windows", "sales_windows"),
    ("sales_priority", "sales_priority"),
    ("url", "url"),
]

ROUTE_COLUMNS = [
    ("데이터범위", "source_scope"),
    ("기회경로", "opportunity_routes"),
    ("대표경로", "primary_route"),
    ("입찰판정", "bid_go_no_go"),
    ("적합경로", "direct_bid_fit_path"),
    ("준비상태", "bid_participation_readiness"),
    ("자격상태", "eligibility_status"),
    ("사업명", "title"),
    ("발주기관", "ordering_organization"),
    ("공고번호", "notice_number"),
    ("제안마감일", "proposal_deadline"),
    ("남은일수", "days_to_deadline"),
    ("영업창", "sales_windows"),
    ("우선순위", "sales_priority"),
    ("권장행동", "recommended_next_action"),
    ("원문URL", "url"),
]

PRE_NOTICE_REVIEW_COLUMNS = [
    ("사업명", "title"),
    ("사전규격번호", "notice_number"),
    ("발주기관", "ordering_organization"),
    ("공개일", "announcement_date"),
    ("배정예산", "estimated_amount"),
    ("MICE적합근거", "mice_relevance_evidence"),
    ("직접입찰경로", "direct_route_flag"),
    ("파트너경로", "partner_route_flag"),
    ("QRPickShowda수행가능범위", "qrpick_showda_delivery_scope"),
    ("미확인자격조건", "blocking_unknowns"),
    ("권장다음행동", "recommended_next_action"),
    ("본공고추적필요여부", "track_formal_notice"),
    ("원문URL", "url"),
]

PRE_NOTICE_PRIORITY_COLUMNS = [
    ("우선순위", "pre_notice_priority"),
    ("주기회경로", "primary_opportunity_route"),
    ("보조경로", "secondary_opportunity_routes"),
    ("사업명", "title"),
    ("사전규격번호", "notice_number"),
    ("발주기관", "ordering_organization"),
    ("공개일", "announcement_date"),
    ("배정예산", "estimated_amount"),
    ("QRPick·Showda 역할", "priority_role_scope"),
    ("MICE 적합 근거", "mice_relevance_evidence"),
    ("직접입찰 근거", "direct_bid_evidence"),
    ("파트너 참여 근거", "partner_participation_evidence"),
    ("미확인 사항", "review_blocking_unknowns"),
    ("권장 다음 행동", "recommended_review_action"),
    ("연락경로 확인 여부", "contact_path_verified"),
    ("검토기한", "review_deadline"),
    ("경로선택근거", "route_selection_reasons"),
    ("원문 URL", "url"),
]


def _enrich_pre_notice_row(r: dict[str, Any]) -> dict[str, Any]:
    out = dict(r)
    routes = out.get("opportunity_routes") or []
    out["direct_route_flag"] = "Y" if "DIRECT_PRIME_BID" in routes else "N"
    out["partner_route_flag"] = (
        "Y"
        if ("CONSORTIUM_BID" in routes or "SUBCONTRACT_OR_SOLUTION_PARTNER" in routes)
        else "N"
    )
    if out.get("track_formal_notice") is None:
        out["track_formal_notice"] = "Y"
    elif isinstance(out.get("track_formal_notice"), bool):
        out["track_formal_notice"] = "Y" if out["track_formal_notice"] else "N"
    scope = out.get("qrpick_showda_delivery_scope") or out.get("usable_qrpick_features") or []
    if not scope:
        scope = out.get("mice_relevance_evidence") or []
    out["qrpick_showda_delivery_scope"] = scope
    return out


def _dedupe_pre_notice_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse direct/partner overlap into one procurement row."""
    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    for index, row in enumerate(sorted(rows, key=priority_sort_key)):
        stable_id = row.get("notice_number") or row.get("procurement_id") or row.get("url")
        title = str(row.get("title") or "")
        organization = str(row.get("ordering_organization") or "")
        if stable_id:
            key = ("id", str(stable_id))
        elif title or organization:
            key = ("fallback", title, organization)
        else:
            key = ("row", str(index))
        if key not in merged:
            merged[key] = dict(row)
            continue
        current = merged[key]
        routes = list(
            dict.fromkeys(
                (current.get("opportunity_routes") or [])
                + (row.get("opportunity_routes") or [])
                + (current.get("secondary_opportunity_routes") or [])
                + (row.get("secondary_opportunity_routes") or [])
            )
        )
        primary = current.get("primary_opportunity_route") or row.get(
            "primary_opportunity_route"
        )
        current["opportunity_routes"] = routes
        current["primary_opportunity_route"] = primary
        current["secondary_opportunity_routes"] = [route for route in routes if route != primary]
        current["route_selection_reasons"] = list(
            dict.fromkeys(
                (current.get("route_selection_reasons") or [])
                + (row.get("route_selection_reasons") or [])
            )
        )
    return sorted(merged.values(), key=priority_sort_key)


def run_g2b_summary(
    *,
    procurements_path: Path,
    report_dir: Path,
    link_stats: dict | None = None,
    collect_manifest: dict | None = None,
    normalize_stats: dict | None = None,
    run_day: str | None = None,
    top_n: int = 30,
) -> dict:
    run_day = run_day or date.today().isoformat()
    ensure_dir(report_dir)
    rows = read_jsonl(procurements_path) if procurements_path.exists() else []

    write_mapped_csv_bom(report_dir / "g2b-mice-procurements.csv", PROCUREMENT_COLUMNS, rows)
    queue = [r for r in rows if r.get("sales_queue_eligible")]
    if not queue:
        if not any("sales_queue_eligible" in r for r in rows):
            queue = [
                r
                for r in rows
                if r.get("mice_relevant") and r.get("sales_priority") in {"P0", "P1", "P2"}
            ]
    write_mapped_csv_bom(report_dir / "g2b-mice-sales-queue.csv", SALES_QUEUE_COLUMNS, queue)

    direct = [r for r in rows if r.get("mice_relevant") and is_direct_bid_candidate(r)]
    consortium = [r for r in rows if r.get("mice_relevant") and is_consortium_candidate(r)]
    partner = [r for r in rows if r.get("mice_relevant") and is_solution_partner_candidate(r)]
    write_mapped_csv_bom(report_dir / "g2b-direct-bid-opportunities.csv", ROUTE_COLUMNS, direct)
    write_mapped_csv_bom(report_dir / "g2b-consortium-opportunities.csv", ROUTE_COLUMNS, consortium)
    write_mapped_csv_bom(report_dir / "g2b-solution-partner-opportunities.csv", ROUTE_COLUMNS, partner)

    pre_direct = [
        _enrich_pre_notice_row(r)
        for r in rows
        if "PRE_NOTICE_DIRECT_REVIEW" in (r.get("sales_windows") or [])
    ]
    pre_partner = [
        _enrich_pre_notice_row(r)
        for r in rows
        if "PRE_NOTICE_PARTNER_OUTREACH" in (r.get("sales_windows") or [])
    ]
    write_mapped_csv_bom(
        report_dir / "g2b-pre-notice-direct-review.csv", PRE_NOTICE_REVIEW_COLUMNS, pre_direct
    )
    write_mapped_csv_bom(
        report_dir / "g2b-pre-notice-partner-outreach.csv", PRE_NOTICE_REVIEW_COLUMNS, pre_partner
    )
    all_pre_notice_candidates = _dedupe_pre_notice_candidates(
        [
            r
            for r in rows
            if r.get("procurement_stage") == "PRE_NOTICE"
            and r.get("sales_queue_eligible")
            and r.get("pre_notice_priority") != "NO_ACTION"
        ]
    )
    priority_queue = all_pre_notice_candidates[: max(0, top_n)]
    write_mapped_csv_bom(
        report_dir / "g2b-pre-notice-priority-queue.csv",
        PRE_NOTICE_PRIORITY_COLUMNS,
        priority_queue,
        preserve_order=True,
    )
    write_mapped_csv_bom(
        report_dir / "g2b-pre-notice-top30.csv",
        PRE_NOTICE_PRIORITY_COLUMNS,
        priority_queue,
        preserve_order=True,
    )
    write_mapped_csv_bom(
        report_dir / "g2b-pre-notice-all-candidates.csv",
        PRE_NOTICE_PRIORITY_COLUMNS,
        all_pre_notice_candidates,
        preserve_order=True,
    )

    award_outreach = [
        r for r in rows if "AWARD_WINNER_WINDOW" in (r.get("sales_windows") or [])
    ]
    bid_partner = [r for r in rows if "BID_PARTNER_WINDOW" in (r.get("sales_windows") or [])]
    next_cycle = [
        r
        for r in rows
        if "NEXT_CYCLE_WINDOW" in (r.get("sales_windows") or [])
        and r.get("previous_cycle_confidence") in {"STRONG", "MEDIUM"}
    ]
    write_mapped_csv_bom(report_dir / "g2b-award-winner-outreach.csv", SALES_QUEUE_COLUMNS, award_outreach)
    write_mapped_csv_bom(report_dir / "g2b-bid-partner-window.csv", SALES_QUEUE_COLUMNS, bid_partner)
    write_mapped_csv_bom(report_dir / "g2b-next-cycle-watch.csv", SALES_QUEUE_COLUMNS, next_cycle)

    md = _build_md(
        run_day=run_day,
        rows=rows,
        link_stats=link_stats or {},
        collect_manifest=collect_manifest or {},
        normalize_stats=normalize_stats or {},
        counts={
            "direct": len(direct),
            "consortium": len(consortium),
            "partner": len(partner),
            "award_outreach": len(award_outreach),
            "bid_partner": len(bid_partner),
            "next_cycle": len(next_cycle),
            "queue": len(queue),
            "pre_direct": len(pre_direct),
            "pre_partner": len(pre_partner),
            "priority_queue": len(priority_queue),
            "all_pre_notice_candidates": len(all_pre_notice_candidates),
        },
    )
    (report_dir / "g2b-lifecycle-summary.md").write_text(md, encoding="utf-8")
    return {
        "report_dir": str(report_dir),
        "procurement_count": len(rows),
        "counts": {
            "direct": len(direct),
            "consortium": len(consortium),
            "partner": len(partner),
            "award_outreach": len(award_outreach),
            "bid_partner": len(bid_partner),
            "next_cycle": len(next_cycle),
            "queue": len(queue),
            "pre_direct": len(pre_direct),
            "pre_partner": len(pre_partner),
            "priority_queue": len(priority_queue),
            "all_pre_notice_candidates": len(all_pre_notice_candidates),
        },
    }


def _build_md(*, run_day, rows, link_stats, collect_manifest, normalize_stats, counts) -> str:
    sw = Counter()
    for r in rows:
        for w in r.get("sales_windows") or []:
            sw[w] += 1
    pr = Counter(r.get("sales_priority") for r in rows)
    routes = Counter()
    for r in rows:
        for rt in r.get("opportunity_routes") or []:
            routes[rt] += 1
    email_n = sum(1 for r in rows if r.get("public_contact_email"))
    phone_n = sum(1 for r in rows if r.get("public_contact_phone"))
    lines = [
        f"# G2B MICE Procurement Lifecycle Summary ({run_day})",
        "",
        "## Collection",
        f"- auth_present: **{collect_manifest.get('auth_present')}**",
        f"- stages: `{json.dumps(collect_manifest.get('stages') or [], ensure_ascii=False)[:500]}...`",
        "",
        "## Normalize",
        f"- {json.dumps(normalize_stats, ensure_ascii=False)}",
        "",
        "## Lifecycle / links",
        f"- {json.dumps(link_stats, ensure_ascii=False)}",
        "",
        "## Counts",
        f"- normalized_total: **{(normalize_stats or {}).get('normalized_total')}**",
        f"- procurement_records_total: **{(link_stats or {}).get('procurement_records_total', len(rows))}**",
        f"- mice_relevant_procurements: **{(link_stats or {}).get('mice_relevant_procurements')}**",
        f"- direct_bid_candidates: **{(link_stats or {}).get('direct_bid_candidates', counts['direct'])}**",
        f"- partner_candidates: **{(link_stats or {}).get('partner_candidates', counts['partner'])}**",
        f"- sales_queue_count: **{(link_stats or {}).get('sales_queue_count', counts['queue'])}**",
        f"- pre_notice_direct_review: **{(link_stats or {}).get('pre_notice_direct_review_count', counts.get('pre_direct'))}**",
        f"- pre_notice_partner_outreach: **{(link_stats or {}).get('pre_notice_partner_outreach_count', counts.get('pre_partner'))}**",
        f"- sales_action_types: `{json.dumps((link_stats or {}).get('sales_action_type_counts') or {}, ensure_ascii=False)}`",
        f"- procurements (file rows): **{len(rows)}**",
        f"- mice_relevance confidence: `{json.dumps((link_stats or {}).get('mice_relevance_confidence_counts') or {}, ensure_ascii=False)}`",
        f"- direct / consortium / partner (report filters): **{counts['direct']}** / **{counts['consortium']}** / **{counts['partner']}**",
        f"- award outreach / bid partner / next cycle: **{counts['award_outreach']}** / **{counts['bid_partner']}** / **{counts['next_cycle']}**",
        f"- sales queue rows written: **{counts['queue']}**",
        "",
        "## sales_windows",
    ]
    for k, v in sw.most_common():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## sales_priority")
    for k, v in pr.most_common():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## opportunity_routes")
    for k, v in routes.most_common():
        lines.append(f"- {k}: {v}")
    lines += [
        "",
        f"- public email: **{email_n}**, public phone: **{phone_n}**",
        "",
        "> CSV files are UTF-8 BOM. source_scope=G2B_OFFICIAL_OPENAPI.",
        "> Without DATA_GO_KR_SERVICE_KEY, collection is PARTIAL_EXPECTED (structure only).",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--procurements", required=True)
    ap.add_argument("--report-dir", required=True)
    ap.add_argument("--today", default=None)
    ap.add_argument("--top-n", type=int, default=30)
    args = ap.parse_args(argv)
    stats = run_g2b_summary(
        procurements_path=Path(args.procurements),
        report_dir=Path(args.report_dir),
        run_day=args.today or date.today().isoformat(),
        top_n=args.top_n,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
