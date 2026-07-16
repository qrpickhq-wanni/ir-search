"""KINTEX venue calendar collector — public SSR FullCalendar embed on clist.do.

PARTIAL: calendar provides titles/dates (and hall from a11y text); no public
per-event detail pages with organizer/contact were observed.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from app.io_utils import write_jsonl
from app.mice_collectors.base import CollectResult, MiceCollector
from app.mice_collectors.html_utils import strip_tags
from app.mice_collectors.http_client import PoliteHttpClient


LIST_URL = "https://www.kintex.com/web/ko/event/clist.do"


def _syn_id(title: str, start: str | None, hall: str | None) -> str:
    return hashlib.sha1(f"{title}|{start or ''}|{hall or ''}".encode("utf-8")).hexdigest()[:12]


def parse_fullcalendar_events(html: str) -> list[dict[str, Any]]:
    """Parse FullCalendar events:[{...}] embedded in clist.do."""
    m = re.search(r"events\s*:\s*\[", html)
    if not m:
        return []
    # Take a bounded slice after events:[
    chunk = html[m.end() : m.end() + 200000]
    end = chunk.find("],")
    if end < 0:
        end = chunk.find("]")
    if end < 0:
        return []
    body = chunk[:end]
    items: list[dict[str, Any]] = []
    for obj in re.finditer(
        r"description\s*:\s*'([^']*)'[\s\S]*?start\s*:\s*new Date\('(\d{4}/\d{2}/\d{2})'\)",
        body,
        re.I,
    ):
        desc = obj.group(1).replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
        start = obj.group(2).replace("/", "-")
        for name in re.split(r"[\n]+", desc):
            title = strip_tags(name)
            if not title or title in {"전시회", "회의", "문화", "기타"}:
                continue
            items.append({"title": title, "start_date": start, "source": "fullcalendar_js"})
    return items


def parse_a11y_hall_lines(html: str) -> list[dict[str, Any]]:
    """Parse accessibility prose: '07월 03일부터 07월 05일까지 Hall 10 제목'."""
    text = strip_tags(html)
    items: list[dict[str, Any]] = []
    # Month context: "7월 행사:" sections
    for sec in re.finditer(r"(\d{1,2})월\s*행사\s*[:：]([\s\S]*?)(?=\d{1,2}월\s*행사\s*[:：]|$)", text):
        month = int(sec.group(1))
        body = sec.group(2)
        for m in re.finditer(
            r"(\d{1,2})월\s*(\d{1,2})일부터\s*(?:(\d{1,2})월\s*)?(\d{1,2})일까지\s*"
            r"(Hall\s*[\dA-Za-z,\s]+?)\s+([^,·]+?)(?:,|$)",
            body,
        ):
            sm, sd = int(m.group(1)), int(m.group(2))
            em = int(m.group(3) or sm)
            ed = int(m.group(4))
            hall = strip_tags(m.group(5))
            title = strip_tags(m.group(6))
            if not title:
                continue
            # Year not in a11y — use calendar year from page if present, else leave date_text only
            year_m = re.search(r"new Date\('(\d{4})/", html)
            year = int(year_m.group(1)) if year_m else None
            start = end = date_text = None
            if year:
                start = f"{year}-{sm:02d}-{sd:02d}"
                end = f"{year}-{em:02d}-{ed:02d}"
            else:
                date_text = f"{sm}월 {sd}일 ~ {em}월 {ed}일"
            items.append(
                {
                    "title": title,
                    "start_date": start,
                    "end_date": end,
                    "date_text": date_text,
                    "hall": hall,
                    "source": "a11y_prose",
                    "month_context": month,
                }
            )
    return items


def merge_kintex_items(fc: list[dict[str, Any]], a11y: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer a11y rows (have hall + period); supplement with FullCalendar titles."""
    by_title: dict[str, dict[str, Any]] = {}
    for it in a11y:
        key = (it.get("title") or "").casefold()
        if key:
            by_title[key] = dict(it)
    for it in fc:
        key = (it.get("title") or "").casefold()
        if not key:
            continue
        if key in by_title:
            cur = by_title[key]
            if not cur.get("start_date") and it.get("start_date"):
                cur["start_date"] = it["start_date"]
            cur["seen_in_fullcalendar"] = True
        else:
            by_title[key] = dict(it)
    return list(by_title.values())


