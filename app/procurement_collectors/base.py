"""Shared base for G2B / data.go.kr procurement collectors."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.mice_collectors.http_client import PoliteHttpClient


COLLECTOR_VERSION = "1.0.0"
KST = timezone(timedelta(hours=9))


def now_iso() -> str:
    return datetime.now(KST).replace(microsecond=0).isoformat()


def resolve_service_key(config: dict[str, Any]) -> str | None:
    auth = config.get("auth") or {}
    names = [auth.get("env_var") or "DATA_GO_KR_SERVICE_KEY"]
    names.extend(auth.get("alt_env_vars") or [])
    for name in names:
        if not name:
            continue
        val = (os.environ.get(str(name)) or "").strip()
        if val:
            return val
    return None


@dataclass
class ProcurementCollectResult:
    stage: str
    success: bool
    status: str = "OK"  # OK | OK_EMPTY | PARTIAL_EXPECTED | FAILED
    fetched_count: int = 0
    parsed_count: int = 0
    error_count: int = 0
    raw_output_path: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    request_log: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "success": self.success,
            "status": self.status,
            "fetched_count": self.fetched_count,
            "parsed_count": self.parsed_count,
            "error_count": self.error_count,
            "raw_output_path": self.raw_output_path,
            "errors": self.errors,
            "warnings": self.warnings,
            "request_count": len(self.request_log),
            "metadata": self.metadata,
        }


class ProcurementCollector:
    stage: str = "unknown"

    def __init__(
        self,
        *,
        config: dict[str, Any],
        raw_dir: Path,
        today: date | None = None,
        http: PoliteHttpClient | None = None,
        service_key: str | None = None,
    ) -> None:
        self.config = config
        self.raw_dir = raw_dir
        self.today = today or date.today()
        self.service_key = service_key if service_key is not None else resolve_service_key(config)
        http_cfg = config.get("http") or {}
        limits = config.get("limits") or {}
        self.max_records = int(limits.get("max_records_per_stage", 500))
        self.max_pages = int(limits.get("max_pages_per_query", 20))
        self.num_of_rows = int(limits.get("num_of_rows", 100))
        self.collector_version = str(config.get("collector_version") or COLLECTOR_VERSION)
        if http is not None:
            self.http = http
        else:
            self.http = PoliteHttpClient(
                user_agent=str(http_cfg.get("user_agent") or "QRPickG2BMiceMVP/1.0"),
                timeout_seconds=float(http_cfg.get("request_timeout_seconds", 20)),
                delay_seconds=float(http_cfg.get("request_delay_seconds", 0.5)),
                max_retries=int(http_cfg.get("max_retries", 2)),
                retry_backoff_seconds=float(http_cfg.get("retry_backoff_seconds", 1.0)),
                max_requests=int(http_cfg.get("max_requests_per_run", 200)),
            )

    def date_window(self, past_days: int) -> tuple[str, str]:
        end = self.today
        start = self.today - timedelta(days=past_days)
        return start.strftime("%Y%m%d") + "0000", end.strftime("%Y%m%d") + "2359"

    def stamp(self, record: dict[str, Any], *, operation: str, source_url: str) -> dict[str, Any]:
        out = dict(record)
        out["_stage"] = self.stage
        out["_operation"] = operation
        out["_source_url"] = source_url
        out["_collected_at"] = now_iso()
        out["_collector_version"] = self.collector_version
        return out

    def missing_key_result(self) -> ProcurementCollectResult:
        auth = self.config.get("auth") or {}
        return ProcurementCollectResult(
            stage=self.stage,
            success=True,
            status="PARTIAL_EXPECTED",
            warnings=[
                f"Missing API key env {auth.get('env_var') or 'DATA_GO_KR_SERVICE_KEY'}; "
                "collector structure validated; live OpenAPI collect skipped. "
                f"Apply at: {', '.join(auth.get('apply_urls') or [])}"
            ],
            metadata={"auth_present": False},
        )

    def collect(self) -> ProcurementCollectResult:  # pragma: no cover - override
        raise NotImplementedError
