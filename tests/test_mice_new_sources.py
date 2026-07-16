"""Tests for 1B-1B source parsers, venue≠host, homepage≠inquiry, merge policy."""
from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.mice_collectors.base import CollectResult
from app.mice_collectors.coex import CoexCollector, parse_exhibition_detail, parse_home_cards
from app.mice_collectors.html_utils import is_venue_not_host
from app.mice_collectors.kintex import KintexCollector, merge_kintex_items, parse_fullcalendar_events
from app.mice_collectors.mice_or_kr import MiceOrKrCollector, parse_detail_page, parse_list_page
from app.mice_collectors.mice_seoul_cvb import MiceSeoulCvbCollector
from app.mice_collectors.registry import COLLECTOR_MAP, DEFAULT_MVP_SOURCES
from app.mice_normalizers.deduplicate import deduplicate_events
from app.mice_normalizers.event_normalizer import normalize_intermediate
from app.mice_normalizers.sales_signals import apply_sales_layer
from app.mice_normalizers.schema import new_event
from app.run_mice_collect import run_collect


COEX_HOME_SNIP = """
<div class="HeroSlideThumb-item" data-category='EXHIBITION'
 data-title='서울국제푸드페어' data-date='2026.08.01 - 2026.08.03'
 data-location='Hall A' data-link='https://www.coex.co.kr/exhibitions/food2026/'>
</div>
<div class="HeroSlideThumb-item" data-category='EXHIBITION'
 data-title='외부홈페이지전시' data-date='2026.09.01 - 2026.09.02'
 data-location='Hall B' data-link='https://external-show.example/home'>
</div>
"""

COEX_DETAIL_SNIP = """
<div class="EventDetailBoxHeader-tit">서울국제푸드페어</div>
<div class="EventDetailBoxHeader-date">2026.08.01 - 2026.08.03</div>
<div class="EventDetailBoxBodyTitle">주최</div>
<div class="EventDetailBoxBodyText-txt">한국식품협회</div>
<div class="EventDetailBoxBodyTitle">주관</div>
<div class="EventDetailBoxBodyText-txt">푸드운영사</div>
<div class="EventDetailBoxBodyTitle">담당자</div>
<div class="EventDetailBoxBodyText-txt">홍길동 Email: food@example.com Tel: 02-6000-1115 Fax: 02-1111-2222</div>
"""

KINTEX_FC_SNIP = """
events:[{
  description:'스마트팩토리쇼<br>로봇엑스포',
  start: new Date('2026/09/10')
},],
"""

MICE_OR_LIST = """
<section class="board-list__item">
  <div class="board-list__item-title"><a href="/bbs/board.php?bo_table=event&amp;wr_id=123">테스트전시회</a></div>
  <div class="board-list__item-date"><p>2026-09-01 ~ 2026-09-03</p></div>
</section>
"""

MICE_OR_DETAIL = """
<h1 class="board-view__title">테스트전시회</h1>
<div class="board-view__content">
<p>행사기간: 2026-09-01 ~ 2026-09-03</p>
<p>개최장소: BEXCO</p>
<p>주최: 테스트주최사</p>
<p>홈페이지 <a href="https://event.example.com/show">바로가기</a></p>
</div>
<div class="board-view__nav"></div>
"""


class NewSourceParseTests(unittest.TestCase):
    def test_mice_or_list_and_detail(self):
        items = parse_list_page(MICE_OR_LIST)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["wr_id"], "123")
        detail = parse_detail_page(MICE_OR_DETAIL, "123")
        self.assertEqual(detail["title"], "테스트전시회")
        self.assertIn("2026-09-01", detail["period"] or "")
        self.assertEqual(detail["homepage"], "https://event.example.com/show")
        self.assertNotIn("mice.or.kr", detail["homepage"])

    def test_kintex_fullcalendar_split_titles(self):
        items = parse_fullcalendar_events(KINTEX_FC_SNIP)
        titles = {i["title"] for i in items}
        self.assertIn("스마트팩토리쇼", titles)
        self.assertIn("로봇엑스포", titles)

    def test_coex_home_and_detail(self):
        cards = parse_home_cards(COEX_HOME_SNIP)
        self.assertEqual(len(cards), 2)
        detail = parse_exhibition_detail(COEX_DETAIL_SNIP)
        self.assertEqual(detail["host_raw"], "한국식품협회")
        self.assertEqual(detail["organizer_raw"], "푸드운영사")
        self.assertEqual(detail["contact_name"], "홍길동")
        self.assertEqual(detail["contact_email"], "food@example.com")
        self.assertEqual(detail["contact_phone"], "02-6000-1115")


