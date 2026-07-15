import unittest
from datetime import date

from app.normalizers.text_utils import normalize_organization, normalize_title


class TestTextNormalization(unittest.TestCase):
    def test_korean_whitespace_and_parens(self):
        a = normalize_title("  2026  부산  관광·마이스  그로우업  지원사업（공고） ")
        b = normalize_title("2026 부산 관광 마이스 그로우업 지원사업")
        self.assertEqual(a, b)

    def test_quote_variants(self):
        a = normalize_title("“오픈이노베이션” 모집 공고")
        b = normalize_title("오픈이노베이션 모집공고")
        self.assertEqual(a, b)

    def test_original_title_untouched_concept(self):
        original = "  공고 제목  "
        # normalize_title returns a key; callers must keep original separately
        self.assertNotEqual(normalize_title(original), original)

    def test_org_prefix_suffix(self):
        a = normalize_organization("(재)여성기업종합지원센터 전북센터")
        b = normalize_organization("여성기업종합지원센터 전북센터")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
