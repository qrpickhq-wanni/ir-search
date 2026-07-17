"""Tests for MICE relevance vs procurement preservation."""
from __future__ import annotations

import unittest

from app.procurement_normalizers.mice_relevance import (
    apply_mice_and_sales_fields,
    assess_mice_relevance,
    assess_sales_queue_eligibility,
)
from app.procurement_normalizers.notice_normalizer import normalize_pre_notice
from app.procurement_normalizers.lifecycle_linker import link_lifecycle


def _pre(title: str, no: str = "P1") -> dict:
    return normalize_pre_notice(
        {
            "bfSpecRgstNo": no,
            "prdctClsfcNoNm": title,
            "orderInsttNm": "공공기관",
            "rludInsttNm": "수요기관",
            "rgstDt": "202605010000",
        }
    )


class MiceRelevanceTests(unittest.TestCase):
    def test_general_construction_pre_notice_false(self):
        r = assess_mice_relevance(_pre("대포~컨벤션 도시계획도로(대로2-1-1호선)개설공사 보완설계용역"))
        self.assertFalse(r["mice_relevant"])
        self.assertIn(r["mice_relevance_confidence"], {"NONE", "WEAK"})

    def test_festival_ops_agency_true(self):
        r = assess_mice_relevance(_pre("제11회 실향민문화축제 운영 대행 용역"))
        self.assertTrue(r["mice_relevant"])
        self.assertIn(r["mice_relevance_confidence"], {"STRONG", "MEDIUM"})

    def test_accounting_ops_agency_false(self):
        r = assess_mice_relevance(_pre("글로벌 K-컨벤션 육성 사업 회계검증 및 정산컨설팅 운영 용역"))
        self.assertFalse(r["mice_relevant"])

    def test_legal_exercise_not_event_ops(self):
        r = assess_mice_relevance(
            _pre("디지털성범죄 행위자에 대한 구상권 행사 운영 지침 및 법 개정 방안 연구")
        )
        self.assertFalse(r["mice_relevant"])

    def test_event_ops_service_true(self):
        r = assess_mice_relevance(_pre("2026 국제회의 행사 운영 대행 용역"))
        self.assertTrue(r["mice_relevant"])
        self.assertIn(r["mice_relevance_confidence"], {"STRONG", "MEDIUM"})
        self.assertTrue(r["mice_relevance_evidence"])

    def test_event_system_build_true(self):
        r = assess_mice_relevance(_pre("참가자 등록 및 행사 운영시스템 구축 용역"))
        self.assertTrue(r["mice_relevant"])

    def test_event_word_only_without_task_is_false_or_weak(self):
        r = assess_mice_relevance(_pre("지역 문화 행사 관련 단순 안내 게시판 제작"))
        # Only weak '행사' — no ops task evidence.
        self.assertFalse(r["mice_relevant"])
        self.assertIn(r["mice_relevance_confidence"], {"WEAK", "NONE"})

    def test_mice_false_excluded_from_sales_queue(self):
        base = _pre("학교급식 일부위탁 용역")
        base["sales_priority"] = "P1"
        base["opportunity_routes"] = ["DIRECT_PRIME_BID"]
        base["sales_windows"] = ["DIRECT_BID_WINDOW"]
        base["recommended_next_action"] = "REVIEW"
        out = apply_mice_and_sales_fields(base)
        self.assertFalse(out["mice_relevant"])
        self.assertFalse(out["sales_queue_eligible"])
        self.assertIn("NOT_MICE_RELEVANT", out["sales_queue_exclusion_reasons"])

    def test_procurement_preserved_regardless_of_relevance(self):
        pre = [
            _pre("토목공사 보완설계용역", "A"),
            _pre("국제회의 행사 운영 대행", "B"),
        ]
        linked, stats = link_lifecycle([], [], [], pre_notices=pre)
        self.assertEqual(len(linked), 2)
        self.assertEqual(stats["standalone_pre_notice"], 2)
        scored = [apply_mice_and_sales_fields(r) for r in linked]
        self.assertEqual(len(scored), 2)
        self.assertEqual(sum(1 for r in scored if r["mice_relevant"]), 1)

    def test_required_fields_present(self):
        out = apply_mice_and_sales_fields(_pre("포럼 세션 운영 용역"))
        for key in (
            "mice_relevant",
            "mice_relevance_score",
            "mice_relevance_reasons",
            "mice_relevance_evidence",
            "mice_relevance_confidence",
            "sales_queue_eligible",
            "sales_queue_exclusion_reasons",
        ):
            self.assertIn(key, out)

    def test_sales_queue_requires_path_and_action(self):
        base = _pre("박람회 행사 운영 용역")
        rel = apply_mice_and_sales_fields(base)
        self.assertTrue(rel["mice_relevant"])
        # No routes yet → not eligible
        self.assertFalse(rel["sales_queue_eligible"])
        base2 = dict(rel)
        base2["opportunity_routes"] = ["SUBCONTRACT_OR_SOLUTION_PARTNER"]
        base2["sales_windows"] = ["PRE_NOTICE_PARTNER_OUTREACH"]
        base2["recommended_next_action"] = "PARTNER_OUTREACH"
        base2["sales_priority"] = "P2"
        base2["sales_action_types"] = ["PARTNER_OUTREACH"]
        base2["sales_action_type"] = "PARTNER_OUTREACH"
        q = assess_sales_queue_eligibility(base2)
        self.assertTrue(q["sales_queue_eligible"])


if __name__ == "__main__":
    unittest.main()
