"""Runtime status + exit-code policy tests."""
from __future__ import annotations

import os
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.mice_collectors.base import CollectResult
from app.mice_collectors.kintex import KintexCollector
from app.mice_collectors.mice_or_kr import MiceOrKrCollector
from app.mice_collectors.mice_seoul_cvb import MiceSeoulCvbCollector
from app.mice_collectors.opendata_kintex_gg import OpendataKintexGgCollector
from app.mice_collectors.runtime_status import (
    HOLD_CONFIGURED,
    OK,
    OK_EMPTY,
    PARTIAL_EXPECTED,
    PARTIAL_UNEXPECTED,
    compute_collect_exit_code,
    compute_mvp_exit_code,
    enrich_collect_result,
    status_is_expected,
)
from app.run_mice_collect import run_collect


class RuntimeStatusUnitTests(unittest.TestCase):
    def test_ok_empty_is_expected_when_board_empty(self):
        self.assertTrue(status_is_expected(OK_EMPTY, OK_EMPTY))
        self.assertTrue(status_is_expected(OK, OK_EMPTY))  # improvement

    def test_partial_expected_only_exit_0(self):
        rows = [
            {"source_id": "a", "status": OK, "fetched_count": 10, "metadata": {"runtime_enabled": True}},
            {
                "source_id": "b",
                "status": PARTIAL_EXPECTED,
                "fetched_count": 0,
                "metadata": {"runtime_enabled": True, "failure_affects_exit_code": True},
            },
            {
                "source_id": "c",
                "status": HOLD_CONFIGURED,
                "fetched_count": 0,
                "metadata": {"runtime_enabled": False, "failure_affects_exit_code": False},
            },
            {
                "source_id": "d",
                "status": OK_EMPTY,
                "fetched_count": 0,
                "metadata": {"runtime_enabled": True},
            },
        ]
        self.assertEqual(compute_collect_exit_code(rows), 0)

    def test_unexpected_partial_exit_2(self):
        rows = [
            {"source_id": "a", "status": OK, "fetched_count": 5, "metadata": {}},
            {"source_id": "b", "status": PARTIAL_UNEXPECTED, "fetched_count": 1, "metadata": {}},
        ]
        self.assertEqual(compute_collect_exit_code(rows), 2)

    def test_pipeline_failure_exit_1(self):
        self.assertEqual(
            compute_mvp_exit_code(
                source_rows=[{"status": OK, "metadata": {}}],
                integrity_ok=True,
                test_rc=0,
                pipeline_ok=False,
            ),
            1,
        )
        self.assertEqual(
            compute_mvp_exit_code(
                source_rows=[{"status": OK, "metadata": {}}],
                integrity_ok=False,
                test_rc=0,
                pipeline_ok=True,
            ),
            1,
        )
        self.assertEqual(
            compute_mvp_exit_code(
                source_rows=[{"status": OK, "metadata": {}}],
                integrity_ok=True,
                test_rc=1,
                pipeline_ok=True,
            ),
            1,
        )


class MiceOrEmptyWindowTests(unittest.TestCase):
    def test_zero_in_window_is_ok_empty(self):
        with TemporaryDirectory() as tmp:
            raw = Path(tmp)
            c = MiceOrKrCollector(
                registry_entry={
                    "source_id": "mice_or_kr",
                    "list_urls": ["https://www.mice.or.kr/bbs/board.php?bo_table=event"],
                    "expected_runtime_status": OK_EMPTY,
                },
                policy={
                    "date_window": {"past_days": 60, "future_days": 550},
                    "limits": {
                        "max_records_per_source": 5,
                        "max_requests_per_source": 5,
                        "max_pages_per_source": 2,
                    },
                    "http": {
                        "request_delay_seconds": 0.01,
                        "request_timeout_seconds": 5,
                        "max_retries": 0,
                        "retry_backoff_seconds": 0.01,
                    },
                },
                raw_dir=raw,
                today=date(2026, 7, 16),
            )
            # Simulate: list pages fetched, zero rows kept
            result = CollectResult(
                source_id="mice_or_kr",
                success=True,
                status=OK_EMPTY,
                fetched_count=0,
                warnings=["OK_EMPTY: none in window"],
            )
            enrich_collect_result(result, c.registry_entry)
            self.assertEqual(result.status, OK_EMPTY)
            self.assertTrue(result.metadata["status_is_expected"])


