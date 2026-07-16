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


def run_g2b_summary(
    *,
    procurements_path: Path,
    report_dir: Path,
    link_stats: dict | None = None,
    collect_manifest: dict | None = None,
    normalize_stats: dict | None = None,
    run_day: str | None = None,
) -> dict:
    run_day = run_day or date.today().isoformat()
    ensure_dir(report_dir)
    rows = read_jsonl(procurements_path) if procurements_path.exists() else []

    write_mapped_csv_bom(report_dir / "g2b-mice-procurements.csv", PROCUREMENT_COLUMNS, rows)
    queue = [r for r in rows if r.get("sales_priority") in {"P0", "P1", "P2"}]
    write_mapped_csv_bom(report_dir / "g2b-mice-sales-queue.csv", SALES_QUEUE_COLUMNS, queue)

    direct = [r for r in rows if is_direct_bid_candidate(r)]
    consortium = [r for r in rows if is_consortium_candidate(r)]
    partner = [r for r in rows if is_solution_partner_candidate(r)]
    write_mapped_csv_bom(report_dir / "g2b-direct-bid-opportunities.csv", ROUTE_COLUMNS, direct)
    write_mapped_csv_bom(report_dir / "g2b-consortium-opportunities.csv", ROUTE_COLUMNS, consortium)
    write_mapped_csv_bom(report_dir / "g2b-solution-partner-opportunities.csv", ROUTE_COLUMNS, partner)

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
        f"- procurements: **{len(rows)}**",
        f"- direct / consortium / partner: **{counts['direct']}** / **{counts['consortium']}** / **{counts['partner']}**",
        f"- award outreach / bid partner / next cycle: **{counts['award_outreach']}** / **{counts['bid_partner']}** / **{counts['next_cycle']}**",
        f"- sales queue (P0–P2): **{counts['queue']}**",
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
    args = ap.parse_args(argv)
    stats = run_g2b_summary(
        procurements_path=Path(args.procurements),
        report_dir=Path(args.report_dir),
        run_day=args.today or date.today().isoformat(),
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
