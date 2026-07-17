"""Pre-notice human review priority and route selection tests."""
from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.io_utils import write_jsonl
from app.procurement_normalizers.pre_notice_priority import (
    ALLOWED_PRIORITIES,
    assess_pre_notice_priority,
    priority_sort_key,
)
from app.run_g2b_summary import run_g2b_summary


TODAY = date(2026, 7, 16)


def _base(**overrides):
    rec = {
        "procurement_stage": "PRE_NOTICE",
        "mice_relevant": True,
        "mice_relevance_confidence": "MEDIUM",
        "mice_relevance_score": 3,
        "title": "국제포럼 운영 용역",
        "notice_number": "PRE-1",
        "ordering_organization": "공공기관",
        "announcement_date": "2026-07-10",
        "estimated_amount": None,
        "opportunity_routes": [],
        "detail_verification_status": "NOT_FETCHED",
        "attachment_urls": [],
        "blocking_unknowns": [],
        "url": "https://example.com/pre/1",
    }
    rec.update(overrides)
    return rec


class PreNoticePriorityTests(unittest.TestCase):
    def test_p0_direct_scope_budget_recent(self):
        out = assess_pre_notice_priority(
            _base(
                title="국제회의 참가자 등록 QR 체크인 플랫폼 구축 용역",
                estimated_amount="120000000",
                mice_relevance_confidence="STRONG",
                opportunity_routes=[
                    "DIRECT_PRIME_BID",
                    "SUBCONTRACT_OR_SOLUTION_PARTNER",
                ],
            ),
            today=TODAY,
        )
        self.assertEqual(out["pre_notice_priority"], "P0_DETAIL_REVIEW")
        self.assertEqual(out["primary_opportunity_route"], "DIRECT_PRIME_BID")
        self.assertIn(
            "SUBCONTRACT_OR_SOLUTION_PARTNER",
            out["secondary_opportunity_routes"],
        )
        self.assertIn("DETAIL_NOT_VERIFIED", out["review_blocking_unknowns"])
        self.assertIsNotNone(out["review_deadline"])

    def test_p1_partner_led_full_event(self):
        out = assess_pre_notice_priority(
            _base(
                title="국제박람회 전체 행사 기획·연출·운영 대행 용역",
                opportunity_routes=[
                    "CONSORTIUM_BID",
                    "SUBCONTRACT_OR_SOLUTION_PARTNER",
                ],
                mice_relevance_confidence="STRONG",
            ),
            today=TODAY,
        )
        self.assertEqual(out["pre_notice_priority"], "P1_PARTNER_OUTREACH")
        self.assertEqual(out["primary_opportunity_route"], "CONSORTIUM_BID")

    def test_p2_direct_role_needs_research(self):
        out = assess_pre_notice_priority(
            _base(
                title="참가자 등록 시스템 용역",
                announcement_date="2026-01-01",
                opportunity_routes=["DIRECT_PRIME_BID"],
            ),
            today=TODAY,
        )
        self.assertEqual(out["pre_notice_priority"], "P2_QUALIFICATION_RESEARCH")
        self.assertEqual(out["primary_opportunity_route"], "DIRECT_PRIME_BID")

    def test_p2_partner_route_without_recency_budget_or_strong_signal(self):
        out = assess_pre_notice_priority(
            _base(
                title="행사 운영 대행 용역",
                announcement_date="2026-01-01",
                opportunity_routes=["SUBCONTRACT_OR_SOLUTION_PARTNER"],
            ),
            today=TODAY,
        )
        self.assertEqual(out["pre_notice_priority"], "P2_QUALIFICATION_RESEARCH")

    def test_p3_mice_but_route_or_role_thin(self):
        out = assess_pre_notice_priority(
            _base(title="국제포럼 개최 지원", opportunity_routes=[]),
            today=TODAY,
        )
        self.assertEqual(out["pre_notice_priority"], "P3_WATCH")
        self.assertIsNone(out["primary_opportunity_route"])

    def test_no_action_when_not_mice_relevant(self):
        out = assess_pre_notice_priority(
            _base(
                mice_relevant=False,
                title="사무용품 구매",
                opportunity_routes=["DIRECT_PRIME_BID"],
            ),
            today=TODAY,
        )
        self.assertEqual(out["pre_notice_priority"], "NO_ACTION")
        self.assertIsNone(out["review_deadline"])
        self.assertIsNone(out["primary_opportunity_route"])
        self.assertIn("DIRECT_PRIME_BID", out["secondary_opportunity_routes"])

    def test_only_allowed_priorities_are_emitted(self):
        for rec in (
            _base(mice_relevant=False),
            _base(opportunity_routes=[]),
            _base(
                title="참가자 등록 시스템",
                announcement_date="2026-01-01",
                opportunity_routes=["DIRECT_PRIME_BID"],
            ),
        ):
            out = assess_pre_notice_priority(rec, today=TODAY)
            self.assertIn(out["pre_notice_priority"], ALLOWED_PRIORITIES)

    def test_unverified_detail_never_promotes_go(self):
        out = assess_pre_notice_priority(
            _base(
                title="참가등록 체크인 시스템 구축",
                estimated_amount="100000000",
                mice_relevance_confidence="STRONG",
                opportunity_routes=["DIRECT_PRIME_BID"],
                bid_go_no_go="UNKNOWN",
                bid_participation_readiness="QUALIFICATION_CHECK",
            ),
            today=TODAY,
        )
        self.assertEqual(out["bid_go_no_go"], "UNKNOWN")
        self.assertEqual(out["bid_participation_readiness"], "QUALIFICATION_CHECK")

    def test_priority_csv_contains_required_headers(self):
        row = assess_pre_notice_priority(
            _base(
                title="국제회의 참가자 등록 플랫폼 구축",
                estimated_amount="100000000",
                mice_relevance_confidence="STRONG",
                opportunity_routes=["DIRECT_PRIME_BID"],
                sales_queue_eligible=True,
                sales_priority="P2",
                sales_windows=["PRE_NOTICE_DIRECT_REVIEW"],
                mice_relevance_evidence=["strong:국제회의", "strong:참가자 등록"],
            ),
            today=TODAY,
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            procurements = root / "procurements.jsonl"
            report = root / "reports"
            write_jsonl(procurements, [row])
            run_g2b_summary(procurements_path=procurements, report_dir=report)
            csv_path = report / "g2b-pre-notice-priority-queue.csv"
            self.assertTrue(csv_path.exists())
            header = csv_path.read_text(encoding="utf-8-sig").splitlines()[0]
            for expected in (
                "우선순위",
                "주기회경로",
                "보조경로",
                "사업명",
                "사전규격번호",
                "QRPick·Showda 역할",
                "MICE 적합 근거",
                "직접입찰 근거",
                "파트너 참여 근거",
                "미확인 사항",
                "권장 다음 행동",
                "원문 URL",
            ):
                self.assertIn(expected, header)

    def test_operator_sort_order(self):
        base = {
            "pre_notice_priority": "P1_PARTNER_OUTREACH",
            "announcement_date": "2026-07-10",
            "mice_relevance_confidence": "STRONG",
            "direct_bid_evidence": ["체크인"],
            "estimated_amount": "100",
            "contact_path_verified": True,
        }
        rows = [
            {**base, "title": "older", "announcement_date": "2026-07-09"},
            {**base, "title": "medium", "mice_relevance_confidence": "MEDIUM"},
            {**base, "title": "no-direct", "direct_bid_evidence": []},
            {**base, "title": "no-budget", "estimated_amount": None},
            {**base, "title": "no-contact", "contact_path_verified": False},
            {**base, "title": "best"},
            {**base, "title": "p0", "pre_notice_priority": "P0_DETAIL_REVIEW"},
        ]
        ordered = [row["title"] for row in sorted(rows, key=priority_sort_key)]
        self.assertEqual(
            ordered,
            ["p0", "best", "no-contact", "no-budget", "no-direct", "medium", "older"],
        )

    def test_top30_and_all_candidates_outputs_are_deduplicated(self):
        rows = []
        for index in range(35):
            rows.append(
                assess_pre_notice_priority(
                    _base(
                        title=f"행사 운영 대행 용역 {index:02d}",
                        notice_number=f"PRE-{index:02d}",
                        announcement_date=f"2026-07-{(index % 15) + 1:02d}",
                        mice_relevance_confidence="STRONG",
                        opportunity_routes=[
                            "DIRECT_PRIME_BID",
                            "SUBCONTRACT_OR_SOLUTION_PARTNER",
                        ],
                        sales_queue_eligible=True,
                    ),
                    today=TODAY,
                )
            )
        duplicate = dict(rows[0])
        duplicate["opportunity_routes"] = ["CONSORTIUM_BID"]
        rows.append(duplicate)
        rows.append(
            assess_pre_notice_priority(
                _base(
                    title="사무용품 구매",
                    notice_number="PRE-NO",
                    mice_relevant=False,
                    sales_queue_eligible=False,
                ),
                today=TODAY,
            )
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            procurements = root / "procurements.jsonl"
            report = root / "reports"
            write_jsonl(procurements, rows)
            result = run_g2b_summary(
                procurements_path=procurements,
                report_dir=report,
                top_n=30,
            )
            with (report / "g2b-pre-notice-top30.csv").open(
                encoding="utf-8-sig", newline=""
            ) as fh:
                top_rows = list(csv.DictReader(fh))
            with (report / "g2b-pre-notice-all-candidates.csv").open(
                encoding="utf-8-sig", newline=""
            ) as fh:
                all_rows = list(csv.DictReader(fh))

        self.assertEqual(len(top_rows), 30)
        self.assertEqual(len(all_rows), 35)
        self.assertEqual(result["counts"]["priority_queue"], 30)
        self.assertEqual(result["counts"]["all_pre_notice_candidates"], 35)
        self.assertNotIn("NO_ACTION", {row["우선순위"] for row in top_rows})
        expected_notices = [
            row["notice_number"]
            for row in sorted(rows[:35], key=priority_sort_key)[:30]
        ]
        self.assertEqual(
            [row["사전규격번호"] for row in top_rows],
            expected_notices,
        )


if __name__ == "__main__":
    unittest.main()
