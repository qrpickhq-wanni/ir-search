"""Lifecycle linking and revision handling tests."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.io_utils import write_mapped_csv_bom
from app.procurement_collectors.openapi_status import (
    FILTERED_ALL,
    OK_EMPTY,
    OK_TRUNCATED,
    PARSING_ERROR,
    finalize_collect_status,
)
from app.procurement_normalizers.lifecycle_linker import link_lifecycle
from app.procurement_normalizers.notice_normalizer import (
    normalize_award_result,
    normalize_bid_notice,
    normalize_contract_result,
    normalize_pre_notice,
)
from app.run_g2b_summary import ROUTE_COLUMNS


def _notice(no: str, rev: str, title: str) -> dict:
    return normalize_bid_notice(
        {
            "bidNtceNo": no,
            "bidNtceOrd": rev,
            "bidNtceNm": title,
            "ntceInsttNm": "한국관광공사",
            "dminsttNm": "한국관광공사",
            "bidNtceDate": "202605010000",
            "bidClseDate": "202605200000",
            "bidNtceDtlUrl": "https://www.g2b.go.kr/notice/" + no,
        }
    )


def _award(no: str, name: str) -> dict:
    return normalize_award_result(
        {
            "bidNtceNo": no,
            "bidNtceOrd": "00",
            "bidNtceNm": "국제포럼 운영 대행 용역",
            "bidwinnrNm": name,
            "sucsfbidAmt": "100000000",
            "opengDate": "202605250000",
            "fnlSucsfDate": "202605250000",
        }
    )


def _contract(no: str, amt: str) -> dict:
    return normalize_contract_result(
        {
            "untyCntrctNo": "C-" + no,
            "bidNtceNo": no,
            "cntrctNm": "국제포럼 운영 대행 용역",
            "totCntrctAmt": amt,
            "cntrctCnclsDate": "202606010000",
            "corpNm": "낙찰사A",
        }
    )


def _pre(no: str, title: str) -> dict:
    return normalize_pre_notice(
        {
            "bfSpecRgstNo": no,
            "prdctClsfcNoNm": title,
            "orderInsttNm": "한국관광공사",
            "rludInsttNm": "한국관광공사",
            "rgstDt": "202605010000",
        }
    )


class LifecycleTests(unittest.TestCase):
    def test_notice_award_contract_link(self):
        notices = [_notice("2026N001", "00", "국제포럼 운영 대행 용역 입찰")]
        awards = [_award("2026N001", "낙찰사A")]
        contracts = [_contract("2026N001", "120000000")]
        linked, stats = link_lifecycle(notices, awards, contracts)
        self.assertEqual(len(linked), 1)
        self.assertEqual(stats["notice_to_award_links"], 1)
        self.assertEqual(stats["award_to_contract_links"], 1)
        self.assertEqual(linked[0]["awardee_organizations"], ["낙찰사A"])
        self.assertEqual(linked[0]["contract_amount"], "120000000")
        self.assertIn("notice_number:2026N001", linked[0]["lifecycle_link_basis"])

    def test_change_notice_not_duplicated(self):
        notices = [
            _notice("2026N002", "00", "전시 등록시스템 구축 용역"),
            _notice("2026N002", "01", "전시 등록시스템 구축 용역(변경)"),
        ]
        linked, stats = link_lifecycle(notices, [], [])
        self.assertEqual(len(linked), 1)
        self.assertEqual(stats["change_revision_groups"], 1)
        self.assertEqual(linked[0]["notice_revision"], "01")

    def test_pre_notice_alone_preserved_as_procurement(self):
        pre = [_pre("P2026001", "국제회의 운영 대행 용역 사전규격")]
        linked, stats = link_lifecycle([], [], [], pre_notices=pre)
        self.assertEqual(len(linked), 1)
        self.assertEqual(linked[0]["procurement_stage"], "PRE_NOTICE")
        self.assertTrue(str(linked[0]["lifecycle_group_id"]).startswith("g2b:prelg:"))
        self.assertEqual(stats["standalone_pre_notice"], 1)

    def test_normalized_rows_never_force_zero_procurements(self):
        pre = [_pre(f"P{i}", f"행사 운영 {i}") for i in range(5)]
        linked, _ = link_lifecycle([], [], [], pre_notices=pre)
        self.assertEqual(len(linked), 5)

    def test_bid_award_contract_standalone_preserved(self):
        notices = [_notice("B1", "00", "단독 입찰")]
        awards = [_award("A1", "낙찰사")]
        contracts = [
            normalize_contract_result(
                {
                    "untyCntrctNo": "C-ORPHAN",
                    "cntrctNm": "단독 계약",
                    "totCntrctAmt": "1",
                    "cntrctCnclsDate": "202606010000",
                    "corpNm": "업체",
                }
            )
        ]
        linked, stats = link_lifecycle(notices, awards, contracts)
        stages = {r.get("procurement_stage") for r in linked}
        self.assertIn("BID_NOTICE", stages)
        self.assertIn("AWARD_RESULT", stages)
        self.assertTrue(any(r.get("lifecycle_link_basis") == ["orphan_contract"] for r in linked))
        self.assertGreaterEqual(stats["standalone_bid_notice"], 1)
        self.assertGreaterEqual(stats["standalone_award"], 1)
        self.assertGreaterEqual(stats["standalone_contract"], 1)

    def test_linkable_stages_merge_into_one_group(self):
        notices = [_notice("M1", "00", "통합")]
        awards = [_award("M1", "낙찰")]
        contracts = [_contract("M1", "10")]
        pre = [_pre("P-OTHER", "별도 사전규격")]
        linked, _ = link_lifecycle(notices, awards, contracts, pre_notices=pre)
        self.assertEqual(len(linked), 2)  # merged lifecycle + standalone pre
        merged = [r for r in linked if r.get("notice_number") == "M1"][0]
        self.assertEqual(merged["procurement_stage"], "CONTRACT_RESULT")

    def test_utf8_bom_header_when_empty_consortium(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "g2b-consortium-opportunities.csv"
            write_mapped_csv_bom(p, ROUTE_COLUMNS, [])
            self.assertTrue(p.read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertEqual(len(p.read_text(encoding="utf-8-sig").strip().splitlines()), 1)


class CollectStatusTests(unittest.TestCase):
    def test_total_count_positive_parsed_zero_not_ok_empty(self):
        st = finalize_collect_status(
            record_count=0,
            page_statuses=[None],
            total_count_reported=12,
            raw_item_count=0,
        )
        self.assertEqual(st, PARSING_ERROR)
        self.assertNotEqual(st, OK_EMPTY)

    def test_mice_filter_all_status(self):
        st = finalize_collect_status(
            record_count=0,
            page_statuses=[None],
            total_count_reported=12,
            raw_item_count=12,
        )
        self.assertEqual(st, FILTERED_ALL)

    def test_limit_reached_ok_truncated(self):
        st = finalize_collect_status(
            record_count=500,
            page_statuses=[None],
            limit_reached=True,
        )
        self.assertEqual(st, OK_TRUNCATED)

    def test_true_empty_is_ok_empty(self):
        st = finalize_collect_status(
            record_count=0,
            page_statuses=[None],
            total_count_reported=0,
            raw_item_count=0,
        )
        self.assertEqual(st, OK_EMPTY)


if __name__ == "__main__":
    unittest.main()
