"""Tests for Showda · QRPick direct / consortium bid assessment."""
from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from app.evaluators.bid_assessment import (
    assess_bid_opportunity,
    is_consortium_candidate,
    is_direct_bid_candidate,
    is_solution_partner_candidate,
)
from app.evaluators.rule_filter import apply_first_pass
from app.io_utils import load_yaml, project_root


def _bid_rules():
    return load_yaml(project_root() / "config" / "bid-assessment-rules.yaml")


def _rules():
    return load_yaml(project_root() / "config" / "filter-rules.yaml")


def _profile():
    return load_yaml(project_root() / "config" / "qrpick-profile.yaml")


class DirectBidAssessmentTests(unittest.TestCase):
    def test_qrpick_standard_direct_route_without_docs_is_unknown(self):
        rec = {
            "title": "국제전시회 참가등록·QR 체크인 시스템 구축 용역 입찰공고",
            "organization": "○○컨벤션센터",
            "source": "bizinfo",
            "source_id": "B1",
            "deadline": "2026-08-20",
            "dday": 35,
            "support_amount": "2억원",
            "attachment_urls": [],
            "detail_verification_status": "NOT_FETCHED",
            "url": "https://example.com/bid/1",
        }
        bid = assess_bid_opportunity(
            rec,
            _bid_rules(),
            profile=_profile(),
            asset_fit={
                "opportunity_type": "PROCUREMENT_OR_BUILD",
                "primary_asset_fit_path": "CUSTOM_BUILD_SERVICE",
                "matched_asset_families": ["QRPICK_EVENT_OPERATIONS"],
                "usable_qrpick_features": ["등록", "체크인"],
            },
            today=date(2026, 7, 16),
        )
        self.assertIn("DIRECT_PRIME_BID", bid["opportunity_routes"])
        self.assertIn(
            bid["direct_bid_fit_path"],
            {"QRPICK_STANDARD_SERVICE", "QRPICK_PLUS_OPERATION", "SHOWDA_CUSTOM_BUILD"},
        )
        self.assertEqual(bid["eligibility_status"], "UNKNOWN_NEEDS_DOCUMENT_REVIEW")
        self.assertEqual(bid["bid_participation_readiness"], "QUALIFICATION_CHECK")
        self.assertNotEqual(bid["bid_go_no_go"], "GO")
        self.assertNotEqual(bid["eligibility_status"], "VERIFIED_ELIGIBLE")
        self.assertIn("DIRECT_BID_WINDOW", bid["sales_windows"])

    def test_industry_name_alone_does_not_block_sw_ops_role(self):
        rec = {
            "title": "바이오 전시회 등록·체크인·비즈니스매칭 플랫폼 구축 용역",
            "organization": "협회",
            "source": "nipa",
            "source_id": "N1",
            "deadline": "2026-09-01",
            "dday": 47,
            "attachment_urls": [],
            "detail_verification_status": "NOT_FETCHED",
        }
        bid = assess_bid_opportunity(
            rec,
            _bid_rules(),
            profile=_profile(),
            asset_fit={
                "opportunity_type": "PROCUREMENT_OR_BUILD",
                "primary_asset_fit_path": "CUSTOM_BUILD_SERVICE",
                "matched_asset_families": ["QRPICK_EVENT_OPERATIONS"],
            },
            today=date(2026, 7, 16),
        )
        self.assertIn("DIRECT_PRIME_BID", bid["opportunity_routes"])
        self.assertNotEqual(bid["direct_bid_fit_path"], "NO_REALISTIC_DIRECT_BID_PATH")

    def test_consortium_path_when_event_production_dominant(self):
        rec = {
            "title": "국제포럼 행사기획·연출·무대·홍보 및 운영시스템 구축 용역(공동수급 가능)",
            "organization": "관광공사",
            "source": "bizinfo",
            "source_id": "B2",
            "deadline": "2026-08-10",
            "dday": 25,
            "attachment_urls": [],
            "detail_verification_status": "NOT_FETCHED",
        }
        bid = assess_bid_opportunity(
            rec,
            _bid_rules(),
            profile=_profile(),
            asset_fit={
                "opportunity_type": "PROCUREMENT_OR_BUILD",
                "primary_asset_fit_path": "PARTNER_CONSORTIUM",
                "matched_asset_families": ["QRPICK_EVENT_OPERATIONS"],
                "partner_required_scope": ["행사기획", "무대"],
            },
            today=date(2026, 7, 16),
        )
        self.assertIn("CONSORTIUM_BID", bid["opportunity_routes"])
        self.assertIn(
            bid["direct_bid_fit_path"],
            {"CONSORTIUM_REQUIRED", "SHOWDA_CUSTOM_BUILD", "QRPICK_PLUS_OPERATION"},
        )
        self.assertTrue(any(w.startswith("CONSORTIUM") for w in bid["sales_windows"]))
        self.assertTrue(is_consortium_candidate({**rec, **bid}))

    def test_never_verified_or_go_without_attachments(self):
        rec = {
            "title": "MICE 운영시스템 SaaS 구축 입찰",
            "organization": "지자체",
            "source": "g2b",
            "source_id": "G1",
            "deadline": "2026-07-30",
            "dday": 14,
            "support_amount": "1.5억",
            "attachment_urls": [],
            "detail_verification_status": "VERIFIED",  # even if marked verified
            "actionability_verified": True,
        }
        bid = assess_bid_opportunity(
            rec,
            _bid_rules(),
            profile=_profile(),
            asset_fit={
                "opportunity_type": "PROCUREMENT_OR_BUILD",
                "primary_asset_fit_path": "CUSTOM_BUILD_SERVICE",
            },
            today=date(2026, 7, 16),
        )
        self.assertNotEqual(bid["eligibility_status"], "VERIFIED_ELIGIBLE")
        self.assertNotEqual(bid["bid_go_no_go"], "GO")
        self.assertNotEqual(bid["bid_participation_readiness"], "ACTION_NOW")

    def test_first_pass_wires_bid_fields(self):
        rec = {
            "title": "전시회 참가등록 QR체크인 시스템 구축 용역 입찰",
            "organization": "코엑스",
            "source": "bizinfo",
            "source_id": "X1",
            "program": "용역",
            "category": "정보화",
            "deadline": "2026-08-15",
            "dday": 30,
            "url": "https://example.com/x1",
            "attachment_urls": [],
            "detail_verification_status": "NOT_FETCHED",
        }
        out = apply_first_pass(rec, _rules(), _profile(), today=date(2026, 7, 16))
        self.assertTrue(out.get("opportunity_routes"))
        self.assertTrue(is_direct_bid_candidate(out))
        self.assertEqual(out.get("eligibility_status"), "UNKNOWN_NEEDS_DOCUMENT_REVIEW")
        self.assertEqual(out.get("action_queue"), "QUALIFICATION_CHECK")


