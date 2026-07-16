"""Base interface for MICE event collectors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


COLLECTOR_VERSION = "1.0.0"
KST = timezone(timedelta(hours=9))


def now_iso() -> str:
    return datetime.now(KST).replace(microsecond=0).isoformat()


@dataclass
class CollectResult:
    source_id: str
    success: bool
    fetched_count: int = 0
    parsed_count: int = 0
    error_count: int = 0
    raw_output_path: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: str = "OK"  # OK | OK_EMPTY | PARTIAL_EXPECTED | HOLD_CONFIGURED | PARTIAL_UNEXPECTED | FAILED
    request_log: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
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


class MiceCollector(ABC):
    source_id: str

    def __init__(
        self,
        *,
        registry_entry: dict[str, Any],
        policy: dict[str, Any],
        raw_dir: Path,
        today: date | None = None,
    ) -> None:
        self.registry_entry = registry_entry
        self.policy = policy
        self.raw_dir = raw_dir
        self.today = today or date.today()
        self.collector_version = policy.get("collector_version") or COLLECTOR_VERSION
        window = policy.get("date_window") or {}
        self.past_days = int(window.get("past_days", 60))
        self.future_days = int(window.get("future_days", 550))
        limits = policy.get("limits") or {}
        self.max_records = int(limits.get("max_records_per_source", 500))
        self.max_requests = int(limits.get("max_requests_per_source", 120))
        self.max_pages = int(limits.get("max_pages_per_source", 50))
        http = policy.get("http") or {}
        self.user_agent = str(
            http.get("user_agent")
            or "QRPickMiceMVP/1.0 (+internal research; polite; delay>=0.5s)"
        )
        self.delay_seconds = float(http.get("request_delay_seconds", 0.5))
        self.timeout_seconds = float(http.get("request_timeout_seconds", 20))
        self.max_retries = int(http.get("max_retries", 2))
        self.retry_backoff_seconds = float(http.get("retry_backoff_seconds", 1.0))

    def window_bounds(self) -> tuple[date, date]:
        start = self.today - timedelta(days=self.past_days)
        end = self.today + timedelta(days=self.future_days)
        return start, end

    def stamp_raw(self, record: dict[str, Any], source_url: str) -> dict[str, Any]:
        out = dict(record)
        out["_source_id"] = self.source_id
        out["_source_url"] = source_url
        out["_collected_at"] = now_iso()
        out["_collector_version"] = self.collector_version
        return out

    @abstractmethod
    def validate_configuration(self) -> list[str]:
        """Return warning/error strings. Empty means ready."""

    @abstractmethod
    def collect(self) -> CollectResult:
        ...

    @abstractmethod
    def normalize_source_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Map one raw record into intermediate fields for the event normalizer."""

    def get_source_metadata(self) -> dict[str, Any]:
        e = self.registry_entry
        return {
            "source_id": self.source_id,
            "source_name": e.get("source_name"),
            "base_url": e.get("base_url"),
            "list_urls": list(e.get("list_urls") or []),
            "implementation_mode": e.get("implementation_mode"),
            "technical_grade": e.get("technical_grade"),
            "legal_operational_grade": e.get("legal_operational_grade"),
            "rendering_type": e.get("rendering_type"),
            "api_or_xhr_status": e.get("api_or_xhr_status"),
        }
