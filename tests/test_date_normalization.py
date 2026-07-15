import unittest
from datetime import date

from app.normalizers.date_utils import dday_from_deadline, is_expired, parse_date


class TestDateNormalization(unittest.TestCase):
    def test_parse_iso(self):
        self.assertEqual(parse_date("2026-07-30"), "2026-07-30")

    def test_parse_dotted(self):
        self.assertEqual(parse_date("2026.07.30"), "2026-07-30")

    def test_parse_korean(self):
        self.assertEqual(parse_date("2026년 7월 30일"), "2026-07-30")

    def test_invalid(self):
        self.assertIsNone(parse_date("상시모집"))
        self.assertIsNone(parse_date(""))

    def test_expired(self):
        today = date(2026, 7, 15)
        self.assertTrue(is_expired("2026-07-14", today=today))
        self.assertFalse(is_expired("2026-07-15", today=today))
        self.assertFalse(is_expired(None, today=today))

    def test_dday(self):
        today = date(2026, 7, 15)
        self.assertEqual(dday_from_deadline("2026-07-20", today=today), "D-5")
        self.assertEqual(dday_from_deadline("2026-07-15", today=today), "D-Day")


if __name__ == "__main__":
    unittest.main()