class BidAssessmentScopeGateTests(unittest.TestCase):
    def test_simple_grant_not_applicable(self):
        rec = {
            "title": "예비창업패키지 창업지원금 지원사업 모집",
            "organization": "중기부",
            "source": "kstartup",
            "source_id": "K1",
            "deadline": "2026-08-01",
            "dday": 16,
        }
        bid = assess_bid_opportunity(
            rec,
            _bid_rules(),
            profile=_profile(),
            asset_fit={"opportunity_type": "SUPPORT_PROGRAM"},
            today=date(2026, 7, 16),
        )
        self.assertFalse(bid["bid_assessment_applicable"])
        self.assertEqual(bid["opportunity_routes"], [])
        self.assertIsNone(bid["bid_go_no_go"])
        self.assertFalse(is_direct_bid_candidate({**rec, **bid}))

    def test_exhibitor_recruitment_excluded_by_default(self):
        rec = {
            "title": "스마트모빌리티 전시회 참가기업 모집",
            "organization": "협회",
            "source": "bizinfo",
            "source_id": "E1",
            "deadline": "2026-08-01",
            "dday": 16,
        }
        bid = assess_bid_opportunity(
            rec,
            _bid_rules(),
            profile=_profile(),
            asset_fit={"opportunity_type": "EXHIBITION_OR_MARKET_ACCESS"},
            today=date(2026, 7, 16),
        )
        self.assertFalse(bid["bid_assessment_applicable"])
        self.assertNotIn("DIRECT_PRIME_BID", bid["opportunity_routes"])

    def test_operator_recruitment_is_applicable(self):
        rec = {
            "title": "지역 MICE 운영사업자 모집 공고",
            "organization": "관광공사",
            "source": "bizinfo",
            "source_id": "O1",
            "deadline": "2026-08-20",
            "dday": 35,
            "attachment_urls": [],
            "detail_verification_status": "NOT_FETCHED",
        }
        bid = assess_bid_opportunity(
            rec,
            _bid_rules(),
            profile=_profile(),
            asset_fit={
                "opportunity_type": "PROCUREMENT_OR_BUILD",
                "primary_asset_fit_path": "CUSTOM_BUILD_SERVICE",
                "matched_asset_families": ["QRPICK_EVENT_OPERATIONS"],
                "usable_qrpick_features": ["등록"],
            },
            today=date(2026, 7, 16),
        )
        self.assertTrue(bid["bid_assessment_applicable"])

    def test_event_ops_service_is_applicable(self):
        rec = {
            "title": "국제회의 행사 운영 대행 용역",
            "organization": "지자체",
            "source": "bizinfo",
            "source_id": "O2",
            "deadline": "2026-09-01",
            "dday": 47,
            "attachment_urls": [],
        }
        bid = assess_bid_opportunity(
            rec,
            _bid_rules(),
            profile=_profile(),
            asset_fit={"opportunity_type": "PROCUREMENT_OR_BUILD"},
            today=date(2026, 7, 16),
        )
        self.assertTrue(bid["bid_assessment_applicable"])

    def test_system_build_service_is_applicable(self):
        rec = {
            "title": "전시 참가등록 시스템 구축 용역 입찰",
            "organization": "컨벤션",
            "source": "bizinfo",
            "source_id": "S1",
            "deadline": "2026-09-01",
            "dday": 47,
            "attachment_urls": [],
            "detail_verification_status": "NOT_FETCHED",
        }
        bid = assess_bid_opportunity(
            rec,
            _bid_rules(),
            profile=_profile(),
            asset_fit={
                "opportunity_type": "PROCUREMENT_OR_BUILD",
                "primary_asset_fit_path": "CUSTOM_BUILD_SERVICE",
                "usable_qrpick_features": ["등록"],
            },
            today=date(2026, 7, 16),
        )
        self.assertTrue(bid["bid_assessment_applicable"])
        self.assertIn("DIRECT_PRIME_BID", bid["opportunity_routes"])

    def test_no_go_without_detail_and_attachments(self):
        rec = {
            "title": "MICE 플랫폼 구축 용역 입찰",
            "organization": "공사",
            "source": "bizinfo",
            "source_id": "G2",
            "deadline": "2026-08-01",
            "dday": 16,
            "attachment_urls": [],
            "detail_verification_status": "NOT_FETCHED",
        }
        bid = assess_bid_opportunity(
            rec,
            _bid_rules(),
            profile=_profile(),
            asset_fit={
                "opportunity_type": "PROCUREMENT_OR_BUILD",
                "primary_asset_fit_path": "CUSTOM_BUILD_SERVICE",
            },
            today=date(2026, 7, 16),
        )
        self.assertNotEqual(bid["bid_go_no_go"], "GO")
        self.assertNotEqual(bid["eligibility_status"], "VERIFIED_ELIGIBLE")

    def test_non_applicable_excluded_from_direct_csv_helper(self):
        rec = {
            "title": "입주기업 모집 공고",
            "organization": "센터",
            "source": "kstartup",
            "source_id": "I1",
            "deadline": "2026-08-01",
            "dday": 16,
            "bid_assessment_applicable": False,
            "opportunity_routes": ["DIRECT_PRIME_BID"],  # should still be excluded
            "direct_bid_fit_path": "QRPICK_STANDARD_SERVICE",
        }
        self.assertFalse(is_direct_bid_candidate(rec))
        self.assertFalse(is_consortium_candidate(rec))

    def test_no_direct_prime_without_procurement_signal(self):
        rec = {
            "title": "스마트시티 산업 세미나 안내",
            "organization": "협회",
            "source": "bizinfo",
            "source_id": "N2",
            "deadline": "2026-08-01",
            "dday": 16,
        }
        bid = assess_bid_opportunity(
            rec,
            _bid_rules(),
            profile=_profile(),
            asset_fit={"opportunity_type": "NETWORKING"},
            today=date(2026, 7, 16),
        )
        self.assertFalse(bid["bid_assessment_applicable"])
        self.assertNotIn("DIRECT_PRIME_BID", bid["opportunity_routes"])

    def test_consortium_partner_window_enum(self):
        rec = {
            "title": "국제포럼 행사기획·연출 및 운영시스템 구축 용역(공동수급)",
            "organization": "관광공사",
            "source": "bizinfo",
            "source_id": "C1",
            "deadline": "2026-08-10",
            "dday": 25,
            "attachment_urls": [],
        }
        bid = assess_bid_opportunity(
            rec,
            _bid_rules(),
            profile=_profile(),
            asset_fit={
                "opportunity_type": "PROCUREMENT_OR_BUILD",
                "primary_asset_fit_path": "PARTNER_CONSORTIUM",
                "matched_asset_families": ["QRPICK_EVENT_OPERATIONS"],
            },
            today=date(2026, 7, 16),
        )
        self.assertIn("CONSORTIUM_PARTNER_WINDOW", bid["sales_windows"])
        self.assertNotIn("CONSORTIUM_PLATFORM_WINDOW", bid["sales_windows"])


    def test_procurement_office_recruitment_not_bid(self):
        rec = {
            "title": "2026년 조달청 벤처나라 추천기업 모집 공고",
            "organization": "창조경제혁신센터",
            "source": "bizinfo",
            "source_id": "P1",
            "deadline": "2026-08-01",
            "dday": "D-16",
        }
        bid = assess_bid_opportunity(
            rec,
            _bid_rules(),
            profile=_profile(),
            asset_fit={"opportunity_type": "SUPPORT_PROGRAM"},
            today=date(2026, 7, 16),
        )
        self.assertFalse(bid["bid_assessment_applicable"])

    def test_dday_string_past_forces_no_bid(self):
        rec = {
            "title": "전시 참가등록 시스템 구축 용역 입찰",
            "organization": "컨벤션",
            "source": "bizinfo",
            "source_id": "D1",
            "deadline": "2026-03-01",
            "dday": "D+100",
            "attachment_urls": [],
            "detail_verification_status": "NOT_FETCHED",
        }
        bid = assess_bid_opportunity(
            rec,
            _bid_rules(),
            profile=_profile(),
            asset_fit={
                "opportunity_type": "PROCUREMENT_OR_BUILD",
                "usable_qrpick_features": ["등록"],
            },
            today=date(2026, 7, 16),
        )
        self.assertTrue(bid["bid_assessment_applicable"])
        self.assertEqual(bid["bid_participation_readiness"], "NO_BID")
        self.assertEqual(bid["bid_go_no_go"], "NO_GO")
        # Deadline alone must not force NOT_ELIGIBLE
        self.assertEqual(bid["eligibility_status"], "UNKNOWN_NEEDS_DOCUMENT_REVIEW")
        self.assertNotEqual(bid["eligibility_status"], "NOT_ELIGIBLE")


