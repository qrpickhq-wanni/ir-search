"""G2B 용역 입찰공고 collector (BidPublicInfoService)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.io_utils import write_jsonl
from app.procurement_collectors.api_client import DataGoKrClient
from app.procurement_collectors.base import ProcurementCollectResult, ProcurementCollector


class G2bBidNoticeCollector(ProcurementCollector):
    stage = "bid_notice"

    def collect(self) -> ProcurementCollectResult:
        if not self.service_key:
            return self.missing_key_result()

        openapi = (self.config.get("openapi") or {}).get("bid_notice") or {}
        service_path = str(openapi.get("service_path") or "")
        search_op = str(openapi.get("search_operation") or "getBidPblancListInfoServcPPSSrch")
        list_op = str(openapi.get("list_operation") or "getBidPblancListInfoServc")
        windows = self.config.get("windows") or {}
        bgn, end = self.date_window(int(windows.get("bid_notice_past_days", 180)))

        client = DataGoKrClient(config=self.config, http=self.http, service_key=self.service_key)
        keywords = _all_keywords(self.config)
        errors: list[str] = []
        warnings: list[str] = []
        page_meta: list[dict[str, Any]] = []
        by_key: dict[str, dict[str, Any]] = {}

        # Primary: keyword PPS search (title)
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
                    "bidNtceNm": kw,
                },
                max_pages=min(self.max_pages, 5),
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
                key = _notice_key(row)
                if key and key not in by_key:
                    by_key[key] = stamped

        # Fallback list window if keyword search yielded nothing (still caps at max_records)
        if not by_key and not errors:
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
                key = _notice_key(row)
                if key and key not in by_key:
                    by_key[key] = stamped
            warnings.append("keyword PPS search empty; used list_operation window fallback")

        records = list(by_key.values())[: self.max_records]
        # Client-side MICE/QRPick relevance filter when list fallback used
        filtered = [r for r in records if _title_matches_keywords(r, keywords)] or records

        out_path = Path(self.raw_dir) / "g2b_bid_notices.jsonl"
        write_jsonl(out_path, filtered)

        status = "OK" if filtered else "OK_EMPTY"
        if errors and filtered:
            status = "PARTIAL_UNEXPECTED"
        elif errors and not filtered:
            status = "FAILED"

        return ProcurementCollectResult(
            stage=self.stage,
            success=status in {"OK", "OK_EMPTY", "PARTIAL_UNEXPECTED"},
            status=status,
            fetched_count=len(records),
            parsed_count=len(filtered),
            error_count=len(errors),
            raw_output_path=str(out_path),
            errors=errors,
            warnings=warnings,
            request_log=list(self.http.request_log),
            metadata={
                "auth_present": True,
                "window": {"inqryBgnDt": bgn, "inqryEndDt": end},
                "keywords_tried": len(keywords),
                "pages": page_meta[:40],
                "dataset_url": openapi.get("dataset_url"),
            },
        )


def _all_keywords(config: dict[str, Any]) -> list[str]:
    sk = config.get("search_keywords") or {}
    out: list[str] = []
    for group in sk.values():
        if isinstance(group, list):
            out.extend(str(x) for x in group if x)
    # de-dupe preserve order
    return list(dict.fromkeys(out))


def _notice_key(row: dict[str, Any]) -> str | None:
    no = row.get("bidNtceNo") or row.get("bidntceNo")
    ord_ = row.get("bidNtceOrd") or row.get("bidntceOrd") or "00"
    if not no:
        return None
    return f"{no}:{ord_}"


def _title_matches_keywords(row: dict[str, Any], keywords: list[str]) -> bool:
    title = str(row.get("bidNtceNm") or row.get("bidntceNm") or "")
    if not title:
        return False
    return any(k in title for k in keywords)
