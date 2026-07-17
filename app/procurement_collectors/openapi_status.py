"""Classify data.go.kr OpenAPI / HTTP outcomes for G2B collectors."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from xml.etree import ElementTree as ET


OK = "OK"
OK_EMPTY = "OK_EMPTY"
OK_TRUNCATED = "OK_TRUNCATED"
FILTERED_ALL = "FILTERED_ALL"
PARTIAL_EXPECTED = "PARTIAL_EXPECTED"
SERVICE_NOT_APPROVED = "SERVICE_NOT_APPROVED"
SERVICE_KEY_INVALID = "SERVICE_KEY_INVALID"
SERVICE_KEY_ENCODING_ERROR = "SERVICE_KEY_ENCODING_ERROR"
INVALID_PARAMETER = "INVALID_PARAMETER"
ENDPOINT_NOT_FOUND = "ENDPOINT_NOT_FOUND"
ACCESS_DENIED = "ACCESS_DENIED"
RATE_LIMITED = "RATE_LIMITED"
TIMEOUT = "TIMEOUT"
TLS_ERROR = "TLS_ERROR"
PARSING_ERROR = "PARSING_ERROR"
HTTP_4XX = "HTTP_4XX"
HTTP_5XX = "HTTP_5XX"
HTTP_ERROR = "HTTP_ERROR"
PARTIAL_UNEXPECTED = "PARTIAL_UNEXPECTED"

REDACTED = "***REDACTED***"

# Statuses that mean "empty but healthy"
EMPTY_OK = frozenset({OK_EMPTY})

# Auth / approval / parameter failures — must NOT be reported as OK_EMPTY
AUTH_OR_PARAM_ERRORS = frozenset(
    {
        SERVICE_NOT_APPROVED,
        SERVICE_KEY_INVALID,
        SERVICE_KEY_ENCODING_ERROR,
        INVALID_PARAMETER,
        ACCESS_DENIED,
    }
)

TRANSPORT_OR_HTTP_ERRORS = frozenset(
    {
        ENDPOINT_NOT_FOUND,
        RATE_LIMITED,
        TIMEOUT,
        TLS_ERROR,
        PARSING_ERROR,
        HTTP_4XX,
        HTTP_5XX,
        HTTP_ERROR,
    }
)

# Soft outcomes that are not transport failures
SOFT_NONEMPTY = frozenset({OK, OK_TRUNCATED, FILTERED_ALL})

NORMAL_RESULT_CODES = frozenset({"00", "0", "INFO-000", "NORMAL"})


def mask_service_key_in_text(text: str | None, key: str | None = None) -> str:
    """Redact serviceKey query values and optional raw key material."""
    if not text:
        return ""
    out = str(text)
    out = re.sub(
        r"(?i)(serviceKey=)([^&\s\"']+)",
        rf"\1{REDACTED}",
        out,
    )
    if key and key in out:
        out = out.replace(key, REDACTED)
    return out


def mask_service_key_in_url(url: str | None, key: str | None = None) -> str:
    if not url:
        return ""
    try:
        parts = urlparse(str(url))
        q = []
        for k, v in parse_qsl(parts.query, keep_blank_values=True):
            if k.lower() == "servicekey":
                q.append((k, REDACTED))
            elif key and v == key:
                q.append((k, REDACTED))
            else:
                q.append((k, v))
        return urlunparse(parts._replace(query=urlencode(q, safe="*")))
    except Exception:  # noqa: BLE001
        return mask_service_key_in_text(url, key)


def sanitize_service_key(raw: str | None) -> tuple[str | None, dict[str, Any]]:
    """Strip accidental wrapping only. Never decode/re-encode key bytes."""
    meta: dict[str, Any] = {
        "key_length": 0,
        "has_percent_encoding": False,
        "has_leading_or_trailing_whitespace": False,
        "had_surrounding_quotes": False,
        "has_newline": False,
        "is_ascii": True,
        "non_ascii_count": 0,
        "shape_error": None,
    }
    if raw is None:
        return None, meta
    original = str(raw)
    meta["has_leading_or_trailing_whitespace"] = original != original.strip()
    meta["has_newline"] = ("\n" in original or "\r" in original)
    key = original.strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in "'\"":
        meta["had_surrounding_quotes"] = True
        key = key[1:-1].strip()
    meta["key_length"] = len(key)
    meta["has_percent_encoding"] = "%" in key
    meta["is_ascii"] = key.isascii()
    meta["non_ascii_count"] = sum(1 for c in key if ord(c) > 127)
    if not key:
        meta["shape_error"] = "EMPTY"
        return None, meta
    if not key.isascii():
        # data.go.kr Encoding/Decoding keys are ASCII. Non-ASCII usually means
        # Hangul IME corruption or pasting the wrong clipboard contents.
        meta["shape_error"] = "NON_ASCII"
        return key, meta
    return key, meta


def classify_http_status(http_status: int | None) -> str | None:
    if http_status is None:
        return None
    if http_status == 401 or http_status == 403:
        return ACCESS_DENIED
    if http_status == 404:
        return ENDPOINT_NOT_FOUND
    if http_status == 429:
        return RATE_LIMITED
    if 400 <= http_status < 500:
        return HTTP_4XX
    if http_status >= 500:
        return HTTP_5XX
    return None


def classify_exception(exc: BaseException) -> str:
    name = type(exc).__name__
    msg = str(exc).upper()
    combined = f"{name} {msg}"
    if any(t in combined for t in ("TIMEOUT", "TIMED OUT", "DEADLINE")):
        return TIMEOUT
    if any(t in combined for t in ("SSL", "TLS", "CERTIFICATE", "CERT VERIFY")):
        return TLS_ERROR
    if "HTTP 401" in combined or "HTTP 403" in combined or "UNAUTHORIZED" in combined:
        return ACCESS_DENIED
    if "HTTP 404" in combined:
        return ENDPOINT_NOT_FOUND
    if "HTTP 429" in combined:
        return RATE_LIMITED
    if re.search(r"HTTP 5\d\d", combined):
        return HTTP_5XX
    if re.search(r"HTTP 4\d\d", combined):
        return HTTP_4XX
    return HTTP_ERROR


def classify_result_code_msg(
    result_code: str | None,
    result_msg: str | None,
    *,
    http_status: int | None = None,
) -> str | None:
    """Return an error status, or None when the OpenAPI result is normal."""
    http_err = classify_http_status(http_status)
    if http_err:
        # Prefer OpenAPI body classification when present (rare on 4xx plain text).
        code = str(result_code or "").strip().upper()
        msg = str(result_msg or "").strip().upper()
        if code or (msg and msg not in {"UNAUTHORIZED", "FORBIDDEN", "UNAUTHORIZED\n"}):
            body_err = _classify_body(code, msg)
            if body_err:
                return body_err
        return http_err

    return _classify_body(str(result_code or "").strip().upper(), str(result_msg or "").strip().upper())


def _classify_body(code: str, msg: str) -> str | None:
    combined = f"{code} {msg}"

    if code in NORMAL_RESULT_CODES or code == "":
        if not msg or "NORMAL" in msg:
            return None

    if any(
        t in combined
        for t in (
            "SERVICE_KEY_IS_NOT_REGISTERED",
            "SERVICE KEY IS NOT REGISTERED",
            "UNREGISTERED SERVICE KEY",
            "SERVICE NOT REGISTERED",
            "NOT APPROVED",
            "UNAUTHORIZED",
            "HTTP ERROR 401",
            "HTTP ERROR 403",
        )
    ) or code in {"30", "31", "32"}:
        if "ENCODING" in combined or "DECODE" in combined or "URL DECODER" in combined:
            return SERVICE_KEY_ENCODING_ERROR
        if "INVALID" in combined and "KEY" in combined:
            return SERVICE_KEY_INVALID
        if "UNAUTHORIZED" in combined or "FORBIDDEN" in combined:
            return ACCESS_DENIED
        return SERVICE_NOT_APPROVED

    if any(
        t in combined
        for t in (
            "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
            "SERVICE KEY IS NOT REGISTERED ERROR",
        )
    ):
        return SERVICE_NOT_APPROVED

    if any(
        t in combined
        for t in (
            "INVALID SERVICE KEY",
            "SERVICE_KEY_IS_INVALID",
            "DEADLINE EXPIRED",
            "KEY IS INVALID",
        )
    ):
        return SERVICE_KEY_INVALID

    if any(
        t in combined
        for t in (
            "URL DECODER",
            "ENCODING ERROR",
            "SERVICE_KEY_IS_NOT_UTF8",
            "DECODED AS",
        )
    ):
        return SERVICE_KEY_ENCODING_ERROR

    if any(
        t in combined
        for t in (
            "INVALID REQUEST PARAMETER",
            "INVALID_PARAMETER",
            "MANDATORY PARAMETER",
            "ERROR-400",
            "PARAMET",
        )
    ) or code in {"10", "11", "12", "22"}:
        return INVALID_PARAMETER

    if code and code not in NORMAL_RESULT_CODES:
        return PARTIAL_UNEXPECTED

    return None


def parse_xml_error_payload(text: str) -> dict[str, Any]:
    """Parse common data.go.kr XML error envelopes."""
    out: dict[str, Any] = {
        "result_code": None,
        "result_msg": None,
        "is_xml_error": False,
    }
    raw = (text or "").strip()
    if not raw.startswith("<"):
        return out
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        out["is_xml_error"] = True
        out["result_msg"] = "XML_PARSE_FAILED"
        return out

    tags: dict[str, str] = {}
    for el in root.iter():
        tag = el.tag.split("}")[-1] if isinstance(el.tag, str) else ""
        if el.text and str(el.text).strip():
            tags[tag.lower()] = str(el.text).strip()

    code = (
        tags.get("returnreasoncode")
        or tags.get("resultcode")
        or tags.get("errcode")
        or tags.get("err_code")
    )
    msg = (
        tags.get("returnauthmsg")
        or tags.get("errmsg")
        or tags.get("resultmsg")
        or tags.get("returnreason")
        or tags.get("err_msg")
    )
    out["result_code"] = code
    out["result_msg"] = msg
    out["is_xml_error"] = True
    return out


def finalize_collect_status(
    *,
    record_count: int,
    page_statuses: list[str | None],
    hard_error: str | None = None,
    total_count_reported: int | None = None,
    raw_item_count: int | None = None,
    limit_reached: bool = False,
) -> str:
    """Pick stage status. Auth/param errors never become OK_EMPTY.

    OK_EMPTY only when API succeeded and truly returned no items.
    totalCount>0 with parsed=0 → PARSING_ERROR (or FILTERED_ALL if raw items existed).
    """
    if hard_error:
        return hard_error
    for st in page_statuses:
        if st in AUTH_OR_PARAM_ERRORS or st in TRANSPORT_OR_HTTP_ERRORS:
            return st
    unexpected = [st for st in page_statuses if st == PARTIAL_UNEXPECTED]
    if record_count > 0 and unexpected:
        return PARTIAL_UNEXPECTED
    if record_count > 0:
        return OK_TRUNCATED if limit_reached else OK
    # record_count == 0
    if unexpected:
        return PARTIAL_UNEXPECTED
    raw = int(raw_item_count or 0)
    if raw > 0:
        return FILTERED_ALL
    if isinstance(total_count_reported, int) and total_count_reported > 0:
        return PARSING_ERROR
    return OK_EMPTY
