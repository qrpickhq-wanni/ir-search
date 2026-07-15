"""Apply rule-based first-pass filter to normalized opportunities."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluators.rule_filter import apply_first_pass_batch
from app.io_utils import iso_today, load_yaml, read_jsonl, write_jsonl


def run_first_pass(
    opportunities_path: Path,
    *,
    rules_path: Path | None = None,
    profile_path: Path | None = None,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    rules_path = rules_path or (ROOT / "config" / "filter-rules.yaml")
    profile_path = profile_path or (ROOT / "config" / "qrpick-profile.yaml")
    rules = load_yaml(rules_path)
    profile = load_yaml(profile_path)
    rows = read_jsonl(opportunities_path)
    scored = apply_first_pass_batch(rows, rules, profile, today=today)
    write_jsonl(opportunities_path, scored)

    from collections import Counter

    status_counts = Counter(r.get("first_pass_status") for r in scored)
    return {
        "opportunities_path": str(opportunities_path),
        "count": len(scored),
        "status_counts": dict(status_counts),
        "run_day": today.isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rule-based first-pass filter")
    ap.add_argument("--opportunities", type=Path, required=True)
    ap.add_argument("--today", type=str, default=None)
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else date.today()
    stats = run_first_pass(args.opportunities, today=today)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
