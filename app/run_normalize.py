"""Normalize raw JSONL into standard opportunities + dedupe log."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.io_utils import ensure_dir, find_latest_raw_dir, write_jsonl
from app.normalizers.deduplicate import deduplicate
from app.normalizers.kstartup import normalize_kstartup_row
from app.normalizers.sources import normalize_sources_row


def stream_normalize(
    paths: list[Path],
    *,
    today: date | None = None,
) -> tuple[list[dict], list[dict], Counter, int]:
    """Returns normalized_rows, errors, source_counts, input_total."""
    normalized: list[dict] = []
    errors: list[dict] = []
    source_counts: Counter = Counter()
    input_total = 0
    today = today or date.today()

    for path in paths:
        rel = str(path.as_posix())
        # Prefer repo-relative path for traceability
        try:
            rel = str(path.resolve().relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            rel = str(path).replace("\\", "/")

        with path.open(encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if not line.strip():
                    continue
                input_total += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as e:
                    errors.append(
                        {
                            "raw_file": rel,
                            "line_number": line_no,
                            "error_type": "json_decode",
                            "error_message": str(e),
                        }
                    )
                    continue
                try:
                    name = path.name.lower()
                    if "kstartup" in name:
                        rec = normalize_kstartup_row(row, raw_file=rel, today=today)
                    else:
                        rec = normalize_sources_row(row, raw_file=rel, today=today)
                    normalized.append(rec)
                    source_counts[rec["source"]] += 1
                except Exception as e:  # noqa: BLE001 — record and continue
                    errors.append(
                        {
                            "raw_file": rel,
                            "line_number": line_no,
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                        }
                    )
    return normalized, errors, source_counts, input_total


def run_normalize(
    raw_dir: Path | None = None,
    out_dir: Path | None = None,
    *,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    raw_dir = raw_dir or find_latest_raw_dir()
    run_day = today.isoformat()
    out_dir = out_dir or (ROOT / "data" / "normalized" / run_day)
    ensure_dir(out_dir)

    k_path = raw_dir / "kstartup_all.jsonl"
    s_path = raw_dir / "sources_all.jsonl"
    missing = [str(p) for p in (k_path, s_path) if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing input files: " + ", ".join(missing))

    normalized, errors, source_counts, input_total = stream_normalize(
        [k_path, s_path], today=today
    )
    reps, dup_logs = deduplicate(normalized)

    opp_path = out_dir / "opportunities.jsonl"
    dup_path = out_dir / "duplicates.jsonl"
    err_path = out_dir / "normalization_errors.jsonl"
    write_jsonl(opp_path, reps)
    write_jsonl(dup_path, dup_logs)
    write_jsonl(err_path, errors)

    auto_groups = [d for d in dup_logs if d.get("type") == "auto_merged"]
    merged_record_count = sum(max(0, int(d.get("duplicate_count") or 1) - 0) for d in auto_groups)
    # Records absorbed beyond representatives in those groups:
    absorbed = sum(int(d.get("duplicate_count") or 1) for d in auto_groups) - len(auto_groups)

    stats = {
        "raw_dir": str(raw_dir),
        "out_dir": str(out_dir),
        "input_total": input_total,
        "normalized_ok": len(normalized),
        "error_count": len(errors),
        "source_counts": dict(source_counts),
        "representative_count": len(reps),
        "auto_merge_groups": len(auto_groups),
        "candidate_duplicate_pairs": sum(1 for d in dup_logs if d.get("type") == "candidate_duplicate"),
        "merged_occurrence_total": sum(int(d.get("duplicate_count") or 1) for d in auto_groups),
        "absorbed_extra_records": absorbed,
        "paths": {
            "opportunities": str(opp_path),
            "duplicates": str(dup_path),
            "errors": str(err_path),
        },
    }
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Normalize + dedupe raw opportunity JSONL")
    ap.add_argument("--raw-dir", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--today", type=str, default=None, help="YYYY-MM-DD override for D-day/expired")
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else date.today()
    stats = run_normalize(args.raw_dir, args.out_dir, today=today)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
