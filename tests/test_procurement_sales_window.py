"""Procurement sales window tests."""
from __future__ import annotations

import unittest
from datetime import date

from app.io_utils import load_yaml, project_root
from app.procurement_normalizers.sales_window import apply_sales_windows


class SalesWindowTests(unittest.TestCase):
    def setUp(self):
        self.config = load_yaml(project_root() / "config" / "g2b-mice-lifecycle.yaml")
        self.bid_rules = load_yaml(project_root() / "config" / "bid-assessment-rules.yaml")
        self.profile = load_yaml(project_root() / "config" / "qrpick-profile.yaml")

    def test_direct_bid_window_before_deadline(self):
        rec = {
            "title": "국제전시회 참가등록 QR체크인 시스템 구축 용역 입찰",
            "organization": "컨벤션센터",
            "ordering_organization": "컨벤션센터",
            "proposal_deadline": "2026-08-20",
            "announcement_date": "2026-07-01",
            "attachment_urls": [],
            "detail_verification_status": "NOT_FETCHED",
            "procurement_stage": "BID_NOTICE",
            "registration_open_status": "UNKNOWN",
        }
        out = apply_sales_windows(
            rec,
            config=self.config,
            bid_rules=self.bid_rules,
            profile=self.profile,
            today=date(2026, 7, 16),
        )
        self.assertTrue(out.get("bid_assessment_applicable"))
        self.assertIn("DIRECT_PRIME_BID", out.get("opportunity_routes") or [])
        self.assertIn("DIRECT_BID_WINDOW", out.get("sales_windows") or [])
        self.assertNotEqual(out.get("eligibility_status"), "NOT_ELIGIBLE")

    def test_award_winner_window_and_unknown_supplier(self):
        rec = {
            "title": "국제포럼 운영 대행 용역",
            "organization": "관광공사",
            "ordering_organization": "관광공사",
            "award_date": "2026-07-01",
            "event_date": "2026-10-01",
            "awardee_organizations": ["낙찰사A"],
            "attachment_urls": ["https://example.com/rfp.pdf"],
            "detail_verification_status": "NOT_FETCHED",
            "procurement_stage": "AWARD_RESULT",
            "registration_open_status": "UNKNOWN",
            "proposal_deadline": "2026-06-01",
        }
        out = apply_sales_windows(
            rec,
            config=self.config,
            bid_rules=self.bid_rules,
            profile=self.profile,
            today=date(2026, 7, 16),
        )
        self.assertIn("AWARD_WINNER_WINDOW", out.get("sales_windows") or [])
        self.assertEqual(out.get("system_supplier_status"), "UNKNOWN")
        self.assertEqual(out.get("registration_open_status"), "UNKNOWN")
        self.assertIn("PRE_REGISTRATION_WINDOW", out.get("sales_windows") or [])

    def test_deadline_vs_eligibility_separation(self):
        rec = {
            "title": "세미나 운영시스템 구축 용역 입찰",
            "organization": "지자체",
            "ordering_organization": "지자체",
            "proposal_deadline": "2026-03-01",
            "attachment_urls": [],
            "detail_verification_status": "NOT_FETCHED",
            "procurement_stage": "BID_NOTICE",
        }
        out = apply_sales_windows(
            rec,
            config=self.config,
            bid_rules=self.bid_rules,
            profile=self.profile,
            today=date(2026, 7, 16),
        )
        self.assertEqual(out.get("eligibility_status"), "UNKNOWN_NEEDS_DOCUMENT_REVIEW")
        self.assertEqual(out.get("bid_participation_readiness"), "NO_BID")
        self.assertEqual(out.get("bid_go_no_go"), "NO_GO")

    def test_multi_routes_preserved(self):
        rec = {
            "title": "전시 참가등록 시스템 구축 용역 입찰(공동수급)",
            "organization": "센터",
            "ordering_organization": "센터",
            "proposal_deadline": "2026-09-01",
            "attachment_urls": [],
            "detail_verification_status": "NOT_FETCHED",
            "procurement_stage": "BID_NOTICE",
        }
        out = apply_sales_windows(
            rec,
            config=self.config,
            bid_rules=self.bid_rules,
            profile=self.profile,
            today=date(2026, 7, 16),
        )
        routes = out.get("opportunity_routes") or []
        self.assertTrue(len(routes) >= 1)
        if len(routes) > 1:
            self.assertTrue(out.get("primary_route") in routes)


if __name__ == "__main__":
    unittest.main()
