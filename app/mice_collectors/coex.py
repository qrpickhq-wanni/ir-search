"""COEX venue schedule collector — home exhibition cards + public detail pages.

PARTIAL: full-schedules page is empty SSR (JS calendar). Home cards + /exhibitions/
detail pages provide title/date/location and sometimes 주최/주관/담당자.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from app.io_utils import write_jsonl
from app.mice_collectors.base import CollectResult, MiceCollector
from app.mice_collectors.html_utils import attr, is_venue_not_host, strip_tags
from app.mice_collectors.http_client import PoliteHttpClient


HOME_URL = "https://www.coex.co.kr/"
EXHIBITION_HOST = "www.coex.co.kr"


def _syn_id(title: str, date_text: str | None) -> str:
    return hashlib.sha1(f"{title}|{date_text or ''}".encode("utf-8")).hexdigest()[:12]


def parse_home_cards(html: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for m in re.finditer(
        r"<div[^>]*class=['\"][^'\"]*HeroSlideThumb-item[^'\"]*['\"][^>]*>",
        html,
        re.I,
    ):
        # Expand to a longer attribute-rich opening tag — re-find full tag
        pass
    # Attribute-based: find data-category='EXHIBITION' blocks
    for m in re.finditer(
        r"data-category=['\"]EXHIBITION['\"]([^>]*)>",
        html,
        re.I,
    ):
        # Look backwards for the opening div start
        start = html.rfind("<div", 0, m.start())
        end = html.find(">", m.end() - 1)
        if start < 0 or end < 0:
            tag = m.group(0)
        else:
            tag = html[start : end + 1]
        title = attr(tag, "data-title")
        date_text = attr(tag, "data-date")
        location = attr(tag, "data-location")
        link = attr(tag, "data-link")
        if not title:
            continue
        items.append(
            {
                "title": title,
                "date_text": date_text,
                "hall": location,
                "data_link": link,
                "source_event_id": _syn_id(title, date_text),
            }
        )
    # Dedup
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for it in items:
        k = (it.get("title") or "").casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def parse_exhibition_detail(html: str) -> dict[str, Any]:
    title_m = re.search(
        r'class=["\'][^"\']*EventDetailBoxHeader-tit[^"\']*["\'][^>]*>([^<]+)',
        html,
        re.I,
    )
    date_m = re.search(
        r'class=["\'][^"\']*EventDetailBoxHeader-date[^"\']*["\'][^>]*>([^<]+)',
        html,
        re.I,
    )
    # Body sections: EventDetailBoxBodyTitle + sibling text
    sections: dict[str, str] = {}
    for m in re.finditer(
        r'EventDetailBoxBodyTitle[^>]*>([^<]+)</[^>]+>[\s\S]{0,400}?'
        r'EventDetailBoxBodyText-txt[^>]*>([\s\S]*?)</',
        html,
        re.I,
    ):
        lab = strip_tags(m.group(1))
        val = strip_tags(m.group(2))
        if lab and val:
            sections[lab] = val

    host = sections.get("주최")
    organizer = sections.get("주관")
    contact_blob = sections.get("담당자") or ""
    contact_name = None
    contact_email = None
    contact_phone = None
    if contact_blob and contact_blob not in {"-", "—"}:
        em = re.search(r"[\w.+-]+@[\w.-]+\.\w+", contact_blob)
        if em:
            contact_email = em.group(0)
        ph = re.search(r"(?:Tel|전화|T)[:\s]*([0-9][0-9\-\s]{7,})", contact_blob, re.I)
        if ph:
            contact_phone = re.sub(r"\s+", "", ph.group(1))
        # Name = leading token before Email/Tel/Fax
        name_m = re.match(r"([^E전화TelFax\n]+)", contact_blob)
        if name_m:
            contact_name = name_m.group(1).strip(" :：-|")
            if contact_name in {"-", "—", ""}:
                contact_name = None
    return {
        "title_detail": strip_tags(title_m.group(1)) if title_m else None,
        "date_text_detail": strip_tags(date_m.group(1)) if date_m else None,
        "host_raw": host,
        "organizer_raw": organizer,
        "contact_name": contact_name,
        "contact_email": contact_email,
        "contact_phone": contact_phone,
        "detail_sections": sections,
    }


class CoexCollector(MiceCollector):
    source_id = "coex"

    def validate_configuration(self) -> list[str]:
        return [
            "PARTIAL: COEX /event/full-schedules/ is empty SSR; collecting home exhibition "
            "cards and public /exhibitions/ detail pages only."
        ]

    def collect(self) -> CollectResult:
        warnings = self.validate_configuration()
        errors: list[str] = []
        home = HOME_URL
        for u in self.registry_entry.get("list_urls") or []:
            if "coex.co.kr" in u:
                home = u
                break

        client = PoliteHttpClient(
            user_agent=self.user_agent,
            timeout_seconds=self.timeout_seconds,
            delay_seconds=self.delay_seconds,
            max_retries=self.max_retries,
            retry_backoff_seconds=self.retry_backoff_seconds,
            max_requests=min(self.max_requests, 40),
        )

        raw_rows: list[dict[str, Any]] = []
        try:
            resp = client.get(home, expect_content_types=("html", "text/"))
            cards = parse_home_cards(resp.text)
            if not cards:
                errors.append("No EXHIBITION HeroSlideThumb cards found on COEX home")
            warnings.append(f"Home exhibition cards: {len(cards)}")

            for card in cards[: self.max_records]:
                title = card.get("title") or ""
                if "창립" in title and "주년" in title:
                    warnings.append(f"Skipped venue promo card (not event): {title}")
                    continue
                link = card.get("data_link") or ""
                detail: dict[str, Any] = {}
                official = None
                source_url = home

                if EXHIBITION_HOST in link and "/exhibitions/" in link:
                    source_url = link
                    if client.remaining_budget() > 0:
                        try:
                            dresp = client.get(link, expect_content_types=("html", "text/"))
                            detail = parse_exhibition_detail(dresp.text)
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"detail {link}: {exc}")
                    # COEX exhibition page is venue page, not necessarily event site
                    official = None
                elif link.startswith("http"):
                    # External official event site from data-link
                    official = link
                    source_url = home

                merged = {
                    **card,
                    **detail,
                    "official_event_url": official,
                    "venue_page_url": link if EXHIBITION_HOST in (link or "") else None,
                }
                raw_rows.append(self.stamp_raw(merged, source_url))

            warnings.append(
                "Facility contact numbers on COEX site are not stored as event contacts; "
                "only EventDetailBoxBodyTitle '담당자' when present."
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

        out_path = self.raw_dir / f"{self.source_id}.jsonl"
        write_jsonl(out_path, raw_rows)
        if raw_rows and errors:
            status = "PARTIAL_UNEXPECTED"
            success = True
        elif raw_rows:
            # Documented limited scope (home cards + exhibition detail)
            status = "PARTIAL_EXPECTED"
            success = True
        elif not errors:
            status = "OK_EMPTY"
            success = True
            warnings.append("OK_EMPTY: COEX home reachable but no exhibition cards parsed.")
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
                "home_url": home,
                "implementation_status": "PARTIAL_EXPECTED",
                "full_schedules_ssr": "empty",
            },
        )

    def normalize_source_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        title = raw.get("title_detail") or raw.get("title")
        date_text = raw.get("date_text_detail") or raw.get("date_text")
        hall = raw.get("hall")
        venue = "COEX"
        if hall:
            venue = f"COEX {hall}".strip()

        # Venue page vs official event homepage
        official = raw.get("official_event_url")
        venue_page = raw.get("venue_page_url")
        # Never set host to COEX / facility name
        host = raw.get("host_raw")
        if is_venue_not_host(host):
            host = None
        organizer = raw.get("organizer_raw")
        if is_venue_not_host(organizer):
            organizer = None

        contact_name = raw.get("contact_name")
        contact_email = raw.get("contact_email")
        contact_phone = raw.get("contact_phone")
        # Contact source = venue exhibition page (public), not invented
        contact_source = (
            venue_page
            if (contact_name or contact_email or contact_phone)
            else None
        )
        # Official event homepage = external data-link only; COEX /exhibitions/ is source_url
        source_url = venue_page or raw.get("_source_url")

        return {
            "source_event_id": raw.get("source_event_id"),
            "title": title,
            "title_en": None,
            "start_date_raw": None,
            "end_date_raw": None,
            "date_text": date_text,
            "venue_name": venue,
            "venue_address": None,
            "city": "서울",
            "region": "서울",
            "country": "KR",
            "location_raw": hall,
            "host_raw": host,
            "organizer_raw": organizer,
            "operator_raw": None,
            "pco_raw": None,
            "category_raw": "EXHIBITION",
            "homepage": official,
            "official_event_url": official,
            "source_url": source_url,
            "inquiry_raw": None,
            "contact_email": contact_email,
            "contact_phone": contact_phone,
            "contact_department": None,
            "contact_name": contact_name,
            "contact_source_url": contact_source,
            "description_summary": None,
            "collected_at": raw.get("_collected_at"),
            "needs_host_role_check": bool(venue_page and not official),
        }
