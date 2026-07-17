"""Orchestrate G2B MICE procurement lifecycle MVP: collect → normalize → link → summary."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.io_utils import ensure_dir, project_root
from app.run_g2b_collect import collect_exit_code, parse_sources, run_g2b_collect
from app.run_g2b_link import run_g2b_link
from app.run_g2b_normalize import run_g2b_normalize
from app.run_g2b_summary import run_g2b_summary


def run_g2b_mice_mvp(
    *,
    today: date | None = None,
    smoke_test: bool = False,
    sources: list[str] | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    max_records: int | None = None,
    max_pages: int | None = None,
    run_id: str | None = None,
    reuse_existing: bool = False,
    base_dir: Path | None = None,
) -> dict:
    today = today or date.today()
    root = base_dir or project_root()
    day = today.isoformat()

    run_id_final: str | None = None
    if smoke_test:
        run_id_final = run_id or uuid4().hex[:8]
        if reuse_existing:
            raw_dir = ensure_dir(root / "data" / "raw" / "procurement" / f"{day}-smoke")
            norm_dir = ensure_dir(root / "data" / "normalized" / "procurement" / f"{day}-smoke")
            report_dir = ensure_dir(root / "reports" / day / "g2b-smoke")
        else:
            raw_dir = ensure_dir(root / "data" / "raw" / "procurement" / f"{day}-smoke-{run_id_final}")
            norm_dir = ensure_dir(root / "data" / "normalized" / "procurement" / f"{day}-smoke-{run_id_final}")
            report_dir = ensure_dir(root / "reports" / day / "g2b-smoke" / run_id_final)
    else:
        raw_dir = ensure_dir(root / "data" / "raw" / "procurement" / day)
        norm_dir = ensure_dir(root / "data" / "normalized" / "procurement" / day)
        report_dir = ensure_dir(root / "reports" / day)

    selected = sources or ["pre_notice", "bid_notice", "award_result", "contract_result"]

    collect = run_g2b_collect(
        today=today,
        raw_dir=raw_dir,
        sources=selected,
        from_date=from_date,
        to_date=to_date,
        max_records=max_records,
        max_pages=max_pages,
        smoke_test=smoke_test,
        run_id=run_id_final,
        overwrite_existing=smoke_test and not reuse_existing,
    )
    selected_sources = collect.get("selected_sources") or selected
    normalize = run_g2b_normalize(
        raw_dir=raw_dir,
        out_dir=norm_dir,
        today=today,
        selected_sources=selected_sources,
    )
    link = run_g2b_link(
        normalized_dir=norm_dir,
        out_dir=norm_dir,
        today=today,
        selected_sources=selected_sources,
    )

    # Cross-check manifest counts for this run only.
    collect["normalized_count"] = normalize.get("normalized_total")
    collect["procurement_count"] = link.get("procurement_count")
    manifest_path = raw_dir / "collection_manifest.json"
    manifest_path.write_text(json.dumps(collect, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = run_g2b_summary(
        procurements_path=norm_dir / "procurements.jsonl",
        report_dir=report_dir,
        link_stats=link,
        collect_manifest=collect,
        normalize_stats=normalize,
        run_day=day,
    )
    result = {
        "run_day": day,
        "smoke_test": smoke_test,
        "run_id": run_id_final,
        "collect": collect,
        "normalize": normalize,
        "link": link,
        "summary": summary,
    }
    out_json = (report_dir / ("g2b-mice-mvp-smoke-result.json" if smoke_test else "g2b-mice-mvp-result.json"))
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="G2B MICE procurement lifecycle MVP")
    ap.add_argument("--today", default=None, help="Run date YYYY-MM-DD (default: today)")
    ap.add_argument(
        "--smoke-test",
        action="store_true",
        help="Bounded live OpenAPI smoke test (default 30d / 20 records / 2 pages)",
    )
    ap.add_argument(
        "--sources",
        default="all",
        help="Comma-separated stages: pre_notice,bid,award,contract,all",
    )
    ap.add_argument("--from-date", default=None, help="Inquiry start date YYYY-MM-DD")
    ap.add_argument("--to-date", default=None, help="Inquiry end date YYYY-MM-DD")
    ap.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Max records per stage (smoke default: 20)",
    )
    ap.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max pages per query (smoke default: 2)",
    )
    ap.add_argument("--run-id", default=None, help="Smoke run id (isolation; default: auto)")
    ap.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Reuse previous smoke outputs for the same day (no isolation; explicit merges only).",
    )
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else date.today()
    result = run_g2b_mice_mvp(
        today=today,
        smoke_test=bool(args.smoke_test),
        sources=parse_sources(args.sources),
        from_date=date.fromisoformat(args.from_date) if args.from_date else None,
        to_date=date.fromisoformat(args.to_date) if args.to_date else None,
        max_records=args.max_records,
        max_pages=args.max_pages,
        run_id=args.run_id,
        reuse_existing=bool(args.reuse_existing),
    )
    label = "SMOKE" if args.smoke_test else "MVP"
    print(f"=== G2B MICE {label} complete ===")
    print(f"auth_present={result['collect'].get('auth_present')}")
    print(f"smoke_test={result.get('smoke_test')}")
    if result.get("run_id"):
        print(f"run_id={result.get('run_id')}")
    print(f"sources={result['collect'].get('sources')}")
    print(f"normalized_total={result['normalize'].get('normalized_total')}")
    print(f"procurement_records_total={result['link'].get('procurement_records_total')}")
    print(f"mice_relevant_procurements={result['link'].get('mice_relevant_procurements')}")
    print(f"direct_bid_candidates={result['link'].get('direct_bid_candidates')}")
    print(f"partner_candidates={result['link'].get('partner_candidates')}")
    print(f"sales_queue_count={result['link'].get('sales_queue_count')}")
    print(f"pre_notice_direct_review={result['link'].get('pre_notice_direct_review_count')}")
    print(f"pre_notice_partner_outreach={result['link'].get('pre_notice_partner_outreach_count')}")
    print(f"sales_action_types={result['link'].get('sales_action_type_counts')}")
    print(f"pre_notice_priority={result['link'].get('pre_notice_priority_counts')}")
    print(f"primary_routes={result['link'].get('primary_opportunity_route_counts')}")
    print(f"mice_confidence={result['link'].get('mice_relevance_confidence_counts')}")
    print(f"procurements={result['link'].get('procurement_count')}")
    print(f"report_dir={result['summary'].get('report_dir')}")
    for s in result["collect"].get("stages") or []:
        meta = s.get("metadata") or {}
        print(
            f"  {s.get('stage')}: status={s.get('status')} "
            f"parsed={s.get('parsed_count')} "
            f"raw_before_mice={meta.get('raw_item_count_before_mice_filter')} "
            f"mice_after={meta.get('mice_filter_after_count')} "
            f"totalCount={meta.get('total_count_reported')} "
            f"limit_reached={meta.get('limit_reached')} "
            f"http_pages={len(meta.get('pages') or [])}"
        )
    return collect_exit_code(result["collect"])


if __name__ == "__main__":
    raise SystemExit(main())
