"""Tests for MICE date parsing."""
from __future__ import annotations

import unittest
from datetime import date

from app.mice_normalizers.date_utils import (
    in_collection_window,
    parse_mice_date,
    parse_mice_date_range,
)


class MiceDateTests(unittest.TestCase):
    def test_single_date(self):
        self.assertEqual(parse_mice_date("2026-07-15"), "2026-07-15")
        self.assertEqual(parse_mice_date("20260715"), "2026-07-15")

    def test_range(self):
        s, e, text = parse_mice_date_range(date_text="2026.07.01 ~ 2026.07.03")
        self.assertEqual(s, "2026-07-01")
        self.assertEqual(e, "2026-07-03")
        self.assertIn("2026", text or "")

    def test_year_boundary(self):
        s, e, _ = parse_mice_date_range(date_text="2025.12.30 ~ 01.02")
        self.assertEqual(s, "2025-12-30")
        self.assertEqual(e, "2026-01-02")

    def test_tbd_day_not_forced(self):
        self.assertIsNone(parse_mice_date("202607미정"))
        s, e, text = parse_mice_date_range(
            start_raw="202607미정",
            end_raw="202607미정",
            date_text="2026.07.미정 ~ 2026.07.미정",
        )
        self.assertIsNone(s)
        self.assertIsNone(e)
        self.assertTrue(text)

    def test_window_filter(self):
        today = date(2026, 7, 15)
        self.assertTrue(
            in_collection_window("2026-08-01", "2026-08-03", today=today, past_days=60, future_days=550)
        )
        self.assertFalse(
            in_collection_window("2020-01-01", "2020-01-05", today=today, past_days=60, future_days=550)
        )


if __name__ == "__main__":
    unittest.main()
