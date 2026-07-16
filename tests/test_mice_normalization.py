"""Tests for MICE field normalization and org role separation."""
from __future__ import annotations

import unittest
from datetime import date

from app.mice_normalizers.event_normalizer import normalize_intermediate
from app.mice_normalizers.text_utils import extract_email, normalize_title


class MiceNormalizationTests(unittest.TestCase):
    def test_korean_title_normalized(self):
        self.assertTrue(normalize_title("2026 서울국제식품산업대전"))
        self.assertEqual(
            normalize_title("제1회 테스트 전시회"),
            normalize_title("제1회  테스트  전시회"),
        )

    def test_host_organizer_fields_separated(self):
        event, err = normalize_intermediate(
            {
                "title": "테스트 전시회",
                "start_date_raw": "20260720",
                "end_date_raw": "20260722",
                "host_raw": "한국전시협회",
                "organizer_raw": "쇼다운영",
                "operator_raw": "사무국A",
                "source_url": "https://example.com/a",
                "collected_at": "2026-07-15T00:00:00+09:00",
            },
            source_id="songdo_convenia",
            raw_file="x.jsonl",
            today=date(2026, 7, 15),
            past_days=60,
            future_days=550,
        )
        self.assertIsNone(err)
        assert event is not None
        self.assertEqual(event["host_organizations"], ["한국전시협회"])
        self.assertEqual(event["organizer_organizations"], ["쇼다운영"])
        self.assertEqual(event["operator_organizations"], ["사무국A"])

    def test_contact_source_preserved(self):
        event, err = normalize_intermediate(
            {
                "title": "공개연락 행사",
                "start_date_raw": "20260801",
                "end_date_raw": "20260802",
                "inquiry_raw": "info@example.org",
                "source_url": "https://example.com/event/1",
                "collected_at": "2026-07-15T00:00:00+09:00",
            },
            source_id="songdo_convenia",
            raw_file="x.jsonl",
            today=date(2026, 7, 15),
            past_days=60,
            future_days=550,
        )
        self.assertIsNone(err)
        assert event is not None
        self.assertEqual(event["contact_email"], "info@example.org")
        self.assertEqual(event["contact_source_url"], "https://example.com/event/1")
        self.assertEqual(event["contact_confidence"], "VERIFIED_PUBLIC_OFFICIAL_SOURCE")

    def test_no_email_invention(self):
        self.assertIsNone(extract_email("홍길동"))
        self.assertIsNone(extract_email("담당자 김철수"))


if __name__ == "__main__":
    unittest.main()