class HoldConfiguredNoHttpTests(unittest.TestCase):
    def test_hold_configured_skips_http(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "mice-collection-policy.yaml").write_text(
                "policy_version: '1.1'\ncollector_version: '1.1.0'\n"
                "date_window: {past_days: 60, future_days: 550}\n"
                "limits: {max_records_per_source: 5, max_requests_per_source: 5, max_pages_per_source: 1}\n"
                "http: {request_delay_seconds: 0.01, request_timeout_seconds: 5, max_retries: 0, retry_backoff_seconds: 0.01}\n"
                "sources: {}\n",
                encoding="utf-8",
            )
            (root / "config" / "mice-source-registry.yaml").write_text(
                "sources:\n"
                "- source_id: mice_seoul_cvb\n"
                "  runtime_enabled: false\n"
                "  expected_runtime_status: HOLD_CONFIGURED\n"
                "  failure_affects_exit_code: false\n"
                "  runtime_notes: no http\n"
                "  list_urls: [https://example.invalid/hold]\n"
                "- source_id: kintex\n"
                "  runtime_enabled: true\n"
                "  expected_runtime_status: PARTIAL_EXPECTED\n"
                "  failure_affects_exit_code: true\n"
                "  list_urls: [https://example.invalid/kintex]\n",
                encoding="utf-8",
            )
            (root / "data" / "raw" / "mice").mkdir(parents=True)

            called = {"seoul": 0, "kintex": 0}

            def seoul_collect(self):
                called["seoul"] += 1
                return CollectResult(source_id="mice_seoul_cvb", success=True, status=HOLD_CONFIGURED)

            def kintex_collect(self):
                called["kintex"] += 1
                return CollectResult(
                    source_id="kintex",
                    success=True,
                    status=PARTIAL_EXPECTED,
                    fetched_count=2,
                )

            with patch.object(MiceSeoulCvbCollector, "collect", seoul_collect), patch.object(
                KintexCollector, "collect", kintex_collect
            ):
                manifest = run_collect(
                    sources=["mice_seoul_cvb", "kintex"],
                    today=date(2026, 7, 16),
                    root=root,
                )

            statuses = {s["source_id"]: s["status"] for s in manifest["sources"]}
            self.assertEqual(statuses["mice_seoul_cvb"], HOLD_CONFIGURED)
            self.assertEqual(statuses["kintex"], PARTIAL_EXPECTED)
            # HOLD short-circuit must not invoke collector.collect
            self.assertEqual(called["seoul"], 0)
            self.assertEqual(called["kintex"], 1)
            self.assertEqual(called["kintex"], 1)
            self.assertEqual(manifest["exit_code_policy"]["collect_exit_code"], 0)
            seoul = next(s for s in manifest["sources"] if s["source_id"] == "mice_seoul_cvb")
            self.assertEqual(seoul.get("request_count"), 0)


class OpendataKeyExpectedTests(unittest.TestCase):
    def test_missing_keys_partial_expected(self):
        with TemporaryDirectory() as tmp:
            raw = Path(tmp)
            env = {k: v for k, v in os.environ.items() if k not in {"GG_OPENAPI_KEY", "GG_KINTEX_OPENAPI_SERVICE"}}
            c = OpendataKintexGgCollector(
                registry_entry={
                    "source_id": "opendata_kintex_gg",
                    "list_urls": [
                        "https://www.data.go.kr/data/15119881/fileData.do",
                        "https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=TM03IWAWFH17G6VM827729982969&infSeq=1",
                    ],
                    "expected_runtime_status": PARTIAL_EXPECTED,
                },
                policy={
                    "limits": {
                        "max_records_per_source": 5,
                        "max_requests_per_source": 8,
                        "max_pages_per_source": 1,
                    },
                    "http": {
                        "request_delay_seconds": 0.01,
                        "request_timeout_seconds": 8,
                        "max_retries": 0,
                        "retry_backoff_seconds": 0.01,
                    },
                },
                raw_dir=raw,
                today=date(2026, 7, 16),
            )
            with patch.dict(os.environ, env, clear=True):
                # Avoid live network: stub collect outcome for key-unset branch logic via direct status
                result = CollectResult(
                    source_id="opendata_kintex_gg",
                    success=True,
                    status=PARTIAL_EXPECTED,
                    fetched_count=0,
                    warnings=["PARTIAL_EXPECTED: keys unset"],
                )
                enrich_collect_result(result, c.registry_entry)
            self.assertEqual(result.status, PARTIAL_EXPECTED)
            self.assertTrue(result.metadata["status_is_expected"])


class ExitCodeIntegrationTests(unittest.TestCase):
    def test_collect_exit_code_with_only_expected(self):
        rows = [
            {"status": OK, "fetched_count": 100, "metadata": {"runtime_enabled": True}},
            {"status": PARTIAL_EXPECTED, "fetched_count": 0, "metadata": {"runtime_enabled": True}},
            {"status": OK_EMPTY, "fetched_count": 0, "metadata": {"runtime_enabled": True}},
            {
                "status": HOLD_CONFIGURED,
                "fetched_count": 0,
                "metadata": {"runtime_enabled": False, "failure_affects_exit_code": False},
            },
        ]
        self.assertEqual(compute_collect_exit_code(rows), 0)
        self.assertEqual(
            compute_mvp_exit_code(source_rows=rows, integrity_ok=True, test_rc=0, pipeline_ok=True),
            0,
        )


if __name__ == "__main__":
    unittest.main()
