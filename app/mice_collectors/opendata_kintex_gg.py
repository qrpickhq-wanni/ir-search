"""Gyeonggi open-data KINTEX schedule collector.

Uses only registry-linked portals:
- https://www.data.go.kr/data/15119881/fileData.do
- https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=TM03IWAWFH17G6VM827729982969&infSeq=1

Optional OpenAPI (requires operator-confirmed service name + key):
- GG_OPENAPI_KEY
- GG_KINTEX_OPENAPI_SERVICE  (path segment under https://openapi.gg.go.kr/)
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
from typing import Any
from urllib.parse import urlencode

from app.io_utils import write_jsonl
from app.mice_collectors.base import CollectResult, MiceCollector
from app.mice_collectors.http_client import PoliteHttpClient


PUBLIC_DATA_PK = "15119881"
# Value observed on the public fileData.do page (hidden input publicDataDetailPk).
PUBLIC_DATA_DETAIL_PK = "uddi:ddfce0ce-eb4d-4330-a8c2-d1b3e21a5d40"
GG_INF_ID = "TM03IWAWFH17G6VM827729982969"
OPENAPI_BASE = "https://openapi.gg.go.kr"


def _rows_from_csv_bytes(content: bytes) -> list[dict[str, Any]]:
    # Try utf-8-sig then cp949 (common for Korean public CSV)
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = content.decode("utf-8", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows: list[dict[str, Any]] = []
    for row in reader:
        cleaned = {str(k).strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
        if any(cleaned.values()):
            rows.append(cleaned)
    return rows


def _pick(row: dict[str, Any], *names: str) -> Any:
    lower = {str(k).strip().casefold(): v for k, v in row.items()}
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
        v = lower.get(name.casefold())
        if v not in (None, ""):
            return v
    # fuzzy contains
    for key, val in row.items():
        k = str(key)
        for name in names:
            if name in k and val not in (None, ""):
                return val
    return None


class OpendataKintexGgCollector(MiceCollector):
    source_id = "opendata_kintex_gg"

    def validate_configuration(self) -> list[str]:
        warnings: list[str] = []
        key = os.environ.get("GG_OPENAPI_KEY")
        svc = os.environ.get("GG_KINTEX_OPENAPI_SERVICE")
        if not key or not svc:
            warnings.append(
                "GG_OPENAPI_KEY and/or GG_KINTEX_OPENAPI_SERVICE unset. "
                "data.go.kr hosts a link to the GG Sheet UI rather than a direct CSV blob; "
                "without OpenAPI credentials this source may be PARTIAL. "
                "Issue a key at https://data.gg.go.kr/portal/openapi/insertApikeyPage.do "
                "and set GG_KINTEX_OPENAPI_SERVICE to the Sheet OpenAPI service name shown "
                "on the KINTEX dataset page."
            )
        return warnings

    def _try_openapi(self, client: PoliteHttpClient) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        warnings: list[str] = []
        key = os.environ.get("GG_OPENAPI_KEY")
        svc = os.environ.get("GG_KINTEX_OPENAPI_SERVICE")
        if not key or not svc:
            return rows, errors, warnings
        # Service name must come from env (confirmed on GG Sheet Open API popup) — do not invent.
        if not re.fullmatch(r"[A-Za-z0-9_]+", svc):
            errors.append("GG_KINTEX_OPENAPI_SERVICE has invalid characters")
            return rows, errors, warnings
        url = f"{OPENAPI_BASE}/{svc}"
        page = 1
        while len(rows) < self.max_records and page <= self.max_pages:
            params = {
                "KEY": key,
                "Type": "json",
                "pIndex": str(page),
                "pSize": "100",
            }
            try:
                resp = client.get(url, params=params, expect_content_types=("json", "text/"))
                payload = json.loads(resp.text)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"OpenAPI page {page}: {exc}")
                break
            # Gyeonggi OpenAPI commonly wraps as {ServiceName: [{head:...},{row:[]}]}
            block = payload.get(svc) if isinstance(payload, dict) else None
            if block is None and isinstance(payload, dict):
                # try first list-like value
                for v in payload.values():
                    if isinstance(v, list):
                        block = v
                        break
            if not isinstance(block, list):
                errors.append(f"OpenAPI unexpected payload keys: {list(payload)[:8] if isinstance(payload, dict) else type(payload)}")
                break
            batch: list[dict[str, Any]] = []
            for part in block:
                if not isinstance(part, dict):
                    continue
                if "row" in part and isinstance(part["row"], list):
                    batch.extend([x for x in part["row"] if isinstance(x, dict)])
                elif "head" in part:
                    continue
                else:
                    batch.append(part)
            if not batch:
                break
            for item in batch:
                rows.append(
                    self.stamp_raw(
                        item,
                        f"{url}?{urlencode({'Type': 'json', 'pIndex': page})}",
                    )
                )
                if len(rows) >= self.max_records:
                    break
            if len(batch) < 100:
                break
            page += 1
        if rows:
            warnings.append(f"Collected via GG OpenAPI service={svc} pages={page}")
        return rows, errors, warnings

    def collect(self) -> CollectResult:
        warnings = self.validate_configuration()
        errors: list[str] = []
        list_urls = list(self.registry_entry.get("list_urls") or [])
        data_go = next((u for u in list_urls if "data.go.kr" in u), list_urls[0] if list_urls else None)
        gg_url = next((u for u in list_urls if "data.gg.go.kr" in u), None)

        client = PoliteHttpClient(
            user_agent=self.user_agent,
            timeout_seconds=self.timeout_seconds,
            delay_seconds=self.delay_seconds,
            max_retries=self.max_retries,
            retry_backoff_seconds=self.retry_backoff_seconds,
            max_requests=self.max_requests,
        )

        raw_rows: list[dict[str, Any]] = []
        meta: dict[str, Any] = {**self.get_source_metadata()}

        # 1) Optional documented OpenAPI path (env-gated)
        api_rows, api_errs, api_warns = self._try_openapi(client)
        errors.extend(api_errs)
        warnings.extend(api_warns)
        raw_rows.extend(api_rows)

        # 2) data.go.kr metadata / download probe (no invented download URL)
        if not raw_rows and data_go:
            try:
                page = client.get(data_go, expect_content_types=("html", "text/", "json"))
                meta["data_go_status"] = page.status_code
                # catalog json companion (public)
                catalog = "https://www.data.go.kr/catalog/15119881/fileData.json"
                cat = client.get(catalog, expect_content_types=("json", "text/"))
                try:
                    meta["catalog"] = json.loads(cat.text)
                except json.JSONDecodeError:
                    warnings.append("catalog JSON parse failed")

                # Official AJAX used by portal download button (observed on public page JS)
                prep = client.post(
                    "https://www.data.go.kr/tcs/dss/selectFileDataDownload.do",
                    data={
                        "publicDataPk": PUBLIC_DATA_PK,
                        "publicDataDetailPk": PUBLIC_DATA_DETAIL_PK,
                    },
                    headers={
                        "Referer": data_go,
                        "X-Requested-With": "XMLHttpRequest",
                        "Origin": "https://www.data.go.kr",
                    },
                    expect_content_types=("json", "text/"),
                )
                prep_json = json.loads(prep.text)
                ds = prep_json.get("dataSetFileDetailInfo") or {}
                meta["download_prep"] = {
                    "status": prep_json.get("status"),
                    "atchFileId": prep_json.get("atchFileId"),
                    "atachFileYn": ds.get("atachFileYn"),
                    "success": ds.get("success"),
                    "dataUrl": ds.get("dataUrl"),
                    "dataNm": ds.get("dataNm"),
                    "atchFileExtsn": ds.get("atchFileExtsn"),
                    "atchFileCo": ds.get("atchFileCo"),
                }
                # If portal ever returns a file id, follow only when URL is present in response
                download_url = None
                for key in ("downloadUrl", "dataUrl"):
                    cand = ds.get(key) or (prep_json.get("fileDataRegistVO") or {}).get(key)
                    if isinstance(cand, str) and cand.startswith("http") and cand.lower().endswith((".csv", ".txt", ".xlsx")):
                        download_url = cand
                        break
                if download_url:
                    file_resp = client.get(download_url)
                    parsed = _rows_from_csv_bytes(file_resp.content)
                    for row in parsed[: self.max_records]:
                        raw_rows.append(self.stamp_raw(row, download_url))
                    warnings.append(f"CSV downloaded from portal-provided URL ({len(raw_rows)} rows)")
                else:
                    warnings.append(
                        "data.go.kr download prep reports no attachable CSV "
                        f"(atachFileYn={ds.get('atachFileYn')}, atchFileId={prep_json.get('atchFileId')}). "
                        f"Provision form redirects to GG Sheet: {ds.get('dataUrl') or gg_url}"
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"data.go.kr probe failed: {exc}")

        # 3) GG Sheet page reachability (not scraped via invented XHR)
        if gg_url and client.remaining_budget() > 0:
            try:
                gg = client.get(gg_url, expect_content_types=("html", "text/"), allow_empty=True)
                meta["gg_status"] = gg.status_code
                meta["gg_bytes"] = len(gg.content)
                if "KINTEX" in gg.text or "킨텍스" in gg.text:
                    warnings.append(
                        "GG Sheet HTML shell reachable, but grid/CSV is client-rendered "
                        "(IBSheet). Browser automation is out of MVP scope; use OpenAPI env vars."
                    )
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"GG page reachability warning: {exc}")

        out_path = self.raw_dir / f"{self.source_id}.jsonl"
        write_jsonl(out_path, raw_rows)

        if raw_rows:
            status = "OK"
            success = True
        else:
            status = "PARTIAL"
            success = False
            errors.append(
                "No KINTEX open-data rows retrieved via HTTP. "
                "Set GG_OPENAPI_KEY and GG_KINTEX_OPENAPI_SERVICE after confirming the "
                "Sheet OpenAPI service name on the GG dataset page, then re-run."
            )

        return CollectResult(
            source_id=self.source_id,
            success=success,
            status=status,
            fetched_count=len(raw_rows),
            parsed_count=len(raw_rows),
            error_count=len(errors),
            raw_output_path=str(out_path),
            errors=errors,
            warnings=warnings,
            request_log=client.request_log,
            metadata=meta,
        )

    def normalize_source_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        title = _pick(raw, "행사명", "행사(전시회)명", "전시회명", "TITLE", "title", "eventNm")
        period = _pick(raw, "기간", "행사기간", "PERIOD", "period")
        venue = _pick(raw, "장소", "행사장소", "PLACE", "venue", "location")
        host = _pick(raw, "주최", "주최기관", "주최주관", "HOST", "organizer")
        organizer = _pick(raw, "주관", "주관기관", "SUPERVISION")
        phone = _pick(raw, "전화", "전화번호", "전화팩스", "TEL", "phone", "연락처")
        homepage = _pick(raw, "홈페이지", "행사(전시회) 홈페이지", "HOMEPAGE", "url", "URL")
        start = _pick(raw, "시작일", "시작일자", "START_DATE", "beginDe")
        end = _pick(raw, "종료일", "종료일자", "END_DATE", "endDe")
        return {
            "source_event_id": _pick(raw, "연번", "번호", "SEQ", "id"),
            "title": title,
            "title_en": _pick(raw, "영문행사명", "TITLE_EN"),
            "start_date_raw": start,
            "end_date_raw": end,
            "date_text": period,
            "venue_name": venue or "KINTEX",
            "venue_address": None,
            "city": "고양",
            "region": "경기",
            "country": "KR",
            "location_raw": venue,
            "host_raw": host,
            "organizer_raw": organizer,
            "operator_raw": None,
            "pco_raw": None,
            "category_raw": _pick(raw, "유형", "분류", "category"),
            "homepage": homepage,
            "official_event_url": homepage,
            "source_url": raw.get("_source_url"),
            "inquiry_raw": phone,
            "contact_email": None,
            "contact_phone": phone if phone and "@" not in str(phone) else None,
            "contact_department": None,
            "contact_name": None,
            "description_summary": None,
            "collected_at": raw.get("_collected_at"),
            "needs_host_role_check": bool(host and ("주최" in str(host) and "주관" in str(host))),
        }