class VenueVsHostTests(unittest.TestCase):
    def test_is_venue_not_host(self):
        self.assertTrue(is_venue_not_host("KINTEX"))
        self.assertTrue(is_venue_not_host("코엑스"))
        self.assertFalse(is_venue_not_host("한국식품협회"))

    def test_kintex_normalize_no_host(self):
        c = KintexCollector(
            registry_entry={"source_id": "kintex", "list_urls": []},
            policy={},
            raw_dir=Path("."),
        )
        mid = c.normalize_source_record(
            {"title": "쇼", "start_date": "2026-09-10", "hall": "Hall 1", "_source_url": "https://x"}
        )
        self.assertTrue(str(mid["venue_name"]).startswith("KINTEX"))
        self.assertIsNone(mid["host_raw"])
        self.assertIsNone(mid["official_event_url"])

    def test_coex_homepage_vs_venue_page(self):
        c = CoexCollector(
            registry_entry={"source_id": "coex", "list_urls": []},
            policy={},
            raw_dir=Path("."),
        )
        # External official site
        mid = c.normalize_source_record(
            {
                "title": "외부홈페이지전시",
                "date_text": "2026.09.01",
                "hall": "Hall B",
                "official_event_url": "https://external-show.example/home",
                "venue_page_url": None,
                "_source_url": "https://www.coex.co.kr/",
            }
        )
        self.assertEqual(mid["official_event_url"], "https://external-show.example/home")
        # Venue detail only — not official homepage
        mid2 = c.normalize_source_record(
            {
                "title": "서울국제푸드페어",
                "date_text": "2026.08.01",
                "hall": "Hall A",
                "host_raw": "COEX",
                "official_event_url": None,
                "venue_page_url": "https://www.coex.co.kr/exhibitions/food2026/",
                "contact_name": "홍길동",
                "_source_url": "https://www.coex.co.kr/",
            }
        )
        self.assertIsNone(mid2["official_event_url"])
        self.assertIsNone(mid2["host_raw"])  # facility name stripped
        self.assertEqual(mid2["source_url"], "https://www.coex.co.kr/exhibitions/food2026/")
        self.assertEqual(mid2["contact_source_url"], mid2["source_url"])


class MergeAndSalesPolicyTests(unittest.TestCase):
    def _ev(self, **kw):
        base = new_event(
            event_id=kw.pop("event_id", "e1"),
            source_id=kw.get("source_id", "k_mice"),
            source_event_id=kw.get("source_event_id"),
            title=kw.get("title", "행사"),
            title_normalized=kw.get("title_normalized", "행사"),
            start_date=kw.get("start_date", "2026-08-01"),
            venue_normalized=kw.get("venue_normalized", "킨텍스"),
            official_event_url=kw.get("official_event_url"),
            source_occurrences=kw.get(
                "source_occurrences",
                [{"source_id": kw.get("source_id", "k_mice"), "source_event_id": kw.get("source_event_id")}],
            ),
        )
        base.update(kw)
        return base

    def test_multi_source_merge_preserves_occurrences(self):
        a = self._ev(event_id="a", source_id="k_mice", source_event_id="1", title_normalized="동일쇼")
        b = self._ev(
            event_id="b",
            source_id="mice_or_kr",
            source_event_id="99",
            title_normalized="동일쇼",
            venue_normalized="킨텍스",
            start_date="2026-08-01",
        )
        reps, log = deduplicate_events([a, b])
        self.assertEqual(len(reps), 1)
        self.assertEqual(len(reps[0]["source_occurrences"]), 2)
        self.assertTrue(any(x.get("relation") == "CONFIRMED_MERGE" for x in log))

    def test_different_edition_not_merged(self):
        a = self._ev(event_id="a", title_normalized="월드쇼", start_date="2025-06-01", source_event_id="1")
        b = self._ev(
            event_id="b",
            title_normalized="월드쇼",
            start_date="2026-06-01",
            source_event_id="2",
            source_id="kintex",
        )
        reps, log = deduplicate_events([a, b])
        self.assertEqual(len(reps), 2)
        self.assertFalse(any(x.get("relation") == "CONFIRMED_MERGE" for x in log))

    def test_sales_readiness_not_from_type_alone(self):
        ev = self._ev(
            event_id="x",
            event_type="EXHIBITION",
            host_organizations=["주최사"],
            official_event_url=None,
            contact_email=None,
            contact_phone=None,
            sales_signal_types=[],
            sales_signal_basis=[],
        )
        apply_sales_layer(ev, today=date(2026, 7, 16), intermediate=None)
        # Type alone must not create sales_signal_types
        self.assertFalse(ev.get("sales_signal_types"))
        self.assertIn(ev.get("sales_readiness"), {"WATCH", "RESEARCH", "NONE"})


