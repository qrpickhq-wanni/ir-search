"""K-MICE calendar collector (public SSR HTML + form POST)."""
from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

from app.io_utils import write_jsonl
from app.mice_collectors.base import CollectResult, MiceCollector
from app.mice_collectors.http_client import PoliteHttpClient


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean(html: str | None) -> str:
    if not html:
        return ""
    text = _TAG_RE.sub(" ", unescape(html))
    return _WS_RE.sub(" ", text).strip()


def _span_desc(html: str, icon_class: str) -> str | None:
    """Extract <span class="desc"> after a tit with given icon class."""
    pat = re.compile(
        rf'class="tit[^"]*{re.escape(icon_class)}[^"]*"[^>]*>.*?</span>\s*'
        rf'<span class="desc">(.*?)</span>',
        re.S | re.I,
    )
    m = pat.search(html)
    if not m:
        return None
    val = _clean(m.group(1))
    return val or None


def parse_list_page(html: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    # Split on list_box openings — nested </div> counts vary; findall under-matches.
    parts = re.split(r'<div class="list_box">', html, flags=re.I)[1:]
    for block in parts:
        eid_m = re.search(r"goView\(\s*['\"](\d+)['\"]\s*\)", block)
        if not eid_m:
            continue
        event_no = eid_m.group(1)
        title_ko_m = re.search(r'<p class="kor tit">(.*?)</p>', block, re.S | re.I)
        title_ko = _clean(title_ko_m.group(1)) if title_ko_m else ""
        title_en_m = re.search(r'<p class="eng tit">(.*?)</p>', block, re.S | re.I)
        title_en = _clean(title_en_m.group(1)) if title_en_m else ""
        date_m = re.search(r'<span class="date">(.*?)</span>', block, re.S | re.I)
        region_m = re.search(r'<span class="region">(.*?)</span>', block, re.S | re.I)
        cat_m = re.search(r'<span class="cate-txt">(.*?)</span>', block, re.S | re.I)
        items.append(
            {
                "event_no": event_no,
                "title_ko_list": title_ko or None,
                "title_en_list": title_en or None,
                "date_text_list": _clean(date_m.group(1)) if date_m else None,
                "region_list": _clean(region_m.group(1)) if region_m else None,
                "category_list": _clean(cat_m.group(1)) if cat_m else None,
            }
        )
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for it in items:
        if it["event_no"] in seen:
            continue
        seen.add(it["event_no"])
        uniq.append(it)
    return uniq


def _clean_website(text: str | None) -> str | None:
    if not text:
        return None
    s = text.strip()
    if s in {"-", "—", ""}:
        return None
    m = re.search(r"https?://[^\s<>\"']+", s)
    if not m:
        return s if s.startswith("www.") else None
    url = m.group(0)
    url = re.sub(r"^https?://https?://", "https://", url, flags=re.I)
    return url


def parse_detail_page(html: str, event_no: str) -> dict[str, Any]:
    title_ko_m = re.search(r'<p class="kor-name">(.*?)</p>', html, re.S | re.I)
    title_en_m = re.search(r'<p class="eng-name">(.*?)</p>', html, re.S | re.I)
    title_ko = _clean(title_ko_m.group(1)) if title_ko_m else ""
    title_en = _clean(title_en_m.group(1)) if title_en_m else ""
    period = _span_desc(html, "ico-date")
    host = _span_desc(html, "ico-host")
    region = _span_desc(html, "ico-area")
    venue = _span_desc(html, "ico-place")
    participants = _span_desc(html, "ico-people")
    website = _clean_website(_span_desc(html, "ico-site"))

    start_hidden = None
    end_hidden = None
    sm = re.search(
        r'name="miceCalendarDTO\.EVENT_START_DT"[^>]*value="([^"]*)"', html, re.I
    )
    em = re.search(r'name="miceCalendarDTO\.EVENT_END_DT"[^>]*value="([^"]*)"', html, re.I)
    if sm:
        start_hidden = sm.group(1).strip() or None
    if em:
        end_hidden = em.group(1).strip() or None

    return {
        "event_no": event_no,
        "title_ko": title_ko or None,
        "title_en": title_en or None,
        "period": period,
        "host": host,
        "region": region,
        "venue": venue,
        "participants_text": participants,
        "website": website,
        "event_start_dt_hidden": start_hidden,
        "event_end_dt_hidden": end_hidden,
    }


class KMiceCollector(MiceCollector):
    source_id = "k_mice"

    def validate_configuration(self) -> list[str]:
        warnings: list[str] = []
        list_urls = list(self.registry_entry.get("list_urls") or [])
        if not list_urls:
            warnings.append("registry list_urls empty for k_mice")
        return warnings

    def collect(self) -> CollectResult:
        warnings = self.validate_configuration()
        errors: list[str] = []
        src_policy = (self.policy.get("sources") or {}).get(self.source_id) or {}
        list_url = str(
            src_policy.get("list_url")
            or (self.registry_entry.get("list_urls") or [None])[0]
            or "https://k-mice.visitkorea.or.kr/miceCalendar.kto?func_name=list"
        )
        post_url = str(
            src_policy.get("post_url") or "https://k-mice.visitkorea.or.kr/miceCalendar.kto"
        )

        client = PoliteHttpClient(
            user_agent=self.user_agent,
            timeout_seconds=self.timeout_seconds,
            delay_seconds=self.delay_seconds,
            max_retries=self.max_retries,
            retry_backoff_seconds=self.retry_backoff_seconds,
            max_requests=self.max_requests,
        )

        raw_rows: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        pages_fetched = 0
        months_touched = 0
        try:
            # Seed session via GET (registry list URL)
            client.get(list_url, expect_content_types=("html", "text/"))

            win_start, win_end = self.window_bounds()
            # Public list form exposes miceCalendarDTO.YEAR / MONTH (observed on list HTML).
            y, m = win_start.year, win_start.month
            while (y < win_end.year) or (y == win_end.year and m <= win_end.month):
                if len(raw_rows) >= self.max_records or client.remaining_budget() <= 2:
                    break
                months_touched += 1
                page = 1
                page_items: list[dict[str, Any]] = []
                while page <= self.max_pages and len(raw_rows) < self.max_records:
                    if client.remaining_budget() <= 1:
                        warnings.append("stopped: max_requests_per_source reached")
                        break
                    try:
                        list_resp = client.post(
                            post_url,
                            data={
                                "func_name": "list",
                                "curr_page": str(page),
                                "miceCalendarDTO.YEAR": str(y),
                                "miceCalendarDTO.MONTH": f"{m:02d}",
                            },
                            headers={
                                "Referer": list_url,
                                "Content-Type": "application/x-www-form-urlencoded",
                            },
                            expect_content_types=("html", "text/"),
                        )
                        page_items = parse_list_page(list_resp.text)
                        pages_fetched += 1
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"list {y}-{m:02d} page {page}: {exc}")
                        break
                    if not page_items:
                        break
                    if all(str(x["event_no"]) in seen_ids for x in page_items):
                        # Month exhausted / repeated page
                        break

                    for item in page_items:
                        if len(raw_rows) >= self.max_records:
                            break
                        eid = str(item["event_no"])
                        if eid in seen_ids:
                            continue
                        seen_ids.add(eid)
                        if client.remaining_budget() <= 0:
                            warnings.append("stopped: max_requests_per_source reached")
                            break
                        try:
                            detail = client.post(
                                post_url,
                                data={
                                    "func_name": "calView",
                                    "miceCalendarDTO.EVENT_NO": eid,
                                    "curr_page": str(page),
                                    "miceCalendarDTO.YEAR": str(y),
                                    "miceCalendarDTO.MONTH": f"{m:02d}",
                                },
                                headers={
                                    "Referer": list_url,
                                    "Content-Type": "application/x-www-form-urlencoded",
                                },
                                expect_content_types=("html", "text/"),
                            )
                            detail_fields = parse_detail_page(detail.text, eid)
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"detail EVENT_NO={eid}: {exc}")
                            detail_fields = {"event_no": eid, "detail_error": str(exc)}
                        merged = {**item, **detail_fields}
                        merged["list_page"] = page
                        merged["list_year"] = y
                        merged["list_month"] = m
                        raw_rows.append(
                            self.stamp_raw(
                                merged,
                                urljoin(post_url, f"?func_name=calView&EVENT_NO={eid}"),
                            )
                        )
                    page += 1

                m += 1
                if m > 12:
                    m = 1
                    y += 1

            if not raw_rows:
                errors.append("k_mice list pages parsed 0 events across month window")
            warnings.append(
                "Listed via public form fields miceCalendarDTO.YEAR/MONTH over collection "
                f"window {win_start}..{win_end} ({months_touched} months, {pages_fetched} list pages). "
                "Normalize still applies date-window filter."
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

        out_path = self.raw_dir / f"{self.source_id}.jsonl"
        write_jsonl(out_path, raw_rows)
        if raw_rows and errors:
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
                "list_url": list_url,
                "post_url": post_url,
                "pages_fetched": pages_fetched,
                "months_touched": months_touched,
            },
        )

    def normalize_source_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        title = raw.get("title_ko") or raw.get("title_ko_list")
        title_en = raw.get("title_en") or raw.get("title_en_list")
        return {
            "source_event_id": str(raw.get("event_no") or "") or None,
            "title": title,
            "title_en": title_en,
            "start_date_raw": raw.get("event_start_dt_hidden"),
            "end_date_raw": raw.get("event_end_dt_hidden"),
            "date_text": raw.get("period") or raw.get("date_text_list"),
            "venue_name": raw.get("venue"),
            "venue_address": None,
            "city": raw.get("region") or raw.get("region_list"),
            "region": raw.get("region") or raw.get("region_list"),
            "country": "KR",
            "location_raw": raw.get("venue"),
            "host_raw": raw.get("host"),
            "organizer_raw": None,
            "operator_raw": None,
            "pco_raw": None,
            "category_raw": raw.get("category_list"),
            "homepage": raw.get("website"),
            "official_event_url": raw.get("website"),
            "source_url": raw.get("_source_url"),
            "inquiry_raw": None,
            "contact_email": None,
            "contact_phone": None,
            "contact_department": None,
            "contact_name": None,
            "description_summary": None,
            "expected_participants_raw": raw.get("participants_text"),
            "collected_at": raw.get("_collected_at"),
        }