class BidRouteCsvSeparationTests(unittest.TestCase):
    def test_deadline_alone_does_not_set_not_eligible(self):
        rec = {
            "title": "국제회의 운영 대행 용역 입찰",
            "organization": "공사",
            "source": "bizinfo",
            "source_id": "E1",
            "deadline": "2026-01-01",
            "dday": "D+50",
            "attachment_urls": [],
            "detail_verification_status": "NOT_FETCHED",
        }
        bid = assess_bid_opportunity(
            rec,
            _bid_rules(),
            profile=_profile(),
            asset_fit={
                "opportunity_type": "PROCUREMENT_OR_BUILD",
                "matched_asset_families": ["QRPICK_EVENT_OPERATIONS"],
            },
            today=date(2026, 7, 16),
        )
        self.assertEqual(bid["eligibility_status"], "UNKNOWN_NEEDS_DOCUMENT_REVIEW")
        self.assertEqual(bid["bid_participation_readiness"], "NO_BID")
        self.assertEqual(bid["bid_go_no_go"], "NO_GO")

    def test_route_helpers_are_mutually_selective(self):
        base = {
            "bid_assessment_applicable": True,
            "direct_bid_fit_path": "QRPICK_PLUS_OPERATION",
            "opportunity_routes": [
                "DIRECT_PRIME_BID",
                "CONSORTIUM_BID",
                "SUBCONTRACT_OR_SOLUTION_PARTNER",
            ],
        }
        self.assertTrue(is_direct_bid_candidate(base))
        self.assertTrue(is_consortium_candidate(base))
        self.assertTrue(is_solution_partner_candidate(base))

        only_partner = {
            "bid_assessment_applicable": True,
            "direct_bid_fit_path": "PARTNER_SPECIALIST_REQUIRED",
            "opportunity_routes": ["SUBCONTRACT_OR_SOLUTION_PARTNER"],
        }
        self.assertFalse(is_direct_bid_candidate(only_partner))
        self.assertFalse(is_consortium_candidate(only_partner))
        self.assertTrue(is_solution_partner_candidate(only_partner))

        only_consortium = {
            "bid_assessment_applicable": True,
            "direct_bid_fit_path": "CONSORTIUM_REQUIRED",
            "opportunity_routes": ["CONSORTIUM_BID"],
        }
        self.assertFalse(is_direct_bid_candidate(only_consortium))
        self.assertTrue(is_consortium_candidate(only_consortium))
        self.assertFalse(is_solution_partner_candidate(only_consortium))

    def test_csv_writers_split_routes_and_empty_consortium_header(self):
        import tempfile
        from pathlib import Path

        from app.io_utils import (
            CONSORTIUM_COLUMNS,
            DIRECT_BID_COLUMNS,
            SOLUTION_PARTNER_COLUMNS,
            write_mapped_csv_bom,
        )

        multi = {
            "bid_assessment_applicable": True,
            "source_scope": "PHASE2_PROCUREMENT_LIKE_NOT_G2B_COLLECTOR",
            "title": "등록·체크인 시스템 구축 용역(공동수급)",
            "organization": "센터",
            "source_id": "M1",
            "url": "https://example.com/m1",
            "opportunity_routes": [
                "DIRECT_PRIME_BID",
                "CONSORTIUM_BID",
                "SUBCONTRACT_OR_SOLUTION_PARTNER",
            ],
            "primary_route": "DIRECT_PRIME_BID",
            "direct_bid_fit_path": "QRPICK_STANDARD_SERVICE",
            "eligibility_status": "UNKNOWN_NEEDS_DOCUMENT_REVIEW",
            "bid_participation_readiness": "QUALIFICATION_CHECK",
            "bid_go_no_go": "UNKNOWN",
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            direct_p = root / "direct-bid-opportunities.csv"
            consort_p = root / "consortium-opportunities.csv"
            partner_p = root / "solution-partner-opportunities.csv"
            write_mapped_csv_bom(direct_p, DIRECT_BID_COLUMNS, [multi])
            write_mapped_csv_bom(consort_p, CONSORTIUM_COLUMNS, [])  # 0 rows → header only
            write_mapped_csv_bom(partner_p, SOLUTION_PARTNER_COLUMNS, [multi])

            d_text = direct_p.read_text(encoding="utf-8-sig")
            c_text = consort_p.read_text(encoding="utf-8-sig")
            p_text = partner_p.read_text(encoding="utf-8-sig")
            self.assertTrue(direct_p.read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertTrue(consort_p.read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertIn("기회경로", d_text)
            self.assertIn("대표경로", d_text)
            self.assertIn("DIRECT_PRIME_BID", d_text)
            self.assertEqual(len(d_text.strip().splitlines()), 2)
            self.assertEqual(len(c_text.strip().splitlines()), 1)  # header only
            self.assertIn("기회경로", c_text)
            self.assertEqual(len(p_text.strip().splitlines()), 2)
            self.assertIn("SUBCONTRACT_OR_SOLUTION_PARTNER", p_text)

    def test_primary_route_prefers_direct(self):
        from app.evaluators.bid_assessment import primary_opportunity_route

        self.assertEqual(
            primary_opportunity_route(
                ["SUBCONTRACT_OR_SOLUTION_PARTNER", "DIRECT_PRIME_BID", "CONSORTIUM_BID"]
            ),
            "DIRECT_PRIME_BID",
        )
        self.assertEqual(primary_opportunity_route(["CONSORTIUM_BID"]), "CONSORTIUM_BID")
        self.assertIsNone(primary_opportunity_route([]))


if __name__ == "__main__":
    unittest.main()
