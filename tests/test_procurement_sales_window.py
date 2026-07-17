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

    def test_pre_notice_direct_review_without_deadline(self):
        from app.procurement_normalizers.mice_relevance import apply_mice_and_sales_fields

        rec = {
            "title": "국제회의 참가등록 QR체크인 시스템 구축 용역",
            "organization": "컨벤션센터",
            "ordering_organization": "컨벤션센터",
            "proposal_deadline": None,
            "announcement_date": "2026-07-01",
            "attachment_urls": [],
            "detail_verification_status": "NOT_FETCHED",
            "procurement_stage": "PRE_NOTICE",
            "notice_number": "P-PRE-1",
        }
        mid = apply_sales_windows(
            rec,
            config=self.config,
            bid_rules=self.bid_rules,
            profile=self.profile,
            today=date(2026, 7, 16),
        )
        out = apply_mice_and_sales_fields(mid)
        self.assertTrue(out.get("mice_relevant"))
        self.assertIn("DIRECT_PRIME_BID", out.get("opportunity_routes") or [])
        self.assertIn("PRE_NOTICE_DIRECT_REVIEW", out.get("sales_windows") or [])
        self.assertIn("PRE_NOTICE_REVIEW", out.get("sales_action_types") or [])
        self.assertTrue(out.get("sales_queue_eligible"))
        self.assertNotEqual(out.get("bid_participation_readiness"), "ACTION_NOW")
        self.assertNotEqual(out.get("bid_go_no_go"), "GO")
        self.assertEqual(out.get("bid_participation_readiness"), "QUALIFICATION_CHECK")
        self.assertNotIn("NO_ACTIONABLE_SALES_WINDOW", out.get("sales_queue_exclusion_reasons") or [])

    def test_pre_notice_partner_outreach(self):
        from app.procurement_normalizers.mice_relevance import apply_mice_and_sales_fields

        rec = {
            "title": "국제박람회 행사 운영 대행 용역(공동수급 가능)",
            "organization": "관광공사",
            "ordering_organization": "관광공사",
            "proposal_deadline": None,
            "attachment_urls": [],
            "detail_verification_status": "NOT_FETCHED",
            "procurement_stage": "PRE_NOTICE",
            "notice_number": "P-PRE-2",
        }
        mid = apply_sales_windows(
            rec,
            config=self.config,
            bid_rules=self.bid_rules,
            profile=self.profile,
            today=date(2026, 7, 16),
        )
        out = apply_mice_and_sales_fields(mid)
        self.assertTrue(out.get("mice_relevant"))
        windows = out.get("sales_windows") or []
        # Partner and/or direct review may both apply for event-ops titles.
        self.assertTrue(
            "PRE_NOTICE_PARTNER_OUTREACH" in windows or "PRE_NOTICE_DIRECT_REVIEW" in windows
        )
        self.assertTrue(out.get("sales_queue_eligible"))

    def test_pre_notice_dual_paths_allowed(self):
        from app.procurement_normalizers.mice_relevance import apply_mice_and_sales_fields

        rec = {
            "title": "전시회 참가등록 시스템 및 행사 운영 대행 용역(공동수급)",
            "organization": "센터",
            "ordering_organization": "센터",
            "attachment_urls": [],
            "detail_verification_status": "NOT_FETCHED",
            "procurement_stage": "PRE_NOTICE",
        }
        mid = apply_sales_windows(
            rec,
            config=self.config,
            bid_rules=self.bid_rules,
            profile=self.profile,
            today=date(2026, 7, 16),
        )
        out = apply_mice_and_sales_fields(mid)
        types = out.get("sales_action_types") or []
        windows = out.get("sales_windows") or []
        if "PRE_NOTICE_DIRECT_REVIEW" in windows and "PRE_NOTICE_PARTNER_OUTREACH" in windows:
            self.assertIn("PRE_NOTICE_REVIEW", types)
            self.assertIn("PARTNER_OUTREACH", types)

    def test_mice_irrelevant_pre_notice_no_queue(self):
        from app.procurement_normalizers.mice_relevance import apply_mice_and_sales_fields

        rec = {
            "title": "사무용품 물품구매 사전규격",
            "organization": "기관",
            "ordering_organization": "기관",
            "procurement_stage": "PRE_NOTICE",
            "detail_verification_status": "NOT_FETCHED",
            "attachment_urls": [],
        }
        mid = apply_sales_windows(
            rec,
            config=self.config,
            bid_rules=self.bid_rules,
            profile=self.profile,
            today=date(2026, 7, 16),
        )
        out = apply_mice_and_sales_fields(mid)
        self.assertFalse(out.get("mice_relevant"))
        self.assertFalse(out.get("sales_queue_eligible"))
        self.assertIn("NO_ACTION", out.get("sales_action_types") or ["NO_ACTION"])


if __name__ == "__main__":
    unittest.main()
