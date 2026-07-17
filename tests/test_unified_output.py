"""Product-wide unified opportunity output tests."""
from __future__ import annotations

import csv
import json
import os
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from app.io_utils import write_jsonl
from app.run_unified_output import UnifiedOutputError, run_unified_output
from app.unified_opportunities import (
    adapt_record,
    merge_unified_records,
    unified_sort_key,
)


TODAY = date(2026, 7, 17)


def _support(index: int = 1, **overrides):
    record = {
        "canonical_id": f"support-{index}",
        "opportunity_id": f"op-{index}",
        "source": "kstartup",
        "source_id": f"K-{index}",
        "title": f"MICE 실증 지원사업 {index}",
        "organization": "지원기관",
        "posted_at": "2026-07-16",
        "deadline": "2026-08-10",
        "first_pass_status": "REVIEW",
        "action_queue": "QUALIFICATION_CHECK",
        "primary_asset_fit_path": "QRPICK_DIRECT",
        "usable_qrpick_features": ["등록", "체크인"],
        "fit_evidence": ["MICE_TASK_EVIDENCE"],
        "recommended_next_action": "상세 자격과 실증 과제를 확인",
        "detail_url": f"https://example.com/support/{index}",
    }
    record.update(overrides)
    return record


def _mice(index: int = 1, **overrides):
    record = {
        "canonical_event_id": f"event-{index}",
        "event_id": f"event-row-{index}",
        "source_id": "official-event",
        "source_event_id": f"E-{index}",
        "title": f"국제 컨벤션 {index}",
        "organizer_organizations": ["행사조직위원회"],
        "collected_at": "2026-07-16T00:00:00Z",
        "start_date": "2026-09-01",
        "event_status": "UPCOMING",
        "sales_readiness": "CONTACTABLE",
        "sales_signal_types": ["ORGANIZER_OUTREACH"],
        "sales_signal_basis": ["contact_email"],
        "qrpick_service_matches": ["참가등록", "체크인"],
        "contact_email": "public@example.com",
        "contact_source_url": f"https://example.com/event/{index}",
        "contact_confidence": "HIGH",
        "official_event_url": f"https://example.com/event/{index}",
        "suggested_sales_action": "주최기관에 등록·체크인 제안",
    }
    record.update(overrides)
    return record


def _procurement(stage: str = "PRE_NOTICE", index: int = 1, **overrides):
    record = {
        "procurement_id": f"g2b-{stage}-{index}",
        "lifecycle_group_id": f"g2b:lg:{index}",
        "notice_number": f"R-{index}",
        "procurement_stage": stage,
        "title": f"국제행사 등록 시스템 용역 {index}",
        "ordering_organization": "조달기관",
        "announcement_date": "2026-07-16",
        "proposal_deadline": "2026-08-05",
        "mice_relevant": True,
        "mice_relevance_evidence": ["strong:참가자 등록"],
        "opportunity_routes": [
            "DIRECT_PRIME_BID",
            "SUBCONTRACT_OR_SOLUTION_PARTNER",
        ],
        "primary_opportunity_route": "DIRECT_PRIME_BID",
        "direct_bid_evidence": ["참가자 등록"],
        "priority_role_scope": ["등록", "체크인"],
        "sales_queue_eligible": True,
        "pre_notice_priority": "P1_PARTNER_OUTREACH",
        "bid_assessment_applicable": True,
        "detail_verification_status": "NOT_FETCHED",
        "recommended_review_action": "첨부·자격·역할 확인",
        "url": f"https://example.com/g2b/{index}",
    }
    record.update(overrides)
    return record


