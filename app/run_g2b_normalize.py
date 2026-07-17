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
from app.procurement_collectors.g2b_stages import (
    ALL_G2B_STAGES,
    STAGE_COUNT_KEYS,
    STAGE_NORMALIZED_FILES,
    STAGE_NORMALIZERS,
    STAGE_RAW_FILES,
    normalize_selected_sources,
)


def run_g2b_normalize(
    *,
    raw_dir: Path,
    out_dir: Path | None = None,
    today: date | None = None,
    selected_sources: list[str] | None = None,
) -> dict:
    today = today or date.today()
    out_dir = out_dir or ensure_dir(
        project_root() / "data" / "normalized" / "procurement" / today.isoformat()
    )
    ensure_dir(out_dir)

    stages = normalize_selected_sources(selected_sources)
    counts: dict[str, int] = {}

    for stage in ALL_G2B_STAGES:
        if stage in stages:
            normalizer = STAGE_NORMALIZERS[stage]
            raw_path = raw_dir / STAGE_RAW_FILES[stage]
            rows = [normalizer(r, today=today) for r in _load(raw_path)]
            rows = [r for r in rows if r.get("procurement_id")]
        else:
            rows = []
        write_jsonl(out_dir / STAGE_NORMALIZED_FILES[stage], rows)
        counts[STAGE_COUNT_KEYS[stage]] = len(rows)

    stats = {
        "raw_dir": str(raw_dir),
        "out_dir": str(out_dir),
        "selected_sources": stages,
        **counts,
        "normalized_total": sum(counts.values()),
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
    ap.add_argument(
        "--sources",
        default="all",
        help="Comma-separated stages to normalize (default: all present in raw dir)",
    )
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else date.today()
    from app.run_g2b_collect import parse_sources

    selected = None if str(args.sources).strip().lower() in {"", "all"} else parse_sources(args.sources)
    stats = run_g2b_normalize(
        raw_dir=Path(args.raw_dir),
        out_dir=Path(args.out_dir) if args.out_dir else None,
        today=today,
        selected_sources=selected,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
