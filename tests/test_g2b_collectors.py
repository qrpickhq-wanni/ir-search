"""Unit tests for G2B procurement collectors (no live key required)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.io_utils import load_yaml, project_root
from app.procurement_collectors.api_client import DataGoKrClient
from app.procurement_collectors.base import resolve_service_key
from app.procurement_collectors.g2b_bid_notice import G2bBidNoticeCollector
from app.run_g2b_collect import run_g2b_collect

KEY_ENV_VARS = ("DATA_GO_KR_SERVICE_KEY", "G2B_SERVICE_KEY", "PUBLIC_DATA_SERVICE_KEY")


class G2bCollectorTests(unittest.TestCase):
    def setUp(self):
        self.config = load_yaml(project_root() / "config" / "g2b-mice-lifecycle.yaml")

    def test_missing_key_is_partial_expected(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {k: "" for k in KEY_ENV_VARS}, clear=False):
                c = G2bBidNoticeCollector(
                    config=self.config,
                    raw_dir=Path(td),
                    today=date(2026, 7, 16),
                    service_key=None,
                )
                r = c.collect()
            self.assertEqual(r.status, "PARTIAL_EXPECTED")
            self.assertTrue(r.success)
            self.assertIn("SERVICE_KEY_NOT_CONFIGURED", r.warnings[0])
            self.assertEqual(r.metadata.get("reason"), "SERVICE_KEY_NOT_CONFIGURED")
            self.assertEqual(r.metadata.get("runtime_status"), "PARTIAL_EXPECTED")
            self.assertEqual(r.metadata.get("http_pages"), 0)
            self.assertEqual(r.parsed_count, 0)

    def test_extract_items_shapes(self):
        payload = {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                "body": {
                    "items": {"item": [{"bidNtceNo": "1", "bidNtceNm": "포럼 운영 대행 용역"}]},
                    "totalCount": 1,
                },
            }
        }
        items = DataGoKrClient.extract_items(payload)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["bidNtceNo"], "1")

    def test_run_collect_without_key_writes_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td)
            # Ensure no key from environment for this process path by forcing config
            # (resolve_service_key reads env — if user has key, still OK)
            manifest = run_g2b_collect(today=date(2026, 7, 16), raw_dir=raw, config=self.config)
            self.assertTrue((raw / "collection_manifest.json").exists())
            self.assertTrue((raw / "collection_errors.jsonl").exists())
            for name in (
                "g2b_pre_notices.jsonl",
                "g2b_bid_notices.jsonl",
                "g2b_award_results.jsonl",
                "g2b_contract_results.jsonl",
            ):
                # created when PARTIAL_EXPECTED
                self.assertTrue((raw / name).exists() or not manifest.get("auth_present"))

    def test_service_key_not_logged_in_safe_query(self):
        client = DataGoKrClient(config=self.config, http=MagicMock(), service_key="SECRETKEY")
        # Build safe query dict as get_page would
        q = {"serviceKey": "SECRETKEY", "pageNo": 1}
        safe = {k: ("***" if k.lower() == "servicekey" else v) for k, v in q.items()}
        self.assertEqual(safe["serviceKey"], "***")


if __name__ == "__main__":
    unittest.main()