class UnifiedOpportunityTests(unittest.TestCase):
    def test_native_domain_scores_are_not_compared(self):
        low = adapt_record(
            _support(first_pass_score=0, mice_relevance_score=0),
            source_domain="support",
            today=TODAY,
        )
        high = adapt_record(
            _support(first_pass_score=100, mice_relevance_score=999),
            source_domain="support",
            today=TODAY,
        )
        score_fields = (
            "urgency_score",
            "business_fit_score",
            "revenue_potential_score",
            "contactability_score",
            "information_completeness_score",
            "deadline_risk_score",
            "unified_priority_score",
        )
        self.assertEqual(
            {key: low[key] for key in score_fields},
            {key: high[key] for key in score_fields},
        )

    def test_unverified_native_p0_is_never_unified_p0(self):
        row = adapt_record(
            _procurement(pre_notice_priority="P0_DETAIL_REVIEW"),
            source_domain="procurement",
            today=TODAY,
        )
        self.assertNotEqual(row["priority_band"], "P0_IMMEDIATE")
        self.assertFalse(row["_strict_p0_gate"])

    def test_strict_verified_bid_can_enter_p0(self):
        row = adapt_record(
            _procurement(
                stage="BID_NOTICE",
                detail_verification_status="VERIFIED",
                eligibility_status="VERIFIED_ELIGIBLE",
                actionability_verified=True,
                attachment_urls=["https://example.com/rfp.pdf"],
                bid_gate_checklist={"qualification": True, "capacity": True},
                blocking_unknowns=[],
                bid_blocking_reasons=[],
                bid_go_no_go="GO",
                bid_participation_readiness="ACTION_NOW",
                public_contact_email="bid@example.com",
                sales_windows=["DIRECT_BID_WINDOW"],
                estimated_amount="200000000",
            ),
            source_domain="procurement",
            today=TODAY,
        )
        self.assertTrue(row["_strict_p0_gate"])
        self.assertEqual(row["priority_band"], "P0_IMMEDIATE")

    def test_duplicate_lifecycle_rows_merge_and_preserve_origins(self):
        bid = adapt_record(
            _procurement(stage="BID_NOTICE", procurement_id="bid-1"),
            source_domain="procurement",
            today=TODAY,
        )
        award = adapt_record(
            _procurement(
                stage="AWARD_RESULT",
                procurement_id="award-1",
                awardee_organizations=["낙찰사"],
                award_date="2026-07-16",
                sales_windows=["AWARD_WINNER_WINDOW"],
            ),
            source_domain="procurement",
            today=TODAY,
        )
        merged, duplicate_count = merge_unified_records([award, bid])
        self.assertEqual(len(merged), 1)
        self.assertEqual(duplicate_count, 1)
        source_ids = merged[0]["source_record_ids"]
        self.assertTrue(any("bid-1" in value for value in source_ids))
        self.assertTrue(any("award-1" in value for value in source_ids))

    def test_each_domain_representative_is_adapted(self):
        cases = [
            ("support", _support(), "SUPPORT_PROGRAM"),
            ("mice", _mice(), "MICE_EVENT"),
            ("procurement", _procurement("PRE_NOTICE"), "PRE_NOTICE"),
            ("procurement", _procurement("BID_NOTICE"), "BID_NOTICE"),
            (
                "procurement",
                _procurement(
                    "AWARD_RESULT",
                    awardee_organizations=["낙찰사"],
                    sales_windows=["AWARD_WINNER_WINDOW"],
                ),
                "AWARD_WINNER_OUTREACH",
            ),
            (
                "procurement",
                _procurement(
                    "CONTRACT_RESULT",
                    sales_windows=["NEXT_CYCLE_WINDOW"],
                    previous_cycle_confidence="STRONG",
                ),
                "CONTRACT_RECURRING",
            ),
        ]
        for source_domain, record, expected in cases:
            with self.subTest(expected=expected):
                row = adapt_record(record, source_domain=source_domain, today=TODAY)
                self.assertEqual(row["domain_type"], expected)
                self.assertTrue(row["source_record_ids"])
                self.assertTrue(row["recommended_next_action"])

    def test_stable_tie_sort_uses_unified_id(self):
        first = adapt_record(_support(1), source_domain="support", today=TODAY)
        second = adapt_record(_support(2), source_domain="support", today=TODAY)
        expected = sorted(
            [first["unified_opportunity_id"], second["unified_opportunity_id"]]
        )
        actual = [
            row["unified_opportunity_id"]
            for row in sorted([second, first], key=unified_sort_key)
        ]
        self.assertEqual(actual, expected)

    def test_runner_limits_top30_excludes_no_action_and_preserves_all(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            support = root / "support.jsonl"
            mice = root / "mice.jsonl"
            procurement = root / "procurement.jsonl"
            write_jsonl(support, [_support(index) for index in range(35)])
            write_jsonl(mice, [_mice(sales_readiness="NONE", event_status="ENDED")])
            write_jsonl(procurement, [_procurement()])
            normalized = root / "normalized"
            reports = root / "reports"

            manifest = run_unified_output(
                run_day=TODAY.isoformat(),
                support_path=support,
                mice_path=mice,
                procurement_paths=[procurement],
                normalized_dir=normalized,
                report_dir=reports,
            )

            with (reports / "unified-opportunity-top30.csv").open(
                encoding="utf-8-sig", newline=""
            ) as fh:
                top = list(csv.DictReader(fh))
            with (reports / "unified-opportunity-all.csv").open(
                encoding="utf-8-sig", newline=""
            ) as fh:
                all_rows = list(csv.DictReader(fh))

            self.assertEqual(len(top), 30)
            self.assertEqual(len(all_rows), 37)
            self.assertNotIn("NO_ACTION", {row["우선순위"] for row in top})
            self.assertEqual(manifest["top_row_count"], 30)
            self.assertEqual(manifest["unified_row_count"], 37)
            self.assertEqual(
                manifest["output_validation"],
                {
                    "jsonl_row_count": 37,
                    "all_csv_data_row_count": 37,
                    "top_csv_data_row_count": 30,
                },
            )
            self.assertFalse(manifest["scoring_policy"]["native_scores_used"])
            self.assertEqual(
                (reports / "unified-opportunity-top30.csv").read_bytes()[:3],
                b"\xef\xbb\xbf",
            )

    def test_empty_input_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = []
            for name in ("support", "mice", "procurement"):
                path = root / f"{name}.jsonl"
                write_jsonl(path, [_support()] if name == "support" else [])
                paths.append(path)
            with self.assertRaisesRegex(UnifiedOutputError, "EMPTY:mice"):
                run_unified_output(
                    run_day=TODAY.isoformat(),
                    support_path=paths[0],
                    mice_path=paths[1],
                    procurement_paths=[paths[2]],
                    normalized_dir=root / "normalized",
                    report_dir=root / "reports",
                )

    def test_failed_rerun_preserves_existing_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            support = root / "support.jsonl"
            mice = root / "mice.jsonl"
            procurement = root / "procurement.jsonl"
            write_jsonl(support, [_support()])
            write_jsonl(mice, [_mice()])
            write_jsonl(procurement, [_procurement()])
            normalized = root / "normalized"
            reports = root / "reports"
            kwargs = {
                "run_day": TODAY.isoformat(),
                "support_path": support,
                "mice_path": mice,
                "procurement_paths": [procurement],
                "normalized_dir": normalized,
                "report_dir": reports,
            }
            first = run_unified_output(**kwargs)
            self.assertEqual(first["unified_row_count"], 3)
            protected = {
                path: path.read_bytes()
                for path in (
                    normalized / "unified-opportunities.jsonl",
                    normalized / "unified-opportunity-manifest.json",
                    reports / "unified-opportunity-top30.csv",
                    reports / "unified-opportunity-all.csv",
                    reports / "unified-opportunity-summary.md",
                )
            }

            with patch(
                "app.run_unified_output._validate_staged_outputs",
                side_effect=UnifiedOutputError("forced staged validation failure"),
            ):
                with self.assertRaisesRegex(
                    UnifiedOutputError, "forced staged validation failure"
                ):
                    run_unified_output(**kwargs)
            for path, before in protected.items():
                self.assertEqual(path.read_bytes(), before)
            self.assertFalse(
                any(
                    path.name.startswith(".unified-output-stage-")
                    for path in root.iterdir()
                )
            )

            write_jsonl(support, [])
            with self.assertRaisesRegex(UnifiedOutputError, "EMPTY:support"):
                run_unified_output(**kwargs)
            for path, before in protected.items():
                self.assertEqual(path.read_bytes(), before)

    def test_missing_input_fails_without_creating_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            support = root / "support.jsonl"
            procurement = root / "procurement.jsonl"
            write_jsonl(support, [_support()])
            write_jsonl(procurement, [_procurement()])
            normalized = root / "normalized"
            reports = root / "reports"

            with self.assertRaisesRegex(UnifiedOutputError, "MISSING:mice"):
                run_unified_output(
                    run_day=TODAY.isoformat(),
                    support_path=support,
                    mice_path=root / "missing-mice.jsonl",
                    procurement_paths=[procurement],
                    normalized_dir=normalized,
                    report_dir=reports,
                )

            self.assertFalse(normalized.exists())
            self.assertFalse(reports.exists())

    @unittest.skipUnless(os.name == "nt", "Windows batch behavior")
    def test_batch_runs_from_wrong_working_directory(self):
        repo_root = Path(__file__).resolve().parents[1]
        batch = repo_root / "scripts" / "run_unified_output.bat"
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as wrong_cwd:
            root = Path(td)
            support = root / "support.jsonl"
            mice = root / "mice.jsonl"
            procurement = root / "procurement.jsonl"
            normalized = root / "normalized"
            reports = root / "reports"
            write_jsonl(support, [_support(index) for index in range(31)])
            write_jsonl(mice, [_mice()])
            write_jsonl(procurement, [_procurement()])

            completed = subprocess.run(
                [
                    "cmd.exe",
                    "/d",
                    "/c",
                    str(batch),
                    "--run-day",
                    TODAY.isoformat(),
                    "--support",
                    str(support),
                    "--mice",
                    str(mice),
                    "--procurement",
                    str(procurement),
                    "--normalized-dir",
                    str(normalized),
                    "--report-dir",
                    str(reports),
                ],
                cwd=wrong_cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            with (reports / "unified-opportunity-top30.csv").open(
                encoding="utf-8-sig", newline=""
            ) as fh:
                self.assertEqual(len(list(csv.DictReader(fh))), 30)
            manifest = json.loads(
                (normalized / "unified-opportunity-manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(manifest["output_validation"]["top_csv_data_row_count"], 30)


if __name__ == "__main__":
    unittest.main()
