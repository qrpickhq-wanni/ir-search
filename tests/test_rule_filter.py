import unittest
from datetime import date
from pathlib import Path

import yaml

from app.evaluators.rule_filter import apply_first_pass
from app.evaluators.scoring import score_opportunity
from app.io_utils import write_csv_bom
from app.normalizers.base import empty_record, finalize_text_keys, make_opportunity_id


ROOT = Path(__file__).resolve().parents[1]


def load_rules():
    with (ROOT / "config" / "filter-rules.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_profile():
    with (ROOT / "config" / "qrpick-profile.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def make(title, **kwargs):
    r = empty_record()
    sid = kwargs.pop("source_id", "1")
    source = kwargs.pop("source", "kstartup")
    r.update(
        {
            "source": source,
            "source_id": sid,
            "opportunity_id": make_opportunity_id(source, sid),
            "canonical_id": make_opportunity_id(source, sid),
            "title": title,
            "organization": kwargs.pop("organization", "테스트기관"),
            "deadline": kwargs.pop("deadline", "2026-08-30"),
            "program": kwargs.pop("program", None),
            "category": kwargs.pop("category", None),
            "url": "https://example.com/x",
            "raw_file": "t.jsonl",
            "source_occurrences": [
                {"source": source, "source_id": sid, "url": "https://example.com/x", "raw_file": "t.jsonl"}
            ],
        }
    )
    r.update(kwargs)
    return finalize_text_keys(r, today=date(2026, 7, 15))


class TestRuleFilter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = load_rules()
        cls.profile = load_profile()
        cls.today = date(2026, 7, 15)

    def test_bio_word_alone_not_auto_excluded(self):
        rec = make("바이오 스타트업 네트워킹 데이")
        out = apply_first_pass(rec, self.rules, self.profile, today=self.today)
        self.assertIn(out["first_pass_status"], {"LOW_FIT", "DETAIL_REVIEW", "REVIEW", "HIGH_PRIORITY"})
        scored = score_opportunity(rec, self.rules)
        self.assertFalse(scored["penalty_flags"].get("strong_domain_mismatch"))
        # Networking day: industry label alone is not exclusion; queue may be WATCHLIST
        self.assertIn(out["action_queue"], {"WATCHLIST", "SALES_OUTREACH", "NO_ACTION", "QUALIFICATION_CHECK"})
        self.assertIsNotNone(out.get("next_action"))
        # path may be NO_REALISTIC_PATH when no concrete asset family; that is OK
        self.assertIn(out.get("fit_confidence"), {"NONE", "WEAK", "MEDIUM", "STRONG"})

    def test_bio_event_ops_at_least_detail_review(self):
        rec = make("바이오 전시회 참가기업 온라인 등록·체크인 시스템 구축 용역")
        out = apply_first_pass(rec, self.rules, self.profile, today=self.today)
        self.assertIn(out["first_pass_status"], {"DETAIL_REVIEW", "REVIEW", "HIGH_PRIORITY"})
        self.assertIn(
            out["asset_fit_path"],
            {"QRPICK_DIRECT", "CUSTOM_BUILD_SERVICE", "SHOWDA_ASSET_REUSE", "SALES_LEAD", "QRPICK_EXTENSION"},
        )

    def test_asset_fit_path_always_present(self):
        rec = make("일반 지원사업 안내")
        out = apply_first_pass(rec, self.rules, self.profile, today=self.today)
        self.assertIn(out["primary_asset_fit_path"], {
            "QRPICK_DIRECT", "QRPICK_EXTENSION", "SHOWDA_ASSET_REUSE",
            "CUSTOM_BUILD_SERVICE", "PARTNER_CONSORTIUM", "SALES_LEAD", "NO_REALISTIC_PATH",
        })
        self.assertIn(out["action_queue"], {
            "ACTION_NOW", "QUALIFICATION_CHECK", "SALES_OUTREACH", "WATCHLIST", "NO_ACTION", "CLOSED",
        })
        self.assertTrue(out.get("opportunity_type"))
        self.assertTrue(out.get("recommended_next_action"))

    def test_showda_requires_family(self):
        rec = make("AI 플랫폼 데이터 디지털 혁신 지원")
        out = apply_first_pass(rec, self.rules, self.profile, today=self.today)
        self.assertNotEqual(out.get("primary_asset_fit_path"), "SHOWDA_ASSET_REUSE")

    def test_exhibition_sales_outreach(self):
        rec = make("국제 컨퍼런스 전시부스 참가기업 모집")
        out = apply_first_pass(rec, self.rules, self.profile, today=self.today)
        self.assertEqual(out["action_queue"], "SALES_OUTREACH")
        self.assertIn(out["opportunity_type"], {"EXHIBITION_OR_MARKET_ACCESS", "SALES_SIGNAL"})

    def test_trainee_no_action(self):
        rec = make("AI 부트캠프 교육생 모집 안내", category="창업교육")
        out = apply_first_pass(rec, self.rules, self.profile, today=self.today)
        self.assertEqual(out["action_queue"], "NO_ACTION")

    def test_build_custom_service(self):
        rec = make("수출상담회 참가자 등록·매칭 시스템 구축 용역")
        out = apply_first_pass(rec, self.rules, self.profile, today=self.today)
        self.assertIn(out["primary_asset_fit_path"], {"QRPICK_DIRECT", "CUSTOM_BUILD_SERVICE"})
        # List-only stage: never ACTION_NOW
        self.assertEqual(out["action_queue"], "QUALIFICATION_CHECK")
        self.assertEqual(out["detail_verification_status"], "NOT_FETCHED")
        self.assertFalse(out["actionability_verified"])

    def test_not_fetched_cannot_be_action_now(self):
        titles = [
            "비즈니스 매칭 상담회 참여 기업 모집",
            "관광·마이스 그로우업 지원사업",
            "크루즈 관광객 유치 인센티브",
            "기술플랫폼 구축사업",
            "IR 고도화 및 투자상담회",
        ]
        for title in titles:
            out = apply_first_pass(make(title), self.rules, self.profile, today=self.today)
            self.assertNotEqual(out["action_queue"], "ACTION_NOW", msg=title)
            self.assertEqual(out["detail_verification_status"], "NOT_FETCHED")

    def test_verified_can_promote_action_now(self):
        rec = make("수출상담회 참가자 등록·매칭 시스템 구축 용역")
        rec["detail_verification_status"] = "VERIFIED"
        rec["action_promotion_source"] = "DETAIL_REVIEW"
        rec["actionability_verified"] = True
        out = apply_first_pass(rec, self.rules, self.profile, today=self.today)
        self.assertEqual(out["action_queue"], "ACTION_NOW")
        self.assertTrue(out["actionability_verified"])
        self.assertEqual(out["action_promotion_source"], "DETAIL_REVIEW")
        self.assertTrue(out.get("actionability_gate_reasons"))

    def test_manual_promotion(self):
        rec = make("임의 공고 제목 플랫폼 매칭")
        rec["action_promotion_source"] = "MANUAL"
        rec["actionability_verified"] = True
        rec["actionability_gate_reasons"] = ["운영자 수동 승인"]
        out = apply_first_pass(rec, self.rules, self.profile, today=self.today)
        self.assertEqual(out["action_queue"], "ACTION_NOW")
        self.assertEqual(out["action_promotion_source"], "MANUAL")

    def test_trainee_penalty(self):
        rec = make("AI 부트캠프 교육생 모집 안내", category="창업교육")
        scored = score_opportunity(rec, self.rules)
        self.assertTrue(scored["penalty_flags"].get("trainee_individual"))
        self.assertLess(scored["score"], 30)

    def test_tourism_mice_demo_boost(self):
        rec = make("부산 관광·마이스 그로우업 지원사업 실증 PoC")
        scored = score_opportunity(rec, self.rules)
        self.assertGreaterEqual(scored["score"], 50)
        self.assertTrue({"tourism_extension", "program_value"} & set(scored["matched_groups"]))

    def test_expired(self):
        rec = make("지난 공고", deadline="2026-07-01")
        out = apply_first_pass(rec, self.rules, self.profile, today=self.today)
        self.assertEqual(out["first_pass_status"], "EXPIRED")

    def test_unknown_deadline_detail_or_unknown(self):
        rec = make("오픈이노베이션 과제 공모", deadline=None)
        out = apply_first_pass(rec, self.rules, self.profile, today=self.today)
        self.assertIn(out["first_pass_status"], {"DETAIL_REVIEW", "UNKNOWN", "REVIEW", "HIGH_PRIORITY"})
        self.assertEqual(out["action_queue"], "QUALIFICATION_CHECK")

    def test_csv_utf8_bom(self):
        import tempfile

        rec = make("한글 공고 테스트")
        scored = apply_first_pass(rec, self.rules, self.profile, today=self.today)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.csv"
            write_csv_bom(path, [scored])
            raw = path.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            text = path.read_text(encoding="utf-8-sig")
            self.assertIn("한글 공고 테스트", text)


if __name__ == "__main__":
    unittest.main()
