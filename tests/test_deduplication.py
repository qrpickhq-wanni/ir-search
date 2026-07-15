import unittest
from datetime import date

from app.normalizers.base import empty_record, finalize_text_keys, make_opportunity_id
from app.normalizers.deduplicate import deduplicate


def _rec(source, sid, title, org, deadline, url=None):
    r = empty_record()
    r.update(
        {
            "source": source,
            "source_id": sid,
            "opportunity_id": make_opportunity_id(source, sid),
            "canonical_id": make_opportunity_id(source, sid),
            "title": title,
            "organization": org,
            "deadline": deadline,
            "url": url or f"https://example.com/{source}/{sid}",
            "raw_file": "test.jsonl",
            "source_occurrences": [
                {"source": source, "source_id": sid, "url": url or f"https://example.com/{source}/{sid}", "raw_file": "test.jsonl"}
            ],
        }
    )
    return finalize_text_keys(r, today=date(2026, 7, 15))


class TestDeduplication(unittest.TestCase):
    def test_different_year_region_not_merged(self):
        a = _rec("kstartup", "1", "2025 서울 관광 SaaS 실증", "관광공사", "2025-08-01")
        b = _rec("kstartup", "2", "2026 부산 관광 SaaS 실증", "관광공사", "2026-08-01")
        reps, logs = deduplicate([a, b])
        self.assertEqual(len(reps), 2)
        auto = [x for x in logs if x.get("type") == "auto_merged"]
        self.assertEqual(len(auto), 0)

    def test_same_title_org_deadline_merged(self):
        a = _rec("kstartup", "10", "동일 공고 제목 지원사업", "쇼다재단", "2026-08-01")
        b = _rec("bizinfo", "X1", "동일 공고 제목 지원사업", "쇼다재단", "2026-08-01")
        reps, logs = deduplicate([a, b])
        self.assertEqual(len(reps), 1)
        self.assertEqual(reps[0]["duplicate_count"], 2)
        auto = [x for x in logs if x.get("type") == "auto_merged"]
        self.assertEqual(len(auto), 1)

    def test_same_source_id_merged(self):
        a = _rec("nipa", "100", "제목A", "NIPA", "2026-08-01")
        b = _rec("nipa", "100", "제목A 수정", "NIPA", "2026-08-01")
        reps, logs = deduplicate([a, b])
        self.assertEqual(len(reps), 1)

    def test_different_org_and_deadline_not_merged(self):
        a = _rec("kstartup", "1", "동일 제목", "기관A", "2026-08-01")
        b = _rec("bizinfo", "2", "동일 제목", "기관B", "2026-09-01")
        reps, _ = deduplicate([a, b])
        self.assertEqual(len(reps), 2)


if __name__ == "__main__":
    unittest.main()
