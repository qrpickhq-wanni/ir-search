"""Lifecycle linking and revision handling tests."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.io_utils import write_mapped_csv_bom
from app.procurement_normalizers.lifecycle_linker import link_lifecycle
from app.procurement_normalizers.notice_normalizer import (
    normalize_award_result,
    normalize_bid_notice,
    normalize_contract_result,
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

    def test_utf8_bom_header_when_empty_consortium(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "g2b-consortium-opportunities.csv"
            write_mapped_csv_bom(p, ROUTE_COLUMNS, [])
            self.assertTrue(p.read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertEqual(len(p.read_text(encoding="utf-8-sig").strip().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
