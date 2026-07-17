"""Collect G2B procurement stages via official data.go.kr OpenAPI."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.io_utils import ensure_dir, load_yaml, project_root, write_jsonl
from app.mice_collectors.http_client import PoliteHttpClient
from app.procurement_collectors import (
    G2bAwardResultCollector,
    G2bBidNoticeCollector,
    G2bContractResultCollector,
    G2bPreNoticeCollector,
)
from app.procurement_collectors.base import resolve_service_key
from app.procurement_collectors.g2b_stages import STAGE_RAW_FILES
from app.procurement_collectors.openapi_status import (
    AUTH_OR_PARAM_ERRORS,
    FILTERED_ALL,
    HTTP_ERROR,
    OK,
    OK_EMPTY,
    OK_TRUNCATED,
    PARSING_ERROR,
    PARTIAL_EXPECTED,
    mask_service_key_in_text,
)


SOURCE_ALIASES = {
    "pre_notice": "pre_notice",
    "pre": "pre_notice",
    "bid": "bid_notice",
    "bid_notice": "bid_notice",
    "award": "award_result",
    "award_result": "award_result",
    "contract": "contract_result",
    "contract_result": "contract_result",
    "all": "all",
}

STAGE_FILE = STAGE_RAW_FILES


def parse_sources(raw: str | None) -> list[str]:
    if not raw or str(raw).strip().lower() in {"", "all"}:
        return ["pre_notice", "bid_notice", "award_result", "contract_result"]
    out: list[str] = []
    for part in str(raw).split(","):
        token = part.strip().lower()
        if not token:
            continue
        if token == "all":
            return ["pre_notice", "bid_notice", "award_result", "contract_result"]
        if token not in SOURCE_ALIASES or SOURCE_ALIASES[token] == "all":
            raise ValueError(
                f"Unknown source {part!r}; allowed: pre_notice, bid, award, contract, all"
            )
        stage = SOURCE_ALIASES[token]
        if stage not in out:
            out.append(stage)
    if not out:
        raise ValueError("No sources selected")
    return out


def run_g2b_collect(
    *,
    today: date | None = None,
    raw_dir: Path | None = None,
    config: dict | None = None,
    sources: list[str] | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    max_records: int | None = None,
    max_pages: int | None = None,
    smoke_test: bool = False,
    run_id: str | None = None,
    overwrite_existing: bool = False,
) -> dict:
    today = today or date.today()
    cfg = config or load_yaml(project_root() / "config" / "g2b-mice-lifecycle.yaml")
    raw_dir = raw_dir or ensure_dir(project_root() / "data" / "raw" / "procurement" / today.isoformat())
    ensure_dir(raw_dir)

    if smoke_test:
        max_records = 20 if max_records is None else max_records
        max_pages = 2 if max_pages is None else max_pages
        if from_date is None and to_date is None:
            to_date = today
            from_date = date.fromordinal(today.toordinal() - 30)

    stages = sources or ["pre_notice", "bid_notice", "award_result", "contract_result"]

    # Smoke isolation: do not let any previous run's raw JSONL leak into this run.
    # If reuse_existing is explicitly enabled, callers should set overwrite_existing=False.
    if overwrite_existing:
        for fname in STAGE_FILE.values():
            write_jsonl(raw_dir / fname, [])

    http_cfg = cfg.get("http") or {}
    key = resolve_service_key(cfg)
    http: PoliteHttpClient | None = None
    if key:
        http = PoliteHttpClient(
            user_agent=str(http_cfg.get("user_agent") or "QRPickG2BMiceMVP/1.0"),
            timeout_seconds=float(http_cfg.get("request_timeout_seconds", 20)),
            delay_seconds=float(http_cfg.get("request_delay_seconds", 0.5)),
            max_retries=int(http_cfg.get("max_retries", 2)),
            retry_backoff_seconds=float(http_cfg.get("retry_backoff_seconds", 1.0)),
            max_requests=int(http_cfg.get("max_requests_per_run", 200)),
        )

    collector_cls = {
        "pre_notice": G2bPreNoticeCollector,
        "bid_notice": G2bBidNoticeCollector,
        "award_result": G2bAwardResultCollector,
        "contract_result": G2bContractResultCollector,
    }

    common_kwargs: dict[str, Any] = {
        "config": cfg,
        "raw_dir": raw_dir,
        "today": today,
        "http": http,
        "service_key": key,
        "from_date": from_date,
        "to_date": to_date,
        "max_records": max_records,
        "max_pages": max_pages,
        "smoke_test": smoke_test,
    }

    results = []
    errors: list[dict] = []
    for stage in stages:
        cls = collector_cls[stage]
        c = cls(**common_kwargs)
        r = c.collect()
        results.append(r.to_dict())
        for e in r.errors:
            errors.append(
                {
                    "stage": r.stage,
                    "error": mask_service_key_in_text(e, key),
                    "status": r.status,
                }
            )
        # Ensure raw file exists for downstream
        p = raw_dir / STAGE_FILE[stage]
        if not p.exists():
            write_jsonl(p, [])

    # Empty placeholders for unselected stages so normalize still works
    for stage, fname in STAGE_FILE.items():
        p = raw_dir / fname
        if not p.exists():
            write_jsonl(p, [])

    fresh_raw_count = sum(int(r.get("parsed_count") or 0) for r in results)
    manifest = {
        "run_day": today.isoformat(),
        "raw_dir": str(raw_dir),
        "run_id": run_id,
        "auth_present": bool(key),
        "auth_env": (cfg.get("auth") or {}).get("env_var"),
        "smoke_test": smoke_test,
        "sources": stages,
        "selected_sources": stages,
        "fresh_raw_count": fresh_raw_count,
        "from_date": from_date.isoformat() if from_date else None,
        "to_date": to_date.isoformat() if to_date else None,
        "max_records": max_records,
        "max_pages": max_pages,
        "contact_enrichment": False,
        "collector_version": cfg.get("collector_version"),
        "stages": results,
        "request_count": len(http.request_log) if http else 0,
        "normalized_count": None,
        "procurement_count": None,
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


def collect_exit_code(manifest: dict) -> int:
    statuses = {s.get("status") for s in manifest.get("stages") or []}
    soft_ok = {OK, OK_EMPTY, OK_TRUNCATED, FILTERED_ALL, PARTIAL_EXPECTED}
    if not statuses or statuses <= soft_ok:
        return 0
    if statuses & (AUTH_OR_PARAM_ERRORS | {HTTP_ERROR, PARSING_ERROR, "PARTIAL_UNEXPECTED", "FAILED"}):
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Collect G2B MICE procurement OpenAPI data")
    ap.add_argument("--today", default=None)
    ap.add_argument("--raw-dir", default=None)
    ap.add_argument("--smoke-test", action="store_true")
    ap.add_argument("--sources", default="all")
    ap.add_argument("--from-date", default=None)
    ap.add_argument("--to-date", default=None)
    ap.add_argument("--max-records", type=int, default=None)
    ap.add_argument("--max-pages", type=int, default=None)
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else date.today()
    raw_dir = Path(args.raw_dir) if args.raw_dir else None
    manifest = run_g2b_collect(
        today=today,
        raw_dir=raw_dir,
        sources=parse_sources(args.sources),
        from_date=date.fromisoformat(args.from_date) if args.from_date else None,
        to_date=date.fromisoformat(args.to_date) if args.to_date else None,
        max_records=args.max_records,
        max_pages=args.max_pages,
        smoke_test=bool(args.smoke_test),
    )
    print(json.dumps({k: manifest[k] for k in ("run_day", "auth_present", "raw_dir", "smoke_test")}, ensure_ascii=False))
    for s in manifest["stages"]:
        print(f"  {s['stage']}: status={s['status']} parsed={s['parsed_count']} errors={s['error_count']}")
    return collect_exit_code(manifest)


if __name__ == "__main__":
    raise SystemExit(main())
