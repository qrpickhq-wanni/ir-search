"""Normalize MICE raw JSONL into common event schema + dedupe."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from app.io_utils import ensure_dir, load_yaml, project_root, read_jsonl, write_jsonl
from app.mice_collectors.k_mice import KMiceCollector
from app.mice_collectors.opendata_kintex_gg import OpendataKintexGgCollector
from app.mice_collectors.songdo_convenia import SongdoConveniaCollector
from app.mice_normalizers.deduplicate import deduplicate_events
from app.mice_normalizers.event_normalizer import normalize_intermediate
from app.mice_normalizers.sales_signals import apply_sales_layer


COLLECTOR_MAP = {
    "opendata_kintex_gg": OpendataKintexGgCollector,
    "songdo_convenia": SongdoConveniaCollector,
    "k_mice": KMiceCollector,
}


def find_mice_raw_dir(root: Path, today: str | None = None) -> Path:
    base = root / "data" / "raw" / "mice"
    if today:
        path = base / today
        if not path.is_dir():
            raise FileNotFoundError(path)
        return path
    dirs = sorted([p for p in base.iterdir() if p.is_dir()], key=lambda p: p.name)
    if not dirs:
        raise FileNotFoundError(f"No raw mice folders under {base}")
    return dirs[-1]


def run_normalize(*, today: date | None = None, raw_dir: Path | None = None, root: Path | None = None) -> dict:
    root = root or project_root()
    policy = load_yaml(root / "config" / "mice-collection-policy.yaml")
    registry = load_yaml(root / "config" / "mice-source-registry.yaml")
    reg_map = {r["source_id"]: r for r in registry.get("sources") or [] if r.get("source_id")}

    raw_dir = raw_dir or find_mice_raw_dir(root, today.isoformat() if today else None)
    day = raw_dir.name
    out_dir = ensure_dir(root / "data" / "normalized" / "mice" / day)

    window = policy.get("date_window") or {}
    past_days = int(window.get("past_days", 60))
    future_days = int(window.get("future_days", 550))
    ref_day = date.fromisoformat(day)

    events: list[dict] = []
    errors: list[dict] = []
    raw_ok = 0

    for sid, cls in COLLECTOR_MAP.items():
        path = raw_dir / f"{sid}.jsonl"
        if not path.exists():
            continue
        rows = read_jsonl(path)
        collector = cls(
            registry_entry=reg_map.get(sid) or {"source_id": sid},
            policy=policy,
            raw_dir=raw_dir,
            today=ref_day,
        )
        for raw in rows:
            raw_ok += 1
            try:
                intermediate = collector.normalize_source_record(raw)
                event, err = normalize_intermediate(
                    intermediate,
                    source_id=sid,
                    raw_file=str(path.as_posix()),
                    today=ref_day,
                    past_days=past_days,
                    future_days=future_days,
                )
                if err or event is None:
                    errors.append(
                        {
                            "source_id": sid,
                            "error": err or "normalize_failed",
                            "title": raw.get("event_nm") or raw.get("title_ko") or raw.get("title"),
                            "raw_source_event_id": intermediate.get("source_event_id"),
                        }
                    )
                    continue
                events.append(event)
            except Exception as exc:  # noqa: BLE001
                errors.append({"source_id": sid, "error": str(exc)})

    reps, dup_log = deduplicate_events(events)
    # Recompute sales layer after merges so contact/org from any member apply
    for rep in reps:
        apply_sales_layer(rep, today=ref_day, intermediate=None)
    write_jsonl(out_dir / "events.jsonl", reps)
    write_jsonl(out_dir / "duplicates.jsonl", dup_log)
    write_jsonl(out_dir / "normalization_errors.jsonl", errors)

    occ_sum = sum(len(e.get("source_occurrences") or []) for e in reps)
    summary = {
        "day": day,
        "raw_ok": raw_ok,
        "normalized_pre_dedupe": len(events),
        "representatives": len(reps),
        "normalization_errors": len(errors),
        "duplicate_log_rows": len(dup_log),
        "confirmed_merges": sum(1 for d in dup_log if d.get("relation") == "CONFIRMED_MERGE"),
        "candidate_duplicates": sum(1 for d in dup_log if d.get("relation") == "CANDIDATE"),
        "source_occurrences_sum": occ_sum,
        "integrity_ok": occ_sum + len(errors) == raw_ok,
        "integrity_formula": "raw_ok == sum(len(source_occurrences)) + normalization_errors",
        "out_dir": str(out_dir),
    }
    (out_dir / "normalize_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", default=None)
    parser.add_argument("--raw-dir", default=None)
    args = parser.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else None
    raw_dir = Path(args.raw_dir) if args.raw_dir else None
    summary = run_normalize(today=today, raw_dir=raw_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("integrity_ok") else 2


if __name__ == "__main__":
    sys.exit(main())
