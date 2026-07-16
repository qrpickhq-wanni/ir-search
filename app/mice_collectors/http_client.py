"""Shared HTTP client for MICE collectors (curl_cffi, polite delay, retries)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from curl_cffi import requests as curl_requests


@dataclass
class HttpResponse:
    url: str
    status_code: int
    content: bytes
    text: str
    headers: dict[str, str]
    elapsed_ms: float
    attempt: int
    content_type: str


@dataclass
class PoliteHttpClient:
    user_agent: str
    timeout_seconds: float = 20.0
    delay_seconds: float = 0.5
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0
    max_requests: int = 120
    request_log: list[dict[str, Any]] = field(default_factory=list)
    _last_request_at: float = 0.0
    _request_count: int = 0

    def __post_init__(self) -> None:
        self._session = curl_requests.Session()

    def remaining_budget(self) -> int:
        return max(0, self.max_requests - self._request_count)

    def _wait(self) -> None:
        if self._last_request_at <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expect_content_types: tuple[str, ...] | None = None,
        allow_empty: bool = False,
    ) -> HttpResponse:
        if self._request_count >= self.max_requests:
            raise RuntimeError(f"max_requests exceeded ({self.max_requests}) for {url}")

        base_headers = {
            "User-Agent": self.user_agent,
            "Accept": "*/*",
        }
        if headers:
            base_headers.update(headers)

        last_exc: Exception | None = None
        attempts = self.max_retries + 1
        for attempt in range(1, attempts + 1):
            self._wait()
            started = time.monotonic()
            try:
                resp = self._session.request(
                    method.upper(),
                    url,
                    params=params,
                    data=data,
                    headers=base_headers,
                    timeout=self.timeout_seconds,
                    impersonate="chrome124",
                    allow_redirects=True,
                )
                elapsed_ms = (time.monotonic() - started) * 1000
                self._last_request_at = time.monotonic()
                self._request_count += 1
                ctype = (resp.headers.get("content-type") or "").lower()
                entry = {
                    "method": method.upper(),
                    "url": str(resp.url) if getattr(resp, "url", None) else url,
                    "status_code": resp.status_code,
                    "content_type": ctype,
                    "bytes": len(resp.content or b""),
                    "attempt": attempt,
                    "elapsed_ms": round(elapsed_ms, 1),
                    "host": urlparse(url).netloc,
                }
                self.request_log.append(entry)

                if resp.status_code in (429, 403) or resp.status_code >= 500:
                    if attempt < attempts:
                        time.sleep(self.retry_backoff_seconds * attempt)
                        continue
                    raise RuntimeError(
                        f"HTTP {resp.status_code} for {url} after {attempt} attempts"
                    )

                if expect_content_types:
                    if not any(t in ctype for t in expect_content_types):
                        # Some Korean public APIs mislabel charset but return valid body.
                        body_ok = bool(resp.content) or allow_empty
                        if not body_ok:
                            raise RuntimeError(
                                f"Unexpected content-type {ctype!r} for {url}"
                            )

                text = ""
                try:
                    text = resp.text
                except Exception:
                    text = (resp.content or b"").decode("utf-8", errors="replace")

                return HttpResponse(
                    url=entry["url"],
                    status_code=resp.status_code,
                    content=resp.content or b"",
                    text=text,
                    headers={k: v for k, v in resp.headers.items()},
                    elapsed_ms=elapsed_ms,
                    attempt=attempt,
                    content_type=ctype,
                )
            except Exception as exc:  # noqa: BLE001 — surface per-attempt, then raise
                last_exc = exc
                self._last_request_at = time.monotonic()
                if attempt < attempts:
                    time.sleep(self.retry_backoff_seconds * attempt)
                    continue
                raise
        raise RuntimeError(f"request failed for {url}: {last_exc}")

    def get(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("POST", url, **kwargs)
