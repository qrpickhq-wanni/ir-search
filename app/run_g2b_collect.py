"""Collect G2B procurement stages via official data.go.kr OpenAPI."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.io_utils import ensure_dir, load_yaml, project_root, write_jsonl
from app.procurement_collectors import (
    G2bAwardResultCollector,
    G2bBidNoticeCollector,
    G2bContractResultCollector,
    G2bPreNoticeCollector,
)
from app.procurement_collectors.base import resolve_service_key
from app.mice_collectors.http_client import PoliteHttpClient


def run_g2b_collect(
    *,
    today: date | None = None,
    raw_dir: Path | None = None,
    config: dict | None = None,
) -> dict:
    today = today or date.today()
    cfg = config or load_yaml(project_root() / "config" / "g2b-mice-lifecycle.yaml")
    raw_dir = raw_dir or ensure_dir(project_root() / "data" / "raw" / "procurement" / today.isoformat())
    ensure_dir(raw_dir)

    http_cfg = cfg.get("http") or {}
    http = PoliteHttpClient(
        user_agent=str(http_cfg.get("user_agent") or "QRPickG2BMiceMVP/1.0"),
        timeout_seconds=float(http_cfg.get("request_timeout_seconds", 20)),
        delay_seconds=float(http_cfg.get("request_delay_seconds", 0.5)),
        max_retries=int(http_cfg.get("max_retries", 2)),
        retry_backoff_seconds=float(http_cfg.get("retry_backoff_seconds", 1.0)),
        max_requests=int(http_cfg.get("max_requests_per_run", 200)),
    )
    key = resolve_service_key(cfg)

    collectors = [
        G2bPreNoticeCollector(config=cfg, raw_dir=raw_dir, today=today, http=http, service_key=key),
        G2bBidNoticeCollector(config=cfg, raw_dir=raw_dir, today=today, http=http, service_key=key),
        G2bAwardResultCollector(config=cfg, raw_dir=raw_dir, today=today, http=http, service_key=key),
        G2bContractResultCollector(config=cfg, raw_dir=raw_dir, today=today, http=http, service_key=key),
    ]

    results = []
    errors: list[dict] = []
    for c in collectors:
        r = c.collect()
        results.append(r.to_dict())
        for e in r.errors:
            errors.append({"stage": r.stage, "error": e})
        # Ensure empty raw files exist for downstream even on PARTIAL_EXPECTED
        if r.raw_output_path is None and r.status == "PARTIAL_EXPECTED":
            mapping = {
                "pre_notice": "g2b_pre_notices.jsonl",
                "bid_notice": "g2b_bid_notices.jsonl",
                "award_result": "g2b_award_results.jsonl",
                "contract_result": "g2b_contract_results.jsonl",
            }
            p = raw_dir / mapping[c.stage]
            if not p.exists():
                write_jsonl(p, [])

    manifest = {
        "run_day": today.isoformat(),
        "raw_dir": str(raw_dir),
        "auth_present": bool(key),
        "auth_env": (cfg.get("auth") or {}).get("env_var"),
        "collector_version": cfg.get("collector_version"),
        "stages": results,
        "request_count": len(http.request_log),
        # Never include key material
        "openapi_datasets": {
            k: (v or {}).get("dataset_url")
            for k, v in (cfg.get("openapi") or {}).items()
            if isinstance(v, dict)
        },
    }
    (raw_dir / "collection_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_jsonl(raw_dir / "collection_errors.jsonl", errors)
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Collect G2B MICE procurement OpenAPI data")
    ap.add_argument("--today", default=None)
    ap.add_argument("--raw-dir", default=None)
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else date.today()
    raw_dir = Path(args.raw_dir) if args.raw_dir else None
    manifest = run_g2b_collect(today=today, raw_dir=raw_dir)
    print(json.dumps({k: manifest[k] for k in ("run_day", "auth_present", "raw_dir")}, ensure_ascii=False))
    for s in manifest["stages"]:
        print(f"  {s['stage']}: status={s['status']} parsed={s['parsed_count']} errors={s['error_count']}")
    statuses = {s["status"] for s in manifest["stages"]}
    if statuses <= {"OK", "OK_EMPTY", "PARTIAL_EXPECTED"}:
        return 0
    if "FAILED" in statuses or "PARTIAL_UNEXPECTED" in statuses:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
