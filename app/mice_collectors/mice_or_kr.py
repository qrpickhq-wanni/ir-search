"""마이스워크넷 (mice.or.kr) SSR HTML collector — bo_table=event."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from app.io_utils import write_jsonl
from app.mice_collectors.base import CollectResult, MiceCollector
from app.mice_collectors.html_utils import is_venue_not_host, labeled_value, strip_tags
from app.mice_collectors.http_client import PoliteHttpClient
from app.mice_normalizers.date_utils import parse_mice_date_range


LIST_URL = "https://www.mice.or.kr/bbs/board.php?bo_table=event"
DETAIL_TMPL = "https://www.mice.or.kr/bbs/board.php?bo_table=event&wr_id={wr_id}"


def parse_list_page(html: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    # Prefer board-list__item blocks; fall back to wr_id links
    blocks = re.split(r'<section[^>]*board-list__item', html, flags=re.I)[1:]
    if not blocks:
        for m in re.finditer(
            r'href="([^"]*bo_table=event[^"]*wr_id=(\d+)[^"]*)"[^>]*>([^<]+)</a>',
            html,
            re.I,
        ):
            items.append(
                {
                    "wr_id": m.group(2),
                    "title": strip_tags(m.group(3)),
                    "list_url": unescape_amp(m.group(1)),
                    "date_text_list": None,
                }
            )
        return _uniq_wr(items)

    for block in blocks:
        wr_m = re.search(r"wr_id=(\d+)", block, re.I)
        if not wr_m:
            continue
        wr_id = wr_m.group(1)
        title_m = re.search(
            r'board-list__item-title[\s\S]*?<a[^>]*>([^<]+)</a>',
            block,
            re.I,
        )
        date_m = re.search(
            r'board-list__item-date[^>]*>\s*<p>([^<]+)</p>',
            block,
            re.I,
        )
        href_m = re.search(r'href="([^"]*wr_id=' + wr_id + r'[^"]*)"', block, re.I)
        items.append(
            {
                "wr_id": wr_id,
                "title": strip_tags(title_m.group(1)) if title_m else None,
                "date_text_list": strip_tags(date_m.group(1)) if date_m else None,
                "list_url": unescape_amp(href_m.group(1)) if href_m else DETAIL_TMPL.format(wr_id=wr_id),
            }
        )
    return _uniq_wr(items)


def unescape_amp(url: str) -> str:
    return url.replace("&amp;", "&")


def _uniq_wr(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for it in items:
        wid = str(it.get("wr_id") or "")
        if not wid or wid in seen:
            continue
        seen.add(wid)
        out.append(it)
    return out


def parse_detail_page(html: str, wr_id: str) -> dict[str, Any]:
    title_m = re.search(
        r'<h1[^>]*class="[^"]*board-view__title[^"]*"[^>]*>([^<]+)</h1>',
        html,
        re.I,
    )
    if not title_m:
        title_m = re.search(r"<title>([^|<]+)", html, re.I)
    title = strip_tags(title_m.group(1)) if title_m else None

    # Main content region
    body_m = re.search(
        r'class="[^"]*board-view__content[^"]*"[^>]*>([\s\S]*?)</div>\s*<div class="[^"]*board-view__',
        html,
        re.I,
    )
    if not body_m:
        body_m = re.search(r'id="bo_v_con"[^>]*>([\s\S]*?)</div>', html, re.I)
    body_html = body_m.group(1) if body_m else html
    body_text = strip_tags(body_html)

    period = labeled_value(body_text, ("행사기간", "기간", "개최기간"))
    venue = labeled_value(body_text, ("개최장소", "장소", "전시장"))
    host = labeled_value(body_text, ("주최/주관", "주최", "주관"))
    # Prefer explicit homepage link near 홈페이지/출처
    homepage = None
    hp_m = re.search(
        r"""(?:홈페이지|출처)[^<]{0,80}<a[^>]+href=["'](https?://[^"']+)["']""",
        body_html,
        re.I,
    )
    if hp_m:
        homepage = hp_m.group(1)
    if not homepage:
        # First external http link that is not mice.or.kr
        for m in re.finditer(r"""href=["'](https?://[^"']+)["']""", body_html, re.I):
            u = m.group(1)
            if "mice.or.kr" in u:
                continue
            homepage = u
            break

    return {
        "wr_id": wr_id,
        "title": title,
        "period": period,
        "venue": venue,
        "host_raw": host,
        "homepage": homepage,
        "body_excerpt": body_text[:800] if body_text else None,
    }


def _list_end_before_window(date_text: str | None, win_start) -> bool:
    if not date_text:
        return False
    start, end, _ = parse_mice_date_range(date_text=date_text)
    iso = end or start
    if not iso:
        return False
    try:
        from datetime import date as date_cls

        return date_cls.fromisoformat(iso) < win_start
    except ValueError:
        return False


class MiceOrKrCollector(MiceCollector):
    source_id = "mice_or_kr"

    def validate_configuration(self) -> list[str]:
        warnings: list[str] = []
        urls = list(self.registry_entry.get("list_urls") or [])
        if not any("bo_table=event" in u for u in urls):
            warnings.append("registry list_urls missing bo_table=event")
        warnings.append(
            "Terms caution: copy/republish restricted without prior approval — internal use only."
        )
        return warnings

    def collect(self) -> CollectResult:
        warnings = self.validate_configuration()
        errors: list[str] = []
        list_url = LIST_URL
        for u in self.registry_entry.get("list_urls") or []:
            if "bo_table=event" in u:
                list_url = u
                break

        client = PoliteHttpClient(
            user_agent=self.user_agent,
            timeout_seconds=self.timeout_seconds,
            delay_seconds=self.delay_seconds,
            max_retries=self.max_retries,
            retry_backoff_seconds=self.retry_backoff_seconds,
            max_requests=self.max_requests,
        )
        win_start, win_end = self.window_bounds()
        raw_rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        pages_fetched = 0
        stop_old = False

        try:
            for page in range(1, self.max_pages + 1):
                if len(raw_rows) >= self.max_records or client.remaining_budget() <= 1:
                    break
                if stop_old:
                    break
                url = list_url if page == 1 else f"{list_url}&page={page}"
                # list_url may already contain ? — handle
                if page > 1:
                    sep = "&" if "?" in list_url else "?"
                    url = f"{list_url}{sep}page={page}"
                try:
                    resp = client.get(url, expect_content_types=("html", "text/"))
                    pages_fetched += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"list page {page}: {exc}")
                    break
                items = parse_list_page(resp.text)
                if not items:
                    if page == 1:
                        errors.append("mice_or_kr list parsed 0 items")
                    break

                page_all_old = True
                for item in items:
                    wid = str(item["wr_id"])
                    if wid in seen:
                        continue
                    dt = item.get("date_text_list")
                    if dt and not _list_end_before_window(dt, win_start):
                        page_all_old = False
                    elif not dt:
                        page_all_old = False
                    if _list_end_before_window(dt, win_start):
                        # still allow if unknown; skip fetching very old
                        continue

                    seen.add(wid)
                    detail_url = DETAIL_TMPL.format(wr_id=wid)
                    if item.get("list_url") and item["list_url"].startswith("http"):
                        detail_url = item["list_url"]
                    elif item.get("list_url"):
                        detail_url = urljoin("https://www.mice.or.kr", item["list_url"])

                    detail_fields: dict[str, Any] = {}
                    if client.remaining_budget() > 0 and len(raw_rows) < self.max_records:
                        try:
                            dresp = client.get(detail_url, expect_content_types=("html", "text/"))
                            detail_fields = parse_detail_page(dresp.text, wid)
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"detail wr_id={wid}: {exc}")
                            detail_fields = {"wr_id": wid, "detail_error": str(exc)}

                    merged = {**item, **detail_fields, "list_page": page}
                    raw_rows.append(self.stamp_raw(merged, detail_url))
                    if len(raw_rows) >= self.max_records:
                        break

                if page_all_old and page > 1:
                    stop_old = True
                    warnings.append(
                        f"Stopped at page {page}: list dates entirely before window start {win_start}"
                    )

            warnings.append(
                f"Collected {len(raw_rows)} events from {pages_fetched} list pages "
                f"(window {win_start}..{win_end}; detail via public GET wr_id)."
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

        out_path = self.raw_dir / f"{self.source_id}.jsonl"
        write_jsonl(out_path, raw_rows)
        if raw_rows and errors:
            status, success = "PARTIAL_UNEXPECTED", True
        elif raw_rows:
            status, success = "OK", True
        elif pages_fetched > 0 and not errors:
            status, success = "OK_EMPTY", True
            warnings.append(
                "OK_EMPTY: event board reachable and parsed, but none fell inside the "
                f"collection window ({win_start}..{win_end}). Latest list dates appear older."
            )
        else:
            status, success = "FAILED", False

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
                "pages_fetched": pages_fetched,
                "implementation_status": "IMPLEMENTED",
            },
        )

    def normalize_source_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        title = raw.get("title") or raw.get("title_list")
        host_raw = raw.get("host_raw")
        if is_venue_not_host(host_raw):
            host_raw = None
        organizer_raw = None
        # If host_raw contains 주최/주관 together, leave as host and flag verification
        homepage = raw.get("homepage")
        if homepage and "mice.or.kr" in str(homepage):
            # board page is source_url, not official event homepage
            homepage = None
        return {
            "source_event_id": str(raw.get("wr_id") or "") or None,
            "title": title,
            "title_en": None,
            "start_date_raw": None,
            "end_date_raw": None,
            "date_text": raw.get("period") or raw.get("date_text_list"),
            "venue_name": raw.get("venue"),
            "venue_address": None,
            "city": None,
            "region": None,
            "country": "KR",
            "location_raw": raw.get("venue"),
            "host_raw": host_raw,
            "organizer_raw": organizer_raw,
            "operator_raw": None,
            "pco_raw": None,
            "category_raw": None,
            "homepage": homepage,
            "official_event_url": homepage,
            "source_url": raw.get("_source_url"),
            "inquiry_raw": None,
            "contact_email": None,
            "contact_phone": None,
            "contact_department": None,
            "contact_name": None,
            "description_summary": (raw.get("body_excerpt") or "")[:400] or None,
            "collected_at": raw.get("_collected_at"),
            "needs_host_role_check": bool(host_raw and "주관" in str(host_raw)),
        }
