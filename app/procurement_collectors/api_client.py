"""data.go.kr OpenAPI client for G2B procurement services."""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode, urlsplit

from app.mice_collectors.http_client import PoliteHttpClient
from app.procurement_collectors.base import resolve_service_key
from app.procurement_collectors.openapi_status import (
    HTTP_ERROR,
    PARSING_ERROR,
    SERVICE_KEY_INVALID,
    TIMEOUT,
    classify_exception,
    classify_result_code_msg,
    mask_service_key_in_text,
    mask_service_key_in_url,
    parse_xml_error_payload,
    sanitize_service_key,
)


def _as_item_list(body: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not body:
        return []
    items = body.get("items")
    if items is None:
        return []
    if isinstance(items, list):
        out: list[dict[str, Any]] = []
        for it in items:
            if isinstance(it, dict) and "item" in it:
                nested = it["item"]
                if isinstance(nested, dict):
                    out.append(nested)
                elif isinstance(nested, list):
                    out.extend(x for x in nested if isinstance(x, dict))
            elif isinstance(it, dict):
                out.append(it)
        return out
    if isinstance(items, dict):
        item = items.get("item")
        if item is None:
            if any(k for k in items if k != "item"):
                pass
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
        raw_key = service_key if service_key is not None else resolve_service_key(config)
        self.service_key, self.key_meta = sanitize_service_key(raw_key)
        openapi = config.get("openapi") or {}
        self.base_host = str(openapi.get("base_host") or "https://apis.data.go.kr").rstrip("/")
        self.response_type = str(openapi.get("type") or "json")

    @property
    def has_key(self) -> bool:
        return bool(self.service_key)

    def build_url(self, service_path: str, operation: str) -> str:
        path = service_path if service_path.startswith("/") else f"/{service_path}"
        return f"{self.base_host}{path}/{operation}"

    def _error_page(
        self,
        *,
        safe_url: str,
        page_no: int,
        num_of_rows: int,
        safe_query: dict[str, Any],
        error_status: str,
        status_code: int | None = None,
        result_code: str | None = None,
        result_msg: str | None = None,
        content_type: str | None = None,
        body_prefix: str | None = None,
        exception_type: str | None = None,
        timed_out: bool = False,
        redirected: bool | None = None,
        retry_count: int = 0,
        passed_via: str | None = None,
    ) -> dict[str, Any]:
        return {
            "url": safe_url,
            "status_code": status_code,
            "payload": None,
            "items": [],
            "total_count": None,
            "pageNo": page_no,
            "numOfRows": num_of_rows,
            "result_code": result_code,
            "result_msg": mask_service_key_in_text(result_msg, self.service_key) if result_msg else None,
            "safe_query": safe_query,
            "error_status": error_status,
            "content_type": content_type,
            "body_prefix": mask_service_key_in_text(body_prefix, self.service_key) if body_prefix else None,
            "exception_type": exception_type,
            "timed_out": timed_out,
            "redirected": redirected,
            "retry_count": retry_count,
            "passed_via": passed_via,
            "service_key_parameter_count": 1,
            "key_meta": {
                k: self.key_meta.get(k)
                for k in (
                    "key_length",
                    "has_percent_encoding",
                    "has_leading_or_trailing_whitespace",
                    "is_ascii",
                    "non_ascii_count",
                    "shape_error",
                )
            },
        }

    def get_page(
        self,
        *,
        service_path: str,
        operation: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.service_key:
            raise RuntimeError("DATA_GO_KR_SERVICE_KEY (or alt) is required for live OpenAPI calls")

        page_no = int(params.get("pageNo", 1))
        num_of_rows = int(params.get("numOfRows", 100))
        other = {
            "type": self.response_type,
            "pageNo": page_no,
            "numOfRows": num_of_rows,
            **{k: v for k, v in params.items() if k not in {"pageNo", "numOfRows"} and v is not None},
        }
        # Drop any caller-supplied serviceKey to avoid duplicates
        other = {k: v for k, v in other.items() if k.lower() != "servicekey"}

        base_url = self.build_url(service_path, operation)
        safe_query = {
            "serviceKey": "***REDACTED***",
            **{k: v for k, v in other.items()},
        }
        safe_url = mask_service_key_in_url(f"{base_url}?pageNo={page_no}", self.service_key)

        if self.key_meta.get("shape_error") == "NON_ASCII":
            return self._error_page(
                safe_url=safe_url,
                page_no=page_no,
                num_of_rows=num_of_rows,
                safe_query=safe_query,
                error_status=SERVICE_KEY_INVALID,
                result_msg=(
                    "SERVICE_KEY contains non-ASCII characters "
                    "(likely Hangul IME corruption). Re-copy Encoding/Decoding key "
                    "from data.go.kr with English input mode."
                ),
                passed_via="rejected_before_request",
            )

        # Encoding keys already contain %XX — append to URL without re-encoding.
        # Decoding keys (no %) go through params so the HTTP client encodes once.
        if self.key_meta.get("has_percent_encoding"):
            qs = urlencode({k: str(v) for k, v in other.items()})
            request_url = f"{base_url}?serviceKey={self.service_key}&{qs}"
            request_params = None
            passed_via = "url"
        else:
            request_url = base_url
            request_params = {"serviceKey": self.service_key, **other}
            passed_via = "params"

        try:
            resp = self.http.get(
                request_url,
                params=request_params,
                headers={"Accept": "application/json, application/xml, text/xml, */*"},
                expect_content_types=("json", "xml", "text"),
                allow_empty=True,
            )
        except Exception as exc:  # noqa: BLE001
            err = classify_exception(exc)
            retries_raw = getattr(self.http, "max_retries", 0)
            try:
                retries = int(retries_raw)
            except (TypeError, ValueError):
                retries = 0
            return self._error_page(
                safe_url=safe_url,
                page_no=page_no,
                num_of_rows=num_of_rows,
                safe_query=safe_query,
                error_status=err,
                result_msg=mask_service_key_in_text(str(exc), self.service_key),
                exception_type=type(exc).__name__,
                timed_out=(err == TIMEOUT),
                retry_count=max(0, retries),
                passed_via=passed_via,
            )

        for entry in self.http.request_log[-3:]:
            if isinstance(entry, dict) and entry.get("url"):
                entry["url"] = mask_service_key_in_url(str(entry["url"]), self.service_key)

        text = resp.text or ""
        safe_resp_url = mask_service_key_in_url(str(resp.url), self.service_key)
        http_status = int(resp.status_code)
        ctype = getattr(resp, "content_type", None) or (resp.headers or {}).get("content-type")
        body_prefix = text[:500]
        redirected = False
        try:
            redirected = urlsplit(str(resp.url)).path.rstrip("/") != urlsplit(base_url).path.rstrip("/")
        except Exception:  # noqa: BLE001
            redirected = None
        retry_count = max(0, int(getattr(resp, "attempt", 1)) - 1)

        # Count serviceKey occurrences in final URL (masked copy)
        sk_count = sum(
            1
            for k, _ in __import__("urllib.parse", fromlist=["parse_qsl"]).parse_qsl(
                urlsplit(str(resp.url)).query, keep_blank_values=True
            )
            if k.lower() == "servicekey"
        )

        if http_status >= 400:
            xml_err = parse_xml_error_payload(text) if text.lstrip().startswith("<") else {}
            code = xml_err.get("result_code")
            msg = xml_err.get("result_msg") or text[:200]
            err = classify_result_code_msg(code, msg, http_status=http_status) or HTTP_ERROR
            page = self._error_page(
                safe_url=safe_resp_url,
                page_no=page_no,
                num_of_rows=num_of_rows,
                safe_query=safe_query,
                error_status=err,
                status_code=http_status,
                result_code=code,
                result_msg=str(msg),
                content_type=ctype,
                body_prefix=body_prefix,
                redirected=redirected,
                retry_count=retry_count,
                passed_via=passed_via,
            )
            page["service_key_parameter_count"] = sk_count
            return page

        if text.lstrip().startswith("<"):
            xml_err = parse_xml_error_payload(text)
            err = classify_result_code_msg(
                xml_err.get("result_code"),
                xml_err.get("result_msg"),
                http_status=http_status,
            )
            if err or xml_err.get("is_xml_error"):
                page = self._error_page(
                    safe_url=safe_resp_url,
                    page_no=page_no,
                    num_of_rows=num_of_rows,
                    safe_query=safe_query,
                    error_status=err or PARSING_ERROR,
                    status_code=http_status,
                    result_code=xml_err.get("result_code"),
                    result_msg=str(xml_err.get("result_msg") or "XML_ERROR"),
                    content_type=ctype,
                    body_prefix=body_prefix,
                    redirected=redirected,
                    retry_count=retry_count,
                    passed_via=passed_via,
                )
                page["service_key_parameter_count"] = sk_count
                return page

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            page = self._error_page(
                safe_url=safe_resp_url,
                page_no=page_no,
                num_of_rows=num_of_rows,
                safe_query=safe_query,
                error_status=PARSING_ERROR,
                status_code=http_status,
                result_msg=text[:200],
                content_type=ctype,
                body_prefix=body_prefix,
                redirected=redirected,
                retry_count=retry_count,
                passed_via=passed_via,
            )
            page["service_key_parameter_count"] = sk_count
            return page

        if not isinstance(payload, dict) or not isinstance(payload.get("response"), dict):
            page = self._error_page(
                safe_url=safe_resp_url,
                page_no=page_no,
                num_of_rows=num_of_rows,
                safe_query=safe_query,
                error_status=PARSING_ERROR,
                status_code=http_status,
                result_msg="RESPONSE_ENVELOPE_MISSING",
                content_type=ctype,
                body_prefix=body_prefix,
                redirected=redirected,
                retry_count=retry_count,
                passed_via=passed_via,
            )
            page["service_key_parameter_count"] = sk_count
            page["payload_top_keys"] = list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
            return page

        result_code = self.extract_result_code(payload)
        result_msg = self.extract_result_msg(payload)
        if result_code is None and result_msg is None:
            # Valid JSON but missing OpenAPI header — not a true empty result.
            page = self._error_page(
                safe_url=safe_resp_url,
                page_no=page_no,
                num_of_rows=num_of_rows,
                safe_query=safe_query,
                error_status=PARSING_ERROR,
                status_code=http_status,
                result_msg="RESULT_HEADER_MISSING",
                content_type=ctype,
                body_prefix=body_prefix,
                redirected=redirected,
                retry_count=retry_count,
                passed_via=passed_via,
            )
            page["service_key_parameter_count"] = sk_count
            return page

        err = classify_result_code_msg(result_code, result_msg, http_status=http_status)
        items = self.extract_items(payload) if not err else []
        return {
            "url": safe_resp_url,
            "status_code": http_status,
            "payload": payload if not err else None,
            "items": items,
            "total_count": self.extract_total(payload),
            "pageNo": page_no,
            "numOfRows": num_of_rows,
            "result_code": result_code,
            "result_msg": mask_service_key_in_text(result_msg, self.service_key) if result_msg else None,
            "safe_query": safe_query,
            "error_status": err,
            "content_type": ctype,
            "body_prefix": None if not err else mask_service_key_in_text(body_prefix, self.service_key),
            "exception_type": None,
            "timed_out": False,
            "redirected": redirected,
            "retry_count": retry_count,
            "passed_via": passed_via,
            "service_key_parameter_count": sk_count,
            "key_meta": {
                k: self.key_meta.get(k)
                for k in (
                    "key_length",
                    "has_percent_encoding",
                    "has_leading_or_trailing_whitespace",
                    "is_ascii",
                    "non_ascii_count",
                    "shape_error",
                )
            },
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
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], str | None]:
        """Return rows, page_meta, error_messages, hard_error_status."""
        rows: list[dict[str, Any]] = []
        page_meta: list[dict[str, Any]] = []
        errors: list[str] = []
        hard_error: str | None = None

        for page in range(1, max_pages + 1):
            if len(rows) >= max_records:
                break
            params = {**base_params, "pageNo": page, "numOfRows": num_of_rows}
            page_result = self.get_page(
                service_path=service_path,
                operation=operation,
                params=params,
            )
            err_status = page_result.get("error_status")
            meta = {
                "operation": operation,
                "pageNo": page_result.get("pageNo"),
                "numOfRows": page_result.get("numOfRows"),
                "httpStatus": page_result.get("status_code"),
                "count": len(page_result.get("items") or []),
                "totalCount": page_result.get("total_count"),
                "resultCode": page_result.get("result_code"),
                "resultMsg": page_result.get("result_msg"),
                "errorStatus": err_status,
                "url": page_result.get("url"),
                "contentType": page_result.get("content_type"),
                "bodyPrefix": page_result.get("body_prefix"),
                "exceptionType": page_result.get("exception_type"),
                "timedOut": page_result.get("timed_out"),
                "redirected": page_result.get("redirected"),
                "retryCount": page_result.get("retry_count"),
                "passedVia": page_result.get("passed_via"),
                "serviceKeyParameterCount": page_result.get("service_key_parameter_count"),
                "keyMeta": page_result.get("key_meta"),
            }
            page_meta.append(meta)

            if err_status:
                hard_error = err_status
                errors.append(
                    f"{operation} page={page} status={err_status} "
                    f"http={page_result.get('status_code')} "
                    f"resultCode={page_result.get('result_code')} "
                    f"msg={page_result.get('result_msg')}"
                )
                break

            items = page_result.get("items") or []
            if not items:
                break
            for it in items:
                rows.append(it)
                if len(rows) >= max_records:
                    break
            total = page_result.get("total_count")
            if isinstance(total, int) and page * num_of_rows >= total:
                break

        return rows[:max_records], page_meta, errors, hard_error