class PartialFailureIsolationTests(unittest.TestCase):
    def test_hold_source_does_not_block_others(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Minimal config files
            (root / "config").mkdir()
            (root / "config" / "mice-collection-policy.yaml").write_text(
                "policy_version: '1.1'\ncollector_version: '1.1.0'\n"
                "date_window: {past_days: 60, future_days: 550}\n"
                "limits: {max_records_per_source: 5, max_requests_per_source: 5, max_pages_per_source: 1}\n"
                "http: {request_delay_seconds: 0.01, request_timeout_seconds: 5, max_retries: 0, retry_backoff_seconds: 0.01}\n"
                "sources: {}\n",
                encoding="utf-8",
            )
            (root / "config" / "mice-source-registry.yaml").write_text(
                "sources:\n"
                "- source_id: mice_seoul_cvb\n"
                "  runtime_enabled: false\n"
                "  expected_runtime_status: HOLD_CONFIGURED\n"
                "  failure_affects_exit_code: false\n"
                "  list_urls: [https://example.invalid/hold]\n"
                "- source_id: kintex\n"
                "  runtime_enabled: true\n"
                "  expected_runtime_status: PARTIAL_EXPECTED\n"
                "  failure_affects_exit_code: true\n"
                "  list_urls: [https://example.invalid/kintex]\n",
                encoding="utf-8",
            )
            (root / "data" / "raw" / "mice").mkdir(parents=True)

            def fake_collect(self):
                if self.source_id == "mice_seoul_cvb":
                    return CollectResult(
                        source_id="mice_seoul_cvb",
                        success=True,
                        status="HOLD_CONFIGURED",
                        fetched_count=0,
                        warnings=["HOLD test"],
                        metadata={"implementation_status": "HOLD_CONFIGURED"},
                    )
                return CollectResult(
                    source_id="kintex",
                    success=True,
                    status="PARTIAL_EXPECTED",
                    fetched_count=2,
                    parsed_count=2,
                    warnings=["ok"],
                    metadata={"implementation_status": "PARTIAL_EXPECTED"},
                )

            with patch.object(MiceSeoulCvbCollector, "collect", fake_collect), patch.object(
                KintexCollector, "collect", fake_collect
            ):
                manifest = run_collect(
                    sources=["mice_seoul_cvb", "kintex"],
                    today=date(2026, 7, 16),
                    root=root,
                )
            statuses = {s["source_id"]: s["status"] for s in manifest["sources"]}
            self.assertEqual(statuses["mice_seoul_cvb"], "HOLD_CONFIGURED")
            self.assertEqual(statuses["kintex"], "PARTIAL_EXPECTED")
            self.assertEqual(manifest["exit_code_policy"]["collect_exit_code"], 0)

    def test_registry_includes_new_sources(self):
        for sid in ("mice_or_kr", "coex", "kintex", "mice_seoul_cvb"):
            self.assertIn(sid, COLLECTOR_MAP)
            self.assertIn(sid, DEFAULT_MVP_SOURCES)


class MiceOrNormalizeTests(unittest.TestCase):
    def test_mice_or_normalize_external_homepage(self):
        c = MiceOrKrCollector(
            registry_entry={"source_id": "mice_or_kr", "list_urls": []},
            policy={},
            raw_dir=Path("."),
        )
        mid = c.normalize_source_record(
            {
                "wr_id": "1",
                "title": "쇼",
                "period": "2026-09-01 ~ 2026-09-02",
                "venue": "BEXCO",
                "host_raw": "KINTEX",
                "homepage": "https://show.example/",
                "_source_url": "https://www.mice.or.kr/bbs/board.php?bo_table=event&wr_id=1",
            }
        )
        self.assertIsNone(mid["host_raw"])
        self.assertEqual(mid["official_event_url"], "https://show.example/")
        event, err = normalize_intermediate(
            mid,
            source_id="mice_or_kr",
            raw_file="x.jsonl",
            today=date(2026, 7, 16),
            past_days=60,
            future_days=550,
        )
        self.assertIsNone(err)
        self.assertIsNotNone(event)
        self.assertFalse(event.get("host_organizations"))


class MergeKintexHelperTests(unittest.TestCase):
    def test_merge_prefers_a11y_hall(self):
        fc = [{"title": "쇼A", "start_date": "2026-07-01"}]
        a11y = [{"title": "쇼A", "start_date": "2026-07-01", "end_date": "2026-07-03", "hall": "Hall 10"}]
        merged = merge_kintex_items(fc, a11y)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["hall"], "Hall 10")


if __name__ == "__main__":
    unittest.main()
