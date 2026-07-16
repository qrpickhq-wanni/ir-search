"""Songdo Convensia OpenAPI collector (documented public JSON endpoint)."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from app.io_utils import write_jsonl
from app.mice_collectors.base import CollectResult, MiceCollector
from app.mice_collectors.http_client import PoliteHttpClient

# Live responses consistently return at most this many rows per call (observed).
OBSERVED_ROW_CAP = 10


def _month_windows(start: date, end: date) -> list[tuple[date, date]]:
    out: list[tuple[date, date]] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        first = date(y, m, 1)
        if m == 12:
            nxt = date(y + 1, 1, 1)
        else:
            nxt = date(y, m + 1, 1)
        last = nxt - timedelta(days=1)
        ws = max(first, start)
        we = min(last, end)
        if ws <= we:
            out.append((ws, we))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _item_key(item: dict[str, Any]) -> tuple:
    return (
        str(item.get("event_nm") or "").strip(),
        str(item.get("st_event_dt") or "").strip(),
        str(item.get("end_event_dt") or "").strip(),
        str(item.get("location") or "").strip(),
    )


class SongdoConveniaCollector(MiceCollector):
    source_id = "songdo_convenia"

    def validate_configuration(self) -> list[str]:
        warnings: list[str] = []
        src_policy = (self.policy.get("sources") or {}).get(self.source_id) or {}
        if not src_policy.get("api_url"):
            warnings.append("policy.sources.songdo_convenia.api_url missing; using list_urls fallback")
        if not os.environ.get("SONGDO_OPENAPI_KEY"):
            warnings.append(
                "SONGDO_OPENAPI_KEY unset; proceeding with unauthenticated documented OpenAPI "
                "(probe observed resultCode=100). Register a key for production use."
            )
        return warnings

    def _fetch_window(
        self,
        client: PoliteHttpClient,
        api_url: str,
        key: str | None,
        start: date,
        end: date,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        params: dict[str, str] = {
            "resultType": "json",
            "stdate": start.strftime("%Y%m%d"),
            "eddate": end.strftime("%Y%m%d"),
        }
        if key:
            params["serviceKey"] = key
        resp = client.get(api_url, params=params, expect_content_types=("json", "text/"))
        payload = json.loads(resp.text)
        meta = {
            "top_level_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
            "resultCode": payload.get("resultCode") if isinstance(payload, dict) else None,
            "resultMessage": payload.get("resultMessage") if isinstance(payload, dict) else None,
            "has_totalCount": isinstance(payload, dict) and ("totalCount" in payload or "total" in payload),
            "item_count": 0,
            "window": f"{start.isoformat()}..{end.isoformat()}",
            "request_url": f"{api_url}?{urlencode({k: v for k, v in params.items() if k != 'serviceKey'})}",
        }
        items = []
        if isinstance(payload, dict):
            raw_items = payload.get("itemList")
            if raw_items is None:
                raw_items = payload.get("items") or []
            if isinstance(raw_items, list):
                items = [x for x in raw_items if isinstance(x, dict)]
            meta["item_count"] = len(items)
            for name in ("totalCount", "total", "pageNo", "numOfRows", "pageSize", "currentPage"):
                if name in payload:
                    meta[name] = payload[name]
        return items, meta

    def _collect_range(
        self,
        client: PoliteHttpClient,
        api_url: str,
        key: str | None,
        start: date,
        end: date,
        *,
        depth: int,
        call_metas: list[dict[str, Any]],
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        if start > end or client.remaining_budget() <= 0:
            return []
        items, meta = self._fetch_window(client, api_url, key, start, end)
        call_metas.append(meta)
        n = len(items)
        # Observed hard cap: exactly 10 rows. Split date range further using only
        # documented stdate/eddate — never invent pageNo/numOfRows.
        if n >= OBSERVED_ROW_CAP and start < end and depth < 8 and client.remaining_budget() > 0:
            mid = start + (end - start) // 2
            if mid >= start and mid < end:
                warnings.append(
                    f"Songdo window {start}..{end} returned {n} rows (=observed cap {OBSERVED_ROW_CAP}); "
                    f"splitting date range (documented stdate/eddate only)."
                )
                left = self._collect_range(
                    client, api_url, key, start, mid, depth=depth + 1, call_metas=call_metas, warnings=warnings
                )
                right = self._collect_range(
                    client,
                    api_url,
                    key,
                    mid + timedelta(days=1),
                    end,
                    depth=depth + 1,
                    call_metas=call_metas,
                    warnings=warnings,
                )
                return left + right
            warnings.append(
                f"Songdo window {start}..{end} hit row cap and cannot split further; "
                "completeness may be PARTIAL for this day."
            )
        return items

    def collect(self) -> CollectResult:
        warnings = self.validate_configuration()
        errors: list[str] = []
        src_policy = (self.policy.get("sources") or {}).get(self.source_id) or {}
        api_url = str(
            src_policy.get("api_url")
            or "https://songdoconvensia.visitincheon.or.kr/openApi/event.do"
        )
        list_urls = list(self.registry_entry.get("list_urls") or [])

        client = PoliteHttpClient(
            user_agent=self.user_agent,
            timeout_seconds=self.timeout_seconds,
            delay_seconds=self.delay_seconds,
            max_retries=self.max_retries,
            retry_backoff_seconds=self.retry_backoff_seconds,
            max_requests=self.max_requests,
        )

        win_start, win_end = self.window_bounds()
        key = os.environ.get("SONGDO_OPENAPI_KEY")
        call_metas: list[dict[str, Any]] = []
        gathered: list[dict[str, Any]] = []
        completeness = "UNKNOWN"

        try:
            # Baseline single wide call (for audit comparison)
            wide_items, wide_meta = self._fetch_window(client, api_url, key, win_start, win_end)
            call_metas.append({**wide_meta, "role": "wide_baseline"})

            # Month-first then adaptive date split when hit observed 10-row cap
            for ws, we in _month_windows(win_start, win_end):
                if len(gathered) >= self.max_records or client.remaining_budget() <= 0:
                    break
                part = self._collect_range(
                    client,
                    api_url,
                    key,
                    ws,
                    we,
                    depth=0,
                    call_metas=call_metas,
                    warnings=warnings,
                )
                gathered.extend(part)

            # Deduplicate
            seen: set[tuple] = set()
            unique_items: list[dict[str, Any]] = []
            for item in gathered:
                k = _item_key(item)
                if k in seen:
                    continue
                seen.add(k)
                unique_items.append(item)
                if len(unique_items) >= self.max_records:
                    break

            capped_windows = [
                m
                for m in call_metas
                if m.get("item_count") == OBSERVED_ROW_CAP and m.get("role") != "wide_baseline"
            ]
            single_day_capped = [
                m
                for m in capped_windows
                if m.get("window") and m["window"].split("..")[0] == m["window"].split("..")[1]
            ]
            if single_day_capped:
                completeness = "PARTIAL_DAY_CAP"
                warnings.append(
                    "At least one single-day window still returned 10 rows; "
                    "API hard-cap may hide additional same-day events. No page* params in docs/response."
                )
            elif any(m.get("item_count") == OBSERVED_ROW_CAP for m in call_metas if m.get("role") == "wide_baseline"):
                if len(unique_items) > len(wide_items):
                    completeness = "IMPROVED_VIA_DATE_SPLIT"
                    warnings.append(
                        f"Wide window returned {len(wide_items)}; date-split recovered "
                        f"{len(unique_items)} unique events. Docs list only resultType/stdate/eddate "
                        "(no page/totalCount)."
                    )
                else:
                    completeness = "COMPLETE_WITHIN_OBSERVED_CAP"
            else:
                completeness = "COMPLETE_NO_CAP_HIT"

            raw_rows = [
                self.stamp_raw(item, next((m.get("request_url") for m in call_metas if m.get("request_url")), api_url))
                for item in unique_items
            ]

            # Doc page reachability
            for u in list_urls[:1]:
                if client.remaining_budget() <= 0:
                    break
                try:
                    client.get(u, expect_content_types=("html", "text/"), allow_empty=True)
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"list_url reachability warning for {u}: {exc}")

            warnings.append(
                "Songdo OpenAPI completeness audit: documented params are resultType/stdate/eddate only; "
                f"response keys={wide_meta.get('top_level_keys')}; has_totalCount="
                f"{wide_meta.get('has_totalCount')}; wide_count={len(wide_items)}; "
                f"unique_after_date_split={len(unique_items)}; completeness={completeness}."
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            raw_rows = []

        out_path = self.raw_dir / f"{self.source_id}.jsonl"
        write_jsonl(out_path, raw_rows)

        # PARTIAL_DAY_CAP = documented 10-row soft-cap not fully cleared → PARTIAL_EXPECTED
        if errors and not raw_rows:
            status = "FAILED"
            success = False
        elif completeness in {"PARTIAL_DAY_CAP"}:
            status = "PARTIAL_EXPECTED"
            success = True
        elif raw_rows and errors:
            status = "PARTIAL_UNEXPECTED"
            success = True
        elif raw_rows:
            status = "OK"
            success = True
        else:
            status = "FAILED"
            success = False

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
            metadata={
                **self.get_source_metadata(),
                "api_url": api_url,
                "window_start": win_start.isoformat(),
                "window_end": win_end.isoformat(),
                "auth_mode": "serviceKey" if key else "none_observed",
                "completeness": completeness,
                "observed_row_cap": OBSERVED_ROW_CAP,
                "api_call_metas": call_metas[:80],
                "documented_params": ["resultType", "stdate", "eddate"],
                "pagination_params_documented": False,
                "totalCount_field_present": any(m.get("has_totalCount") for m in call_metas),
            },
        )

    def normalize_source_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        inquiry = (raw.get("inquiry") or "").strip() or None
        email = None
        phone = None
        if inquiry and "@" in inquiry and " " not in inquiry.strip():
            email = inquiry
        elif inquiry:
            phone = inquiry if any(ch.isdigit() for ch in inquiry) else None
        homepage = (raw.get("homepage") or "").strip() or None
        if homepage in {"-", "—"}:
            homepage = None
        # Synthetic id for tracking (OpenAPI has no event id field)
        syn = hashlib.sha1(
            f"{raw.get('event_nm')}|{raw.get('st_event_dt')}|{raw.get('end_event_dt')}|{raw.get('location')}".encode(
                "utf-8"
            )
        ).hexdigest()[:12]
        return {
            "source_event_id": syn,
            "title": raw.get("event_nm"),
            "title_en": raw.get("event_nm_en"),
            "start_date_raw": raw.get("st_event_dt"),
            "end_date_raw": raw.get("end_event_dt"),
            "date_text": None,
            "venue_name": "송도컨벤시아",
            "venue_address": None,
            "city": "인천",
            "region": "인천",
            "country": "KR",
            "location_raw": raw.get("location"),
            "host_raw": raw.get("host"),
            "organizer_raw": raw.get("supervision"),
            "operator_raw": None,
            "pco_raw": None,
            "category_raw": raw.get("category"),
            "homepage": homepage,
            "official_event_url": homepage,
            "source_url": raw.get("_source_url"),
            "inquiry_raw": inquiry,
            "contact_email": email,
            "contact_phone": phone,
            "contact_department": None,
            "contact_name": None,
            "description_summary": raw.get("pay") or None,
            "collected_at": raw.get("_collected_at"),
        }
