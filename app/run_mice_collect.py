"""Collect MICE MVP sources into data/raw/mice/YYYY-MM-DD/."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from app.io_utils import ensure_dir, load_yaml, project_root, write_jsonl
from app.mice_collectors.base import CollectResult, now_iso
from app.mice_collectors.k_mice import KMiceCollector
from app.mice_collectors.opendata_kintex_gg import OpendataKintexGgCollector
from app.mice_collectors.songdo_convenia import SongdoConveniaCollector


COLLECTORS = {
    "opendata_kintex_gg": OpendataKintexGgCollector,
    "songdo_convenia": SongdoConveniaCollector,
    "k_mice": KMiceCollector,
}


def load_registry_map(path: Path) -> dict[str, dict]:
    data = load_yaml(path)
    out: dict[str, dict] = {}
    for row in data.get("sources") or []:
        sid = row.get("source_id")
        if sid:
            out[str(sid)] = row
    return out


def run_collect(
    *,
    sources: list[str],
    today: date,
    root: Path | None = None,
) -> dict:
    root = root or project_root()
    policy = load_yaml(root / "config" / "mice-collection-policy.yaml")
    registry = load_registry_map(root / "config" / "mice-source-registry.yaml")
    raw_dir = ensure_dir(root / "data" / "raw" / "mice" / today.isoformat())

    results: list[CollectResult] = []
    error_rows: list[dict] = []

    for sid in sources:
        entry = registry.get(sid)
        if not entry:
            err = CollectResult(
                source_id=sid,
                success=False,
                status="FAILED",
                errors=[f"source_id {sid} not found in mice-source-registry.yaml"],
            )
            results.append(err)
            error_rows.append({"source_id": sid, "phase": "collect", "error": err.errors[0], "at": now_iso()})
            continue
        cls = COLLECTORS.get(sid)
        if not cls:
            err = CollectResult(
                source_id=sid,
                success=False,
                status="FAILED",
                errors=[f"no collector implemented for {sid}"],
            )
            results.append(err)
            error_rows.append({"source_id": sid, "phase": "collect", "error": err.errors[0], "at": now_iso()})
            continue
        collector = cls(registry_entry=entry, policy=policy, raw_dir=raw_dir, today=today)
        try:
            result = collector.collect()
        except Exception as exc:  # noqa: BLE001 — one source must not stop others
            result = CollectResult(
                source_id=sid,
                success=False,
                status="FAILED",
                errors=[str(exc)],
                raw_output_path=str(raw_dir / f"{sid}.jsonl"),
            )
        results.append(result)
        for e in result.errors:
            error_rows.append(
                {"source_id": sid, "phase": "collect", "error": e, "at": now_iso(), "status": result.status}
            )

    write_jsonl(raw_dir / "collection_errors.jsonl", error_rows)
    manifest = {
        "collected_at": now_iso(),
        "today": today.isoformat(),
        "sources": [r.to_dict() for r in results],
        "raw_dir": str(raw_dir),
        "policy_version": policy.get("policy_version"),
        "collector_version": policy.get("collector_version"),
    }
    (raw_dir / "collection_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect MICE MVP sources")
    parser.add_argument(
        "--sources",
        default="opendata_kintex_gg,songdo_convenia,k_mice",
        help="comma-separated source_id list",
    )
    parser.add_argument("--today", default=None, help="YYYY-MM-DD (default: local today)")
    args = parser.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else date.today()
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    manifest = run_collect(sources=sources, today=today)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    statuses = [s.get("status") for s in manifest["sources"]]
    if all(s == "OK" for s in statuses):
        return 0
    if any(s == "OK" or s == "PARTIAL" for s in statuses):
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
