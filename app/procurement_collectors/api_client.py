"""data.go.kr OpenAPI client for G2B procurement services."""
from __future__ import annotations

import json
from typing import Any

from app.mice_collectors.http_client import PoliteHttpClient
from app.procurement_collectors.base import resolve_service_key


def _as_item_list(body: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not body:
        return []
    items = body.get("items")
    if items is None:
        return []
    if isinstance(items, list):
        out: list[dict[str, Any]] = []
        for it in items:
            if isinstance(it, dict) and "item" in it and isinstance(it["item"], dict):
                out.append(it["item"])
            elif isinstance(it, dict):
                out.append(it)
        return out
    if isinstance(items, dict):
        item = items.get("item")
        if item is None:
            return []
        if isinstance(item, list):
            return [x for x in item if isinstance(x, dict)]
        if isinstance(item, dict):
            return [item]
    return []


class DataGoKrClient:
    """Thin wrapper around PoliteHttpClient for PPS OpenAPI JSON responses."""

    def __init__(
        self,
        *,
        config: dict[str, Any],
        http: PoliteHttpClient,
        service_key: str | None = None,
    ) -> None:
        self.config = config
        self.http = http
        self.service_key = service_key if service_key is not None else resolve_service_key(config)
        openapi = config.get("openapi") or {}
        self.base_host = str(openapi.get("base_host") or "https://apis.data.go.kr").rstrip("/")
        self.response_type = str(openapi.get("type") or "json")

    @property
    def has_key(self) -> bool:
        return bool(self.service_key)

    def build_url(self, service_path: str, operation: str) -> str:
        path = service_path if service_path.startswith("/") else f"/{service_path}"
        return f"{self.base_host}{path}/{operation}"

    def get_page(
        self,
        *,
        service_path: str,
        operation: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.service_key:
            raise RuntimeError("DATA_GO_KR_SERVICE_KEY (or alt) is required for live OpenAPI calls")
        url = self.build_url(service_path, operation)
        q = {
            "serviceKey": self.service_key,
            "type": self.response_type,
            "pageNo": params.get("pageNo", 1),
            "numOfRows": params.get("numOfRows", 100),
            **{k: v for k, v in params.items() if k not in {"pageNo", "numOfRows"} and v is not None},
        }
        # data.go.kr expects serviceKey as query; do not log the key
        resp = self.http.get(
            url,
            params=q,
            headers={"Accept": "application/json"},
            expect_content_types=("json", "xml", "text"),
            allow_empty=True,
        )
        text = resp.text or ""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Non-JSON OpenAPI response for {operation}: status={resp.status_code} "
                f"ctype={resp.content_type!r} body[:200]={text[:200]!r}"
            ) from exc
        return {
            "url": resp.url,
            "status_code": resp.status_code,
            "payload": payload,
            "items": self.extract_items(payload),
            "total_count": self.extract_total(payload),
            "result_code": self.extract_result_code(payload),
            "result_msg": self.extract_result_msg(payload),
            "safe_query": {k: ("***" if k.lower() == "servicekey" else v) for k, v in q.items()},
        }

    @staticmethod
    def extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        resp = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(resp, dict):
            return []
        body = resp.get("body")
        if isinstance(body, dict):
            return _as_item_list(body)
        return []

    @staticmethod
    def extract_total(payload: dict[str, Any]) -> int | None:
        resp = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(resp, dict):
            return None
        body = resp.get("body")
        if not isinstance(body, dict):
            return None
        try:
            return int(body.get("totalCount"))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def extract_result_code(payload: dict[str, Any]) -> str | None:
        resp = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(resp, dict):
            return None
        header = resp.get("header") or {}
        if isinstance(header, dict):
            return str(header.get("resultCode") or "") or None
        return None

    @staticmethod
    def extract_result_msg(payload: dict[str, Any]) -> str | None:
        resp = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(resp, dict):
            return None
        header = resp.get("header") or {}
        if isinstance(header, dict):
            return str(header.get("resultMsg") or "") or None
        return None

    def paginate(
        self,
        *,
        service_path: str,
        operation: str,
        base_params: dict[str, Any],
        max_pages: int,
        max_records: int,
        num_of_rows: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        rows: list[dict[str, Any]] = []
        page_meta: list[dict[str, Any]] = []
        errors: list[str] = []
        for page in range(1, max_pages + 1):
            if len(rows) >= max_records:
                break
            params = {**base_params, "pageNo": page, "numOfRows": num_of_rows}
            try:
                page_result = self.get_page(
                    service_path=service_path,
                    operation=operation,
                    params=params,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{operation} page={page}: {exc}")
                break
            code = page_result.get("result_code")
            if code and code not in {"00", "0", "NORMAL", "INFO-000"}:
                # Some PPS APIs use resultCode 00; others INFO-000
                if str(code).upper() not in {"00", "0", "INFO-000"}:
                    errors.append(
                        f"{operation} page={page} resultCode={code} "
                        f"msg={page_result.get('result_msg')}"
                    )
                    # AUTH failures stop; empty result may still be code 00
                    if "SERVICE KEY" in str(page_result.get("result_msg") or "").upper():
                        break
                    if str(code) in {"99", "30", "31", "32"}:
                        break
            items = page_result.get("items") or []
            page_meta.append(
                {
                    "operation": operation,
                    "pageNo": page,
                    "count": len(items),
                    "totalCount": page_result.get("total_count"),
                    "resultCode": code,
                    "url": page_result.get("url"),
                }
            )
            if not items:
                break
            for it in items:
                rows.append(it)
                if len(rows) >= max_records:
                    break
            total = page_result.get("total_count")
            if isinstance(total, int) and page * num_of_rows >= total:
                break
        return rows[:max_records], page_meta, errors
