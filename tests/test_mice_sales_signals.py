"""Sales signal / readiness policy tests."""
from __future__ import annotations

import unittest
from datetime import date

from app.mice_normalizers.event_normalizer import normalize_intermediate
from app.mice_normalizers.sales_signals import (
    apply_sales_layer,
    detect_sales_signals,
    infer_qrpick_service_matches,
)
from app.mice_normalizers.schema import new_event
from app.mice_normalizers.text_utils import extract_email
from app.run_mice_summary import write_bom_csv
import tempfile
from pathlib import Path


class MiceSalesSignalTests(unittest.TestCase):
    def test_type_alone_does_not_create_sales_signals(self):
        event = new_event(
            title="국제 학술대회",
            event_type="ACADEMIC_CONFERENCE",
            event_status="UPCOMING",
            start_date="2026-09-01",
            end_date="2026-09-03",
            host_organizations=["테스트학회"],
            official_event_url="https://example.com/conf",
        )
        apply_sales_layer(event, today=date(2026, 7, 16))
        self.assertEqual(event["sales_signal_types"], [])
        self.assertEqual(event["sales_readiness"], "RESEARCH")
        self.assertIn("organizer_name", event["sales_signal_basis"])
        self.assertIn("official_inquiry_url", event["sales_signal_basis"])
        self.assertIn("REGISTRATION", event["qrpick_service_matches"])

    def test_qrpick_services_from_type(self):
        self.assertIn("EXHIBITOR_LEAD", infer_qrpick_service_matches("EXHIBITION"))
        self.assertIn("SESSION_MANAGEMENT", infer_qrpick_service_matches("CONFERENCE"))

    def test_exhibitor_url_creates_sales_signal(self):
        event = new_event(
            title="테스트 박람회",
            event_type="EXHIBITION",
            event_status="UPCOMING",
            start_date="2026-10-01",
            exhibitor_recruitment_url="https://example.com/exhibitors",
            host_organizations=["주최사"],
        )
        signals, basis = detect_sales_signals(event)
        self.assertIn("EXHIBITOR_LEAD", signals)
        self.assertIn("exhibitor_recruitment_url", basis)

    def test_contactable_needs_contact_not_homepage_only(self):
        event = new_event(
            title="미래 컨퍼런스",
            event_type="CONFERENCE",
            event_status="UPCOMING",
            start_date="2026-11-01",
            host_organizations=["주최기관"],
            official_event_url="https://example.com",
        )
        apply_sales_layer(event, today=date(2026, 7, 16))
        self.assertEqual(event["sales_readiness"], "RESEARCH")

        event2 = new_event(
            title="미래 컨퍼런스",
            event_type="CONFERENCE",
            event_status="UPCOMING",
            start_date="2026-11-01",
            host_organizations=["주최기관"],
            contact_email="ops@example.com",
            contact_source_url="https://example.com",
            official_event_url="https://example.com",
        )
        apply_sales_layer(event2, today=date(2026, 7, 16))
        self.assertEqual(event2["sales_readiness"], "CONTACTABLE")
        self.assertIn("contact_email", event2["sales_signal_basis"])
        self.assertIn("organizer_name", event2["sales_signal_basis"])

    def test_homepage_without_org_is_watch(self):
        event = new_event(
            title="미지 기관 행사",
            event_type="OTHER",
            event_status="UPCOMING",
            start_date="2026-12-01",
            official_event_url="https://example.com/e",
        )
        apply_sales_layer(event, today=date(2026, 7, 16))
        self.assertEqual(event["sales_readiness"], "WATCH")

    def test_ended_is_none(self):
        event = new_event(
            title="지난 학술대회",
            event_type="ACADEMIC_CONFERENCE",
            event_status="ENDED",
            start_date="2026-05-01",
            end_date="2026-05-03",
            host_organizations=["학회"],
            contact_email="a@b.c",
        )
        apply_sales_layer(event, today=date(2026, 7, 16))
        self.assertEqual(event["sales_readiness"], "NONE")

    def test_procurement_is_direct(self):
        event = new_event(
            title="전시 운영시스템 구축 용역 입찰 안내",
            event_type="OTHER",
            event_status="UPCOMING",
            start_date="2026-08-01",
            description_summary="등록 시스템 구축 입찰",
            host_organizations=["공단"],
        )
        apply_sales_layer(event, today=date(2026, 7, 16))
        self.assertEqual(event["sales_readiness"], "DIRECT_OPPORTUNITY")
        self.assertIn("procurement_notice", event["sales_signal_basis"])

    def test_no_email_invention(self):
        self.assertIsNone(extract_email("홍길동"))
        self.assertIsNone(extract_email("담당자 김철수"))

    def test_utf8_bom_csv(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.csv"
            write_bom_csv(path, ["행사명"], [{"행사명": "한글행사"}])
            raw = path.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))

    def test_date_parse_failure_preserves_event(self):
        event, err = normalize_intermediate(
            {
                "title": "일정 미정 국제총회",
                "start_date_raw": "202607미정",
                "end_date_raw": "202607미정",
                "date_text": "2026.07.미정 ~ 2026.07.미정",
                "host_raw": "국제기구",
                "source_url": "https://example.com/x",
                "collected_at": "2026-07-16T00:00:00+09:00",
            },
            source_id="k_mice",
            raw_file="x.jsonl",
            today=date(2026, 7, 16),
            past_days=60,
            future_days=550,
        )
        self.assertIsNone(err)
        assert event is not None
        self.assertIsNone(event["start_date"])
        self.assertTrue(event["needs_official_verification"])


class SongdoPaginationPolicyTests(unittest.TestCase):
    def test_month_windows_cover_range(self):
        from app.mice_collectors.songdo_convenia import _month_windows
        from datetime import date

        wins = _month_windows(date(2026, 5, 17), date(2026, 7, 3))
        self.assertEqual(len(wins), 3)
        self.assertEqual(wins[0][0], date(2026, 5, 17))
        self.assertEqual(wins[-1][1], date(2026, 7, 3))


if __name__ == "__main__":
    unittest.main()
