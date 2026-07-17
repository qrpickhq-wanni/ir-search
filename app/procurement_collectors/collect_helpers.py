"""Shared collect helpers for G2B stage collectors."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.io_utils import write_jsonl
from app.procurement_collectors.api_client import DataGoKrClient
from app.procurement_collectors.base import ProcurementCollectResult, ProcurementCollector
from app.procurement_collectors.openapi_status import (
    AUTH_OR_PARAM_ERRORS,
    FILTERED_ALL,
    OK,
    OK_EMPTY,
    OK_TRUNCATED,
    finalize_collect_status,
    mask_service_key_in_url,
)


DateMode = str  # "datetime" (YYYYMMDDHHMM) | "date" (YYYYMMDD)


def all_keywords(config: dict[str, Any]) -> list[str]:
    sk = config.get("search_keywords") or {}
    out: list[str] = []
    for group in sk.values():
        if isinstance(group, list):
            out.extend(str(x) for x in group if x)
    return list(dict.fromkeys(out))


def safe_request_log(entries: list[dict[str, Any]], key: str | None) -> list[dict[str, Any]]:
    out = []
    for e in entries:
        d = dict(e)
        if d.get("url"):
            d["url"] = mask_service_key_in_url(str(d["url"]), key)
        out.append(d)
    return out


def _window_params(
    collector: ProcurementCollector,
    past_days: int,
    *,
    date_mode: DateMode = "datetime",
) -> tuple[dict[str, str], dict[str, str]]:
    """Return (query_date_params, window_meta)."""
    bgn_dt, end_dt = collector.date_window(past_days)
    if date_mode == "date":
        params = {"inqryBgnDate": bgn_dt[:8], "inqryEndDate": end_dt[:8]}
        meta = {"inqryBgnDate": params["inqryBgnDate"], "inqryEndDate": params["inqryEndDate"]}
    else:
        params = {"inqryBgnDt": bgn_dt, "inqryEndDt": end_dt}
        meta = {"inqryBgnDt": bgn_dt, "inqryEndDt": end_dt}
    return params, meta


def _title_match(row: dict[str, Any], keywords: list[str], title_fields: tuple[str, ...]) -> bool:
    if not keywords:
        return True
    blob = " ".join(str(row.get(f) or "") for f in title_fields)
    if not blob.strip():
        return False
    return any(k in blob for k in keywords)


def _max_total_count(page_meta: list[dict[str, Any]]) -> int | None:
    totals = [p.get("totalCount") for p in page_meta if isinstance(p.get("totalCount"), int)]
    return max(totals) if totals else None


def collect_list_first(
    collector: ProcurementCollector,
    *,
    openapi_key: str,
    raw_filename: str,
    past_days_key: str,
    default_past_days: int,
    list_op_default: str,
    search_op_default: str,
    search_param_name: str,
    record_key_fn: Callable[[dict[str, Any]], str | None],
    list_date_mode: DateMode = "datetime",
    search_date_mode: DateMode = "datetime",
    title_fields: tuple[str, ...] = ("bidNtceNm", "cntrctNm", "prdctClsfcNoNm"),
    prefer_list_first: bool = True,
) -> ProcurementCollectResult:
    if not collector.service_key:
        return collector.missing_key_result()

    openapi = (collector.config.get("openapi") or {}).get(openapi_key) or {}
    service_path = str(openapi.get("service_path") or "")
    search_op = str(openapi.get("search_operation") or search_op_default)
    list_op = str(openapi.get("list_operation") or list_op_default)
    windows = collector.config.get("windows") or {}
    past_days = 30 if collector.smoke_test else int(windows.get(past_days_key, default_past_days))
    list_params, list_window = _window_params(collector, past_days, date_mode=list_date_mode)
    search_params, search_window = _window_params(collector, past_days, date_mode=search_date_mode)

    client = DataGoKrClient(
        config=collector.config, http=collector.http, service_key=collector.service_key
    )
    keywords = all_keywords(collector.config)
    if collector.smoke_test:
        keywords = keywords[:3]

    errors: list[str] = []
    warnings: list[str] = []
    page_meta: list[dict[str, Any]] = []
    page_statuses: list[str | None] = []
    hard_error: str | None = None
    by_key: dict[str, dict[str, Any]] = {}
    max_pages_reached = False

    def _ingest(rows: list[dict[str, Any]], operation: str, kw: str | None = None) -> None:
        for row in rows:
            stamped = collector.stamp(
                row,
                operation=operation,
                source_url=client.build_url(service_path, operation),
            )
            if kw:
                stamped["_search_keyword"] = kw
            key = record_key_fn(row)
            if key and key not in by_key:
                by_key[key] = stamped

    def _paginate(operation: str, base_params: dict[str, Any], *, max_pages: int, max_records: int):
        nonlocal hard_error, max_pages_reached
        rows, meta, errs, herr = client.paginate(
            service_path=service_path,
            operation=operation,
            base_params=base_params,
            max_pages=max_pages,
            max_records=max_records,
            num_of_rows=collector.num_of_rows,
        )
        page_meta.extend(meta)
        errors.extend(errs)
        page_statuses.extend(m.get("errorStatus") for m in meta)
        if len(meta) >= max_pages and rows:
            max_pages_reached = True
        if herr:
            hard_error = herr
        return rows

    use_list_first = prefer_list_first or collector.smoke_test or not keywords

    if use_list_first:
        rows = _paginate(
            list_op,
            {"inqryDiv": 1, **list_params},
            max_pages=collector.max_pages,
            max_records=collector.max_records,
        )
        if not hard_error:
            _ingest(rows, list_op)

    if not hard_error and keywords and not collector.smoke_test:
        for kw in keywords:
            if hard_error or len(by_key) >= collector.max_records:
                break
            remaining = collector.max_records - len(by_key)
            rows = _paginate(
                search_op,
                {"inqryDiv": 1, **search_params, search_param_name: kw},
                max_pages=min(collector.max_pages, 3),
                max_records=remaining,
            )
            if hard_error:
                break
            _ingest(rows, search_op, kw)

        # If keyword-first path (prefer_list_first False) and still empty, list fallback.
        if not use_list_first and not by_key and not hard_error:
            rows = _paginate(
                list_op,
                {"inqryDiv": 1, **list_params},
                max_pages=collector.max_pages,
                max_records=collector.max_records,
            )
            if not hard_error:
                _ingest(rows, list_op)
                warnings.append("keyword search empty; used list_operation window fallback")

    raw_records = list(by_key.values())
    raw_item_count = len(raw_records)
    mice_hits = (
        [r for r in raw_records if _title_match(r, keywords, title_fields)]
        if keywords
        else list(raw_records)
    )
    mice_after = len(mice_hits)
    # Never discard raw API rows here — MICE relevance is applied downstream.
    records = raw_records[: collector.max_records]
    if keywords and raw_item_count and mice_after == 0:
        warnings.append(
            f"MICE title filter matched 0 of {raw_item_count} fetched records "
            "(raw retained; mice_relevant applied at link/summary)"
        )

    limit_reached = (not hard_error) and (
        len(records) >= collector.max_records or max_pages_reached
    )
    if limit_reached:
        warnings.append(
            f"max_records/max_pages limit reached "
            f"(max_records={collector.max_records}, max_pages={collector.max_pages})"
        )

    out_path = Path(collector.raw_dir) / raw_filename
    write_jsonl(out_path, [] if hard_error else records)

    total_reported = _max_total_count(page_meta)
    status = finalize_collect_status(
        record_count=0 if hard_error else len(records),
        page_statuses=page_statuses,
        hard_error=hard_error,
        total_count_reported=total_reported,
        raw_item_count=0 if hard_error else raw_item_count,
        limit_reached=limit_reached and not hard_error and bool(records),
    )
    success = status in {OK, OK_EMPTY, OK_TRUNCATED, FILTERED_ALL} or (
        status not in AUTH_OR_PARAM_ERRORS and bool(records) and not hard_error
    )

    remaining_estimated = None
    if isinstance(total_reported, int) and total_reported > len(records):
        remaining_estimated = max(0, total_reported - len(records))

    return ProcurementCollectResult(
        stage=collector.stage,
        success=success,
        status=status,
        fetched_count=raw_item_count,
        parsed_count=0 if hard_error else len(records),
        error_count=len(errors),
        raw_output_path=str(out_path),
        errors=errors,
        warnings=warnings,
        request_log=safe_request_log(
            collector.http.request_log if collector.http else [], collector.service_key
        ),
        metadata={
            "auth_present": True,
            "smoke_test": collector.smoke_test,
            "window": list_window,
            "search_window": search_window,
            "max_records": collector.max_records,
            "max_pages": collector.max_pages,
            "total_count_reported": total_reported,
            "fetched_count": raw_item_count,
            "parsed_count": 0 if hard_error else len(records),
            "raw_item_count_before_mice_filter": raw_item_count,
            "mice_filter_after_count": 0 if hard_error else mice_after,
            "limit_reached": limit_reached and not hard_error,
            "collection_complete": not (limit_reached and not hard_error),
            "remaining_estimated": remaining_estimated,
            "max_pages_reached": max_pages_reached,
            "pages": page_meta[:40],
            "dataset_url": openapi.get("dataset_url"),
        },
    )
