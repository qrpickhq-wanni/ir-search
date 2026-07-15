"""Phase-2 orchestrator: normalize → first-pass filter → summary reports."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.io_utils import ensure_dir, find_latest_raw_dir
from app.run_first_pass import run_first_pass
from app.run_normalize import run_normalize
from app.run_summary import run_summary


def run_phase2(
    *,
    raw_dir: Path | None = None,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    run_day = today.isoformat()
    raw_dir = raw_dir or find_latest_raw_dir()

    norm_stats = run_normalize(raw_dir=raw_dir, today=today)
    opp = Path(norm_stats["paths"]["opportunities"])
    dup = Path(norm_stats["paths"]["duplicates"])

    fp_stats = run_first_pass(opp, today=today)
    report_dir = ensure_dir(ROOT / "reports" / run_day)
    # Persist normalize stats for traceability
    stats_path = Path(norm_stats["out_dir"]) / "normalize_stats.json"
    stats_path.write_text(json.dumps(norm_stats, ensure_ascii=False, indent=2), encoding="utf-8")

    input_files = [
        str((raw_dir / "kstartup_all.jsonl").as_posix()),
        str((raw_dir / "sources_all.jsonl").as_posix()),
    ]
    sum_stats = run_summary(
        opportunities_path=opp,
        duplicates_path=dup,
        report_dir=report_dir,
        normalize_stats=norm_stats,
        input_files=input_files,
        run_day=run_day,
    )

    result = {
        "run_day": run_day,
        "raw_dir": str(raw_dir),
        "normalize": norm_stats,
        "first_pass": fp_stats,
        "summary": sum_stats,
        "status_counts": sum_stats.get("status_counts"),
        "report_dir": str(report_dir),
    }
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run Phase-2 normalize + filter + reports")
    ap.add_argument("--raw-dir", type=Path, default=None)
    ap.add_argument("--today", type=str, default=None)
    ap.add_argument("--json-out", type=Path, default=None, help="optional stats JSON path")
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else date.today()
    try:
        result = run_phase2(raw_dir=args.raw_dir, today=today)
    except Exception as e:  # noqa: BLE001
        print(f"[phase2] FAIL: {e}", file=sys.stderr)
        return 1

    print("=== Phase-2 complete ===")
    print(f"input_total={result['normalize']['input_total']}")
    print(f"representative_count={result['normalize']['representative_count']}")
    print(f"auto_merge_groups={result['normalize']['auto_merge_groups']}")
    print(f"error_count={result['normalize']['error_count']}")
    print(f"status_counts={json.dumps(result['status_counts'], ensure_ascii=False)}")
    print(f"report_dir={result['report_dir']}")
    if args.json_out:
        ensure_dir(args.json_out.parent)
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
