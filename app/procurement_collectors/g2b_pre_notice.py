"""G2B 용역 사전규격 collector (HrcspSsstndrdInfoService)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.io_utils import write_jsonl
from app.procurement_collectors.api_client import DataGoKrClient
from app.procurement_collectors.base import ProcurementCollectResult, ProcurementCollector
from app.procurement_collectors.g2b_bid_notice import _all_keywords


class G2bPreNoticeCollector(ProcurementCollector):
    stage = "pre_notice"

    def collect(self) -> ProcurementCollectResult:
        if not self.service_key:
            return self.missing_key_result()

        openapi = (self.config.get("openapi") or {}).get("pre_notice") or {}
        service_path = str(openapi.get("service_path") or "")
        search_op = str(openapi.get("search_operation") or "getPublicPrcureThngInfoServcPPSSrch")
        list_op = str(openapi.get("list_operation") or "getPublicPrcureThngInfoServc")
        windows = self.config.get("windows") or {}
        bgn, end = self.date_window(int(windows.get("bid_notice_past_days", 180)))

        client = DataGoKrClient(config=self.config, http=self.http, service_key=self.service_key)
        keywords = _all_keywords(self.config)
        errors: list[str] = []
        page_meta: list[dict[str, Any]] = []
        by_key: dict[str, dict[str, Any]] = {}

        for kw in keywords:
            if len(by_key) >= self.max_records:
                break
            remaining = self.max_records - len(by_key)
            rows, meta, errs = client.paginate(
                service_path=service_path,
                operation=search_op,
                base_params={
                    "inqryDiv": 1,
                    "inqryBgnDt": bgn,
                    "inqryEndDt": end,
                    "prdctClsfcNoNm": kw,
                },
                max_pages=min(self.max_pages, 3),
                max_records=remaining,
                num_of_rows=self.num_of_rows,
            )
            page_meta.extend(meta)
            errors.extend(errs)
            for row in rows:
                stamped = self.stamp(
                    row,
                    operation=search_op,
                    source_url=client.build_url(service_path, search_op),
                )
                stamped["_search_keyword"] = kw
                key = str(row.get("bfSpecRgstNo") or row.get("bfspecRgstNo") or "")
                if key and key not in by_key:
                    by_key[key] = stamped

        if not by_key:
            rows, meta, errs = client.paginate(
                service_path=service_path,
                operation=list_op,
                base_params={"inqryDiv": 1, "inqryBgnDt": bgn, "inqryEndDt": end},
                max_pages=self.max_pages,
                max_records=self.max_records,
                num_of_rows=self.num_of_rows,
            )
            page_meta.extend(meta)
            errors.extend(errs)
            for row in rows:
                stamped = self.stamp(
                    row,
                    operation=list_op,
                    source_url=client.build_url(service_path, list_op),
                )
                key = str(row.get("bfSpecRgstNo") or "")
                if key and key not in by_key:
                    by_key[key] = stamped

        records = list(by_key.values())[: self.max_records]
        out_path = Path(self.raw_dir) / "g2b_pre_notices.jsonl"
        write_jsonl(out_path, records)

        status = "OK" if records else ("FAILED" if errors else "OK_EMPTY")
        if errors and records:
            status = "PARTIAL_UNEXPECTED"

        return ProcurementCollectResult(
            stage=self.stage,
            success=status in {"OK", "OK_EMPTY", "PARTIAL_UNEXPECTED"},
            status=status,
            fetched_count=len(records),
            parsed_count=len(records),
            error_count=len(errors),
            raw_output_path=str(out_path),
            errors=errors,
            request_log=list(self.http.request_log),
            metadata={
                "auth_present": True,
                "window": {"inqryBgnDt": bgn, "inqryEndDt": end},
                "pages": page_meta[:40],
                "dataset_url": openapi.get("dataset_url"),
            },
        )
