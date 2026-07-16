"""Previous-cycle matcher tests."""
from __future__ import annotations

import unittest
from datetime import date

from app.procurement_normalizers.previous_cycle_matcher import match_previous_cycles


class PreviousCycleTests(unittest.TestCase):
    def test_strong_previous_year_match(self):
        current = [
            {
                "procurement_id": "g2b:notice:2026A:00",
                "title": "2026 국제 MICE 포럼 운영 대행 용역",
                "ordering_organization": "한국관광공사",
                "demand_organization": "한국관광공사",
                "announcement_date": "2026-03-01",
            }
        ]
        history = [
            {
                "procurement_id": "g2b:notice:2025A:00",
                "title": "2025 국제 MICE 포럼 운영 대행 용역",
                "ordering_organization": "한국관광공사",
                "demand_organization": "한국관광공사",
                "announcement_date": "2025-03-05",
                "award_date": "2025-04-01",
                "awardee_organizations": ["전년낙찰사"],
                "contract_amount": "90000000",
                "notice_number": "2025A",
            }
        ]
        out, stats = match_previous_cycles(current, history, today=date(2026, 7, 16))
        self.assertEqual(stats["STRONG"], 1)
        self.assertEqual(out[0]["previous_cycle_confidence"], "STRONG")
        self.assertEqual(out[0]["previous_awardees"], ["전년낙찰사"])

    def test_similar_title_different_org_not_strong(self):
        current = [
            {
                "procurement_id": "c1",
                "title": "2026 스마트시티 포럼 운영",
                "ordering_organization": "A기관",
                "announcement_date": "2026-05-01",
            }
        ]
        history = [
            {
                "procurement_id": "h1",
                "title": "2025 바이오 포럼 운영",
                "ordering_organization": "B기관",
                "announcement_date": "2025-05-01",
            }
        ]
        out, stats = match_previous_cycles(current, history, today=date(2026, 7, 16))
        self.assertEqual(out[0]["previous_cycle_confidence"], "NONE")
        self.assertEqual(stats["STRONG"], 0)


if __name__ == "__main__":
    unittest.main()
