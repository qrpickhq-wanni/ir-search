"""Link G2B lifecycle, previous cycles, MICE events; apply sales windows."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluators.bid_assessment import (
    is_consortium_candidate,
    is_direct_bid_candidate,
    is_solution_partner_candidate,
)
from app.io_utils import ensure_dir, load_yaml, project_root, read_jsonl, write_jsonl
from app.procurement_collectors.g2b_stages import normalize_selected_sources
from app.procurement_normalizers.event_linker import link_events
from app.procurement_normalizers.lifecycle_linker import link_lifecycle
from app.procurement_normalizers.mice_relevance import apply_mice_and_sales_fields
from app.procurement_normalizers.previous_cycle_matcher import match_previous_cycles
from app.procurement_normalizers.sales_window import apply_sales_windows


def _latest_mice_events() -> list[dict]:
    root = project_root() / "data" / "normalized" / "mice"
    if not root.exists():
        return []
    days = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name)
    if not days:
        return []
    path = days[-1] / "events.jsonl"
    if not path.exists():
        # try alternate names
        for cand in days[-1].glob("*.jsonl"):
            return read_jsonl(cand)
        return []
    return read_jsonl(path)


def run_g2b_link(
    *,
    normalized_dir: Path,
    out_dir: Path | None = None,
    today: date | None = None,
    config: dict | None = None,
    selected_sources: list[str] | None = None,
) -> dict:
    today = today or date.today()
    cfg = config or load_yaml(project_root() / "config" / "g2b-mice-lifecycle.yaml")
    bid_rules = load_yaml(project_root() / "config" / "bid-assessment-rules.yaml")
    profile = load_yaml(project_root() / "config" / "qrpick-profile.yaml")
    out_dir = out_dir or ensure_dir(normalized_dir)
    ensure_dir(out_dir)

    stages = normalize_selected_sources(selected_sources)

    def _read_stage(stage: str, fname: str) -> list[dict]:
        if stage not in stages:
            return []
        path = normalized_dir / fname
        return read_jsonl(path) if path.exists() else []

    pre = _read_stage("pre_notice", "pre_notices.jsonl")
    notices = _read_stage("bid_notice", "bid_notices.jsonl")
    awards = _read_stage("award_result", "award_results.jsonl")
    contracts = _read_stage("contract_result", "contract_results.jsonl")

    linked, life_stats = link_lifecycle(notices, awards, contracts, pre_notices=pre)

    # Previous cycle: use awards+contracts+older notices as history pool
    history = [r for r in linked if r.get("procurement_stage") in {"AWARD_RESULT", "CONTRACT_RESULT"}]
    history += notices + awards + contracts
    with_prev, prev_stats = match_previous_cycles(linked, history, today=today)

    events = _latest_mice_events()
    with_events, event_stats = link_events(with_prev, events)

    scored = [
        apply_sales_windows(r, config=cfg, bid_rules=bid_rules, profile=profile, today=today)
        for r in with_events
    ]
    scored = [apply_mice_and_sales_fields(r, cfg, today=today) for r in scored]

    mice_relevant = sum(1 for r in scored if r.get("mice_relevant"))
    sales_queue = [r for r in scored if r.get("sales_queue_eligible")]
    direct_n = sum(1 for r in scored if r.get("mice_relevant") and is_direct_bid_candidate(r))
    partner_n = sum(
        1
        for r in scored
        if r.get("mice_relevant")
        and (is_solution_partner_candidate(r) or is_consortium_candidate(r))
    )
    pre_direct = sum(1 for r in scored if "PRE_NOTICE_DIRECT_REVIEW" in (r.get("sales_windows") or []))
    pre_partner = sum(
        1 for r in scored if "PRE_NOTICE_PARTNER_OUTREACH" in (r.get("sales_windows") or [])
    )
    both_pre = sum(
        1
        for r in scored
        if "PRE_NOTICE_DIRECT_REVIEW" in (r.get("sales_windows") or [])
        and "PRE_NOTICE_PARTNER_OUTREACH" in (r.get("sales_windows") or [])
    )
    action_counts = {
        "IMMEDIATE_ACTION": 0,
        "PRE_NOTICE_REVIEW": 0,
        "PARTNER_OUTREACH": 0,
        "RESEARCH": 0,
        "NO_ACTION": 0,
    }
    for r in scored:
        for t in r.get("sales_action_types") or [r.get("sales_action_type") or "NO_ACTION"]:
            if t in action_counts:
                action_counts[t] += 1

    priority_counts = {
        "P0_DETAIL_REVIEW": 0,
        "P1_PARTNER_OUTREACH": 0,
        "P2_QUALIFICATION_RESEARCH": 0,
        "P3_WATCH": 0,
        "NO_ACTION": 0,
    }
    primary_route_counts: dict[str, int] = {}
    for row in scored:
        priority = str(row.get("pre_notice_priority") or "NO_ACTION")
        if priority in priority_counts:
            priority_counts[priority] += 1
        primary = str(row.get("primary_opportunity_route") or "NONE")
        primary_route_counts[primary] = primary_route_counts.get(primary, 0) + 1
    direct_partner_overlap = sum(
        1
        for row in scored
        if row.get("mice_relevant")
        and "DIRECT_PRIME_BID" in (row.get("opportunity_routes") or [])
        and any(
            route in (row.get("opportunity_routes") or [])
            for route in ("CONSORTIUM_BID", "SUBCONTRACT_OR_SOLUTION_PARTNER")
        )
    )

    write_jsonl(out_dir / "procurements.jsonl", scored)
    stats = {
        "normalized_dir": str(normalized_dir),
        "selected_sources": stages,
        "procurement_count": len(scored),
        "procurement_records_total": len(scored),
        "mice_relevant_procurements": mice_relevant,
        "direct_bid_candidates": direct_n,
        "partner_candidates": partner_n,
        "sales_queue_count": len(sales_queue),
        "pre_notice_direct_review_count": pre_direct,
        "pre_notice_partner_outreach_count": pre_partner,
        "pre_notice_dual_path_count": both_pre,
        "sales_action_type_counts": action_counts,
        "pre_notice_priority_counts": priority_counts,
        "primary_opportunity_route_counts": primary_route_counts,
        "direct_partner_route_overlap_count": direct_partner_overlap,
        "mice_relevance_confidence_counts": {
            "STRONG": sum(1 for r in scored if r.get("mice_relevance_confidence") == "STRONG"),
            "MEDIUM": sum(1 for r in scored if r.get("mice_relevance_confidence") == "MEDIUM"),
            "WEAK": sum(1 for r in scored if r.get("mice_relevance_confidence") == "WEAK"),
            "NONE": sum(1 for r in scored if r.get("mice_relevance_confidence") == "NONE"),
        },
        "normalized_input_counts": {
            "pre_notice": len(pre),
            "bid_notice": len(notices),
            "award_result": len(awards),
            "contract_result": len(contracts),
        },
        "lifecycle": life_stats,
        "previous_cycle": prev_stats,
        "event_links": event_stats,
        "mice_events_available": len(events),
    }
    (out_dir / "link_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--normalized-dir", required=True)
    ap.add_argument("--today", default=None)
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else date.today()
    stats = run_g2b_link(normalized_dir=Path(args.normalized_dir), today=today)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
