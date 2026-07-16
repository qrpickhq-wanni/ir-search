"""Normalize raw G2B procurement JSONL files."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.io_utils import ensure_dir, project_root, read_jsonl, write_jsonl
from app.procurement_normalizers.notice_normalizer import (
    normalize_award_result,
    normalize_bid_notice,
    normalize_contract_result,
    normalize_pre_notice,
)


def run_g2b_normalize(
    *,
    raw_dir: Path,
    out_dir: Path | None = None,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    out_dir = out_dir or ensure_dir(
        project_root() / "data" / "normalized" / "procurement" / today.isoformat()
    )
    ensure_dir(out_dir)

    pre = [normalize_pre_notice(r, today=today) for r in _load(raw_dir / "g2b_pre_notices.jsonl")]
    notices = [normalize_bid_notice(r, today=today) for r in _load(raw_dir / "g2b_bid_notices.jsonl")]
    awards = [normalize_award_result(r, today=today) for r in _load(raw_dir / "g2b_award_results.jsonl")]
    contracts = [
        normalize_contract_result(r, today=today) for r in _load(raw_dir / "g2b_contract_results.jsonl")
    ]

    # Drop null procurement_id
    pre = [r for r in pre if r.get("procurement_id")]
    notices = [r for r in notices if r.get("procurement_id")]
    awards = [r for r in awards if r.get("procurement_id")]
    contracts = [r for r in contracts if r.get("procurement_id")]

    write_jsonl(out_dir / "pre_notices.jsonl", pre)
    write_jsonl(out_dir / "bid_notices.jsonl", notices)
    write_jsonl(out_dir / "award_results.jsonl", awards)
    write_jsonl(out_dir / "contract_results.jsonl", contracts)

    stats = {
        "raw_dir": str(raw_dir),
        "out_dir": str(out_dir),
        "pre_notice_count": len(pre),
        "bid_notice_count": len(notices),
        "award_result_count": len(awards),
        "contract_result_count": len(contracts),
        "normalized_total": len(pre) + len(notices) + len(awards) + len(contracts),
    }
    (out_dir / "normalize_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stats


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return read_jsonl(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--today", default=None)
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else date.today()
    stats = run_g2b_normalize(
        raw_dir=Path(args.raw_dir),
        out_dir=Path(args.out_dir) if args.out_dir else None,
        today=today,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
