"""서울컨벤션뷰로 (miceseoul.com) — HOLD_CONFIGURED.

Registry sets runtime_enabled=false. Collector must not issue HTTP;
run_collect short-circuits before collect() when disabled, but this
module also refuses network if invoked directly.
"""
from __future__ import annotations

from typing import Any

from app.io_utils import write_jsonl
from app.mice_collectors.base import CollectResult, MiceCollector
from app.mice_collectors.runtime_status import HOLD_CONFIGURED


class MiceSeoulCvbCollector(MiceCollector):
    source_id = "mice_seoul_cvb"

    def validate_configuration(self) -> list[str]:
        return [
            "HOLD_CONFIGURED: list endpoint is JS-board/ready.jsp under polite HTTP; "
            "browser automation out of scope. runtime_enabled=false — no HTTP."
        ]

    def collect(self) -> CollectResult:
        warnings = self.validate_configuration()
        out_path = self.raw_dir / f"{self.source_id}.jsonl"
        write_jsonl(out_path, [])
        # Intentionally no PoliteHttpClient / no network
        return CollectResult(
            source_id=self.source_id,
            success=True,
            status=HOLD_CONFIGURED,
            fetched_count=0,
            parsed_count=0,
            error_count=0,
            raw_output_path=str(out_path),
            errors=[],
            warnings=warnings,
            request_log=[],
            metadata={
                **self.get_source_metadata(),
                "implementation_status": HOLD_CONFIGURED,
                "http_requests": 0,
            },
        )

    def normalize_source_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_event_id": None,
            "title": raw.get("title"),
            "title_en": None,
            "start_date_raw": None,
            "end_date_raw": None,
            "date_text": None,
            "venue_name": None,
            "venue_address": None,
            "city": "서울",
            "region": "서울",
            "country": "KR",
            "location_raw": None,
            "host_raw": None,
            "organizer_raw": None,
            "operator_raw": None,
            "pco_raw": None,
            "category_raw": None,
            "homepage": None,
            "official_event_url": None,
            "source_url": raw.get("_source_url"),
            "inquiry_raw": None,
            "contact_email": None,
            "contact_phone": None,
            "contact_department": None,
            "contact_name": None,
            "description_summary": None,
            "collected_at": raw.get("_collected_at"),
        }
