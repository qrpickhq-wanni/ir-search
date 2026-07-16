"""Orchestrate G2B MICE procurement lifecycle MVP: collect → normalize → link → summary."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.io_utils import ensure_dir, project_root
from app.run_g2b_collect import run_g2b_collect
from app.run_g2b_link import run_g2b_link
from app.run_g2b_normalize import run_g2b_normalize
from app.run_g2b_summary import run_g2b_summary


def run_g2b_mice_mvp(*, today: date | None = None) -> dict:
    today = today or date.today()
    day = today.isoformat()
    raw_dir = ensure_dir(project_root() / "data" / "raw" / "procurement" / day)
    norm_dir = ensure_dir(project_root() / "data" / "normalized" / "procurement" / day)
    report_dir = ensure_dir(project_root() / "reports" / day)

    collect = run_g2b_collect(today=today, raw_dir=raw_dir)
    normalize = run_g2b_normalize(raw_dir=raw_dir, out_dir=norm_dir, today=today)
    link = run_g2b_link(normalized_dir=norm_dir, out_dir=norm_dir, today=today)
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
        "collect": collect,
        "normalize": normalize,
        "link": link,
        "summary": summary,
    }
    (report_dir / "g2b-mice-mvp-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="G2B MICE procurement lifecycle MVP")
    ap.add_argument("--today", default=None)
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else date.today()
    result = run_g2b_mice_mvp(today=today)
    print("=== G2B MICE MVP complete ===")
    print(f"auth_present={result['collect'].get('auth_present')}")
    print(f"normalized_total={result['normalize'].get('normalized_total')}")
    print(f"procurements={result['link'].get('procurement_count')}")
    print(f"report_dir={result['summary'].get('report_dir')}")
    stages = result["collect"].get("stages") or []
    statuses = {s.get("status") for s in stages}
    if statuses <= {"OK", "OK_EMPTY", "PARTIAL_EXPECTED"} or not statuses:
        return 0
    if "FAILED" in statuses or "PARTIAL_UNEXPECTED" in statuses:
        # Still produced reports from whatever was collected
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