class KintexCollector(MiceCollector):
    source_id = "kintex"

    def validate_configuration(self) -> list[str]:
        return [
            "PARTIAL: KINTEX clist.do embeds calendar titles/dates; no public per-event "
            "detail pages with organizer/contact were observed in audit."
        ]

    def collect(self) -> CollectResult:
        warnings = self.validate_configuration()
        errors: list[str] = []
        # Use registry list_urls only (documented clist.do and searchType=11).
        list_urls = list(self.registry_entry.get("list_urls") or [LIST_URL])
        if not list_urls:
            list_urls = [LIST_URL]
        base = list_urls[0]

        client = PoliteHttpClient(
            user_agent=self.user_agent,
            timeout_seconds=self.timeout_seconds,
            delay_seconds=self.delay_seconds,
            max_retries=self.max_retries,
            retry_backoff_seconds=self.retry_backoff_seconds,
            max_requests=min(self.max_requests, 20),
        )

        merged: list[dict[str, Any]] = []
        try:
            for url in list_urls:
                if client.remaining_budget() <= 0:
                    break
                try:
                    resp = client.get(url, expect_content_types=("html", "text/"))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"clist {url}: {exc}")
                    continue
                fc = parse_fullcalendar_events(resp.text)
                a11y = parse_a11y_hall_lines(resp.text)
                part = merge_kintex_items(fc, a11y)
                for it in part:
                    it["list_url"] = url
                merged.extend(part)
                warnings.append(f"{url}: fullcalendar_names={len(fc)} a11y_rows={len(a11y)}")

            # Deduplicate by title+start
            seen: set[tuple] = set()
            unique: list[dict[str, Any]] = []
            for it in merged:
                title = (it.get("title") or "").strip()
                if not title:
                    continue
                key = (title.casefold(), it.get("start_date") or "", it.get("hall") or "")
                if key in seen:
                    continue
                seen.add(key)
                it["source_event_id"] = _syn_id(title, it.get("start_date"), it.get("hall"))
                unique.append(it)
                if len(unique) >= self.max_records:
                    break

            raw_rows = [self.stamp_raw(it, it.get("list_url") or base) for it in unique]
            warnings.append(
                f"PARTIAL completeness: {len(raw_rows)} unique titles from calendar HTML; "
                "organizer/homepage/contact not available without detail pages."
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            raw_rows = []

        out_path = self.raw_dir / f"{self.source_id}.jsonl"
        write_jsonl(out_path, raw_rows)
        if raw_rows and errors:
            status = "PARTIAL_UNEXPECTED"
            success = True
        elif raw_rows:
            # Documented: calendar titles/dates only — expected incomplete field set
            status = "PARTIAL_EXPECTED"
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
                "list_url": base,
                "implementation_status": "PARTIAL_EXPECTED",
                "detail_pages_available": False,
            },
        )

    def normalize_source_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        hall = raw.get("hall")
        venue = "KINTEX"
        if hall:
            venue = f"KINTEX {hall}".strip()
        # Never treat KINTEX as host organization
        return {
            "source_event_id": raw.get("source_event_id"),
            "title": raw.get("title"),
            "title_en": None,
            "start_date_raw": raw.get("start_date"),
            "end_date_raw": raw.get("end_date"),
            "date_text": raw.get("date_text"),
            "venue_name": venue,
            "venue_address": None,
            "city": "고양",
            "region": "경기",
            "country": "KR",
            "location_raw": hall,
            "host_raw": None,
            "organizer_raw": None,
            "operator_raw": None,
            "pco_raw": None,
            "category_raw": None,
            "homepage": None,
            "official_event_url": None,
            "source_url": raw.get("_source_url") or raw.get("list_url"),
            "inquiry_raw": None,
            "contact_email": None,
            "contact_phone": None,
            "contact_department": None,
            "contact_name": None,
            "description_summary": None,
            "collected_at": raw.get("_collected_at"),
        }
