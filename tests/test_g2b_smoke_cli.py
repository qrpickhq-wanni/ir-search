"""Smoke-test CLI and OpenAPI status classification tests."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.io_utils import load_yaml, project_root, read_jsonl, write_jsonl
from app.procurement_collectors.api_client import DataGoKrClient, _as_item_list
from app.procurement_collectors.base import ProcurementCollectResult
from app.procurement_collectors.openapi_status import (
    ACCESS_DENIED,
    ENDPOINT_NOT_FOUND,
    HTTP_4XX,
    HTTP_5XX,
    HTTP_ERROR,
    INVALID_PARAMETER,
    OK_EMPTY,
    PARSING_ERROR,
    RATE_LIMITED,
    SERVICE_KEY_ENCODING_ERROR,
    SERVICE_KEY_INVALID,
    SERVICE_NOT_APPROVED,
    classify_http_status,
    classify_result_code_msg,
    finalize_collect_status,
    mask_service_key_in_text,
    mask_service_key_in_url,
    parse_xml_error_payload,
    sanitize_service_key,
)
from app.run_g2b_collect import parse_sources, run_g2b_collect
from app.run_g2b_mice_mvp import run_g2b_mice_mvp
from app.run_g2b_mice_mvp import main as mvp_main

KEY_ENV_VARS = ("DATA_GO_KR_SERVICE_KEY", "G2B_SERVICE_KEY", "PUBLIC_DATA_SERVICE_KEY")


@contextmanager
def no_network_patches():
    """Block env keys, HTTP client construction, and sleeps in unit tests."""
    with (
        patch.dict("os.environ", {k: "" for k in KEY_ENV_VARS}, clear=False),
        patch("app.procurement_collectors.base.resolve_service_key", return_value=None),
        patch("app.run_g2b_collect.resolve_service_key", return_value=None),
        patch("app.mice_collectors.http_client.PoliteHttpClient") as http_cls,
        patch("time.sleep"),
    ):
        http_cls.return_value.request_log = []
        yield http_cls


class OpenApiStatusTests(unittest.TestCase):
    def test_mask_service_key(self):
        url = "https://apis.data.go.kr/x?serviceKey=SECRET123&pageNo=1"
        masked = mask_service_key_in_url(url, "SECRET123")
        self.assertNotIn("SECRET123", masked)
        self.assertIn("serviceKey=***REDACTED***", masked)
        self.assertNotIn("SECRET123", mask_service_key_in_text("key=SECRET123", "SECRET123"))

    def test_sanitize_rejects_non_ascii_key(self):
        key, meta = sanitize_service_key("  abc한글123  ")
        self.assertEqual(meta["shape_error"], "NON_ASCII")
        self.assertFalse(meta["is_ascii"])
        self.assertTrue(meta["has_leading_or_trailing_whitespace"])
        self.assertIsNotNone(key)

    def test_http_status_taxonomy(self):
        self.assertEqual(classify_http_status(401), ACCESS_DENIED)
        self.assertEqual(classify_http_status(403), ACCESS_DENIED)
        self.assertEqual(classify_http_status(404), ENDPOINT_NOT_FOUND)
        self.assertEqual(classify_http_status(429), RATE_LIMITED)
        self.assertEqual(classify_http_status(418), HTTP_4XX)
        self.assertEqual(classify_http_status(503), HTTP_5XX)
        self.assertEqual(classify_result_code_msg(None, "Unauthorized", http_status=401), ACCESS_DENIED)
        self.assertEqual(classify_result_code_msg(None, None, http_status=500), HTTP_5XX)

    def test_single_item_object_and_array(self):
        single = {"items": {"item": {"bidNtceNo": "1", "bidNtceNm": "포럼 용역"}}}
        arr = {"items": {"item": [{"bidNtceNo": "1"}, {"bidNtceNo": "2"}]}}
        self.assertEqual(len(_as_item_list(single)), 1)
        self.assertEqual(len(_as_item_list(arr)), 2)
        payload = {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                "body": single,
            }
        }
        self.assertEqual(len(DataGoKrClient.extract_items(payload)), 1)

    def test_xml_error_response(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <OpenAPI_ServiceResponse>
          <cmmMsgHeader>
            <errMsg>SERVICE ERROR</errMsg>
            <returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>
            <returnReasonCode>30</returnReasonCode>
          </cmmMsgHeader>
        </OpenAPI_ServiceResponse>
        """
        parsed = parse_xml_error_payload(xml)
        self.assertTrue(parsed["is_xml_error"])
        self.assertEqual(parsed["result_code"], "30")
        status = classify_result_code_msg(parsed["result_code"], parsed["result_msg"])
        self.assertEqual(status, SERVICE_NOT_APPROVED)

    def test_auth_errors_not_ok_empty(self):
        self.assertEqual(
            classify_result_code_msg("30", "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"),
            SERVICE_NOT_APPROVED,
        )
        self.assertEqual(
            classify_result_code_msg("99", "INVALID SERVICE KEY"),
            SERVICE_KEY_INVALID,
        )
        self.assertEqual(
            classify_result_code_msg("99", "URL DECODER SERVICE ERROR"),
            SERVICE_KEY_ENCODING_ERROR,
        )
        self.assertEqual(
            classify_result_code_msg("10", "INVALID REQUEST PARAMETER ERROR"),
            INVALID_PARAMETER,
        )
        self.assertEqual(finalize_collect_status(record_count=0, page_statuses=[], hard_error=None), OK_EMPTY)
        self.assertNotEqual(
            finalize_collect_status(
                record_count=0, page_statuses=[SERVICE_NOT_APPROVED], hard_error=SERVICE_NOT_APPROVED
            ),
            OK_EMPTY,
        )
        self.assertEqual(
            finalize_collect_status(
                record_count=0, page_statuses=[SERVICE_NOT_APPROVED], hard_error=SERVICE_NOT_APPROVED
            ),
            SERVICE_NOT_APPROVED,
        )

    def test_http_and_parsing_errors(self):
        self.assertEqual(classify_result_code_msg(None, None, http_status=500), HTTP_5XX)
        client = DataGoKrClient(config={}, http=MagicMock(), service_key="K")
        http = MagicMock()
        http.get.side_effect = RuntimeError("boom")
        http.request_log = []
        client.http = http
        page = client.get_page(service_path="/x", operation="op", params={"pageNo": 1, "numOfRows": 10})
        self.assertEqual(page["error_status"], HTTP_ERROR)
        self.assertEqual(page["safe_query"]["serviceKey"], "***REDACTED***")
        self.assertNotIn("serviceKey=K", str(page))

    def test_non_ascii_key_rejected_before_http(self):
        http = MagicMock()
        client = DataGoKrClient(config={}, http=http, service_key="12한글34")
        page = client.get_page(service_path="/x", operation="op", params={"pageNo": 1, "numOfRows": 5})
        self.assertEqual(page["error_status"], SERVICE_KEY_INVALID)
        http.get.assert_not_called()

    def test_encoding_key_passed_via_url_not_params(self):
        http = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.text = json.dumps(
            {
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                    "body": {"items": {"item": []}, "totalCount": 0},
                }
            }
        )
        resp.url = "https://apis.data.go.kr/x?serviceKey=ab%2Fcd&type=json&pageNo=1&numOfRows=5"
        resp.content_type = "application/json"
        resp.headers = {"content-type": "application/json"}
        resp.attempt = 1
        http.get.return_value = resp
        http.request_log = []
        client = DataGoKrClient(config={}, http=http, service_key="ab%2Fcd")
        page = client.get_page(service_path="/x", operation="op", params={"pageNo": 1, "numOfRows": 5})
        self.assertIsNone(page["error_status"])
        self.assertEqual(page["passed_via"], "url")
        args, kwargs = http.get.call_args
        self.assertIn("serviceKey=ab%2Fcd", args[0])
        self.assertIsNone(kwargs.get("params"))

    def test_missing_response_envelope_is_parsing_error(self):
        http = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "{}"
        resp.url = "https://apis.data.go.kr/x?serviceKey=SECRET"
        resp.content_type = "application/json"
        resp.headers = {"content-type": "application/json"}
        resp.attempt = 1
        http.get.return_value = resp
        http.request_log = []
        client = DataGoKrClient(config={}, http=http, service_key="SECRET")
        page = client.get_page(service_path="/x", operation="op", params={"pageNo": 1, "numOfRows": 5})
        self.assertEqual(page["error_status"], PARSING_ERROR)
        self.assertNotIn("SECRET", page.get("body_prefix") or "")


class SmokeCliTests(unittest.TestCase):
    def test_parse_sources(self):
        self.assertEqual(
            parse_sources("bid,award"),
            ["bid_notice", "award_result"],
        )
        self.assertEqual(len(parse_sources("all")), 4)
        with self.assertRaises(ValueError):
            parse_sources("nonsense")

    def test_smoke_defaults_max_records_and_pages(self):
        cfg = load_yaml(project_root() / "config" / "g2b-mice-lifecycle.yaml")
        with tempfile.TemporaryDirectory() as td:
            with patch("app.run_g2b_collect.resolve_service_key", return_value=None):
                manifest = run_g2b_collect(
                    today=date(2026, 7, 16),
                    raw_dir=Path(td),
                    config=cfg,
                    smoke_test=True,
                    sources=["bid_notice"],
                )
            self.assertTrue(manifest["smoke_test"])
            self.assertEqual(manifest["max_records"], 20)
            self.assertEqual(manifest["max_pages"], 2)
            self.assertEqual(manifest["sources"], ["bid_notice"])
            self.assertIsNotNone(manifest["from_date"])
            self.assertIsNotNone(manifest["to_date"])
            # only bid stage result present
            self.assertEqual(len(manifest["stages"]), 1)
            self.assertEqual(manifest["stages"][0]["stage"], "bid_notice")

    def test_help_lists_new_options(self):
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with redirect_stdout(buf):
                mvp_main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        text = buf.getvalue()
        for opt in (
            "--smoke-test",
            "--sources",
            "--from-date",
            "--to-date",
            "--max-records",
            "--max-pages",
            "--run-id",
            "--reuse-existing",
        ):
            self.assertIn(opt, text)

    def test_sources_selection_runs_only_selected(self):
        cfg = load_yaml(project_root() / "config" / "g2b-mice-lifecycle.yaml")
        with tempfile.TemporaryDirectory() as td:
            with patch("app.run_g2b_collect.resolve_service_key", return_value=None):
                manifest = run_g2b_collect(
                    today=date(2026, 7, 16),
                    raw_dir=Path(td),
                    config=cfg,
                    smoke_test=True,
                    sources=parse_sources("pre_notice,contract"),
                    max_records=20,
                    max_pages=2,
                )
            stages = [s["stage"] for s in manifest["stages"]]
            self.assertEqual(stages, ["pre_notice", "contract_result"])

    def test_get_page_xml_error_not_ok_empty(self):
        xml = """<?xml version="1.0"?>
        <OpenAPI_ServiceResponse>
          <cmmMsgHeader>
            <returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>
            <returnReasonCode>30</returnReasonCode>
          </cmmMsgHeader>
        </OpenAPI_ServiceResponse>"""
        http = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.text = xml
        resp.url = "https://apis.data.go.kr/x?serviceKey=SECRET"
        resp.content_type = "application/xml"
        http.get.return_value = resp
        http.request_log = [{"url": str(resp.url)}]
        client = DataGoKrClient(config={}, http=http, service_key="SECRET")
        page = client.get_page(service_path="/x", operation="op", params={"pageNo": 1, "numOfRows": 10})
        self.assertEqual(page["error_status"], SERVICE_NOT_APPROVED)
        self.assertNotIn("SECRET", page["url"])
        rows, meta, errs, hard = client.paginate(
            service_path="/x",
            operation="op",
            base_params={},
            max_pages=2,
            max_records=20,
            num_of_rows=10,
        )
        self.assertEqual(rows, [])
        self.assertEqual(hard, SERVICE_NOT_APPROVED)
        self.assertNotEqual(hard, OK_EMPTY)

    def test_smoke_isolation_no_key_overwrites_previous_outputs(self):
        day = date(2026, 7, 16)
        dummy_bid = {
            "bidNtceNo": "9999999",
            "bidNtceOrd": "01",
            "bidNtceNm": "테스트 용역",
            "ntceInsttNm": "발주기관",
            "dminsttNm": "수요기관",
            "bidNtceDate": "20260701",
            "bidClseDate": "20260720",
            "bidNtceDtlUrl": "https://example.com/bid/1",
        }

        def fake_link(*, normalized_dir: Path, out_dir: Path | None = None, today: date | None = None, config=None, selected_sources=None, **kwargs):
            out_dir = out_dir or normalized_dir
            total = 0
            for fname in ("pre_notices.jsonl", "bid_notices.jsonl", "award_results.jsonl", "contract_results.jsonl"):
                p = normalized_dir / fname
                if p.exists():
                    total += len(read_jsonl(p))
            rows = [
                {
                    "procurement_id": f"dummy:{i}",
                    "procurement_stage": "BID_NOTICE",
                    "title": "dummy",
                    "sales_priority": None,
                    "sales_windows": [],
                    "opportunity_routes": [],
                    "bid_assessment_applicable": False,
                    "url": "",
                }
                for i in range(total)
            ]
            write_jsonl(out_dir / "procurements.jsonl", rows)
            return {
                "normalized_dir": str(normalized_dir),
                "procurement_count": len(rows),
                "lifecycle": {},
                "previous_cycle": {},
                "event_links": {},
                "mice_events_available": 0,
            }

        with tempfile.TemporaryDirectory() as td:
            base_dir = Path(td)
            # Simulate a previous smoke run's raw output that should never be read.
            old_raw = base_dir / "data" / "raw" / "procurement" / f"{day.isoformat()}-smoke"
            write_jsonl(old_raw / "g2b_bid_notices.jsonl", [dummy_bid])

            with no_network_patches() as http_cls, patch(
                "app.run_g2b_mice_mvp.run_g2b_link", new=fake_link
            ):
                res = run_g2b_mice_mvp(
                    today=day,
                    smoke_test=True,
                    sources=["pre_notice"],
                    run_id="runIso1",
                    reuse_existing=False,
                    base_dir=base_dir,
                    max_records=5,
                    max_pages=1,
                )

            self.assertEqual(res["collect"]["auth_present"], False)
            self.assertEqual(res["normalize"]["normalized_total"], 0)
            self.assertEqual(res["link"]["procurement_count"], 0)
            self.assertEqual(res["collect"]["run_id"], "runIso1")
            self.assertEqual(res["collect"]["selected_sources"], ["pre_notice"])
            self.assertEqual(res["collect"]["fresh_raw_count"], 0)

            new_raw_dir = Path(res["collect"]["raw_dir"])
            self.assertEqual(len(read_jsonl(new_raw_dir / "g2b_bid_notices.jsonl")), 0)
            http_cls.assert_not_called()

    def test_smoke_isolation_single_source_pre_notice_does_not_leak_bid(self):
        day = date(2026, 7, 16)
        dummy_bid = {
            "bidNtceNo": "8888888",
            "bidNtceOrd": "01",
            "bidNtceNm": "테스트 용역",
            "ntceInsttNm": "발주기관",
            "dminsttNm": "수요기관",
            "bidNtceDate": "20260701",
            "bidClseDate": "20260720",
            "bidNtceDtlUrl": "https://example.com/bid/2",
        }

        def fake_link(*, normalized_dir: Path, out_dir: Path | None = None, today: date | None = None, config=None, selected_sources=None, **kwargs):
            out_dir = out_dir or normalized_dir
            total = 0
            for fname in ("pre_notices.jsonl", "bid_notices.jsonl"):
                p = normalized_dir / fname
                if p.exists():
                    total += len(read_jsonl(p))
            write_jsonl(out_dir / "procurements.jsonl", [{"procurement_id": "dummy"}] * total)
            return {"procurement_count": total, "normalized_dir": str(normalized_dir)}

        with tempfile.TemporaryDirectory() as td:
            base_dir = Path(td)
            old_raw = base_dir / "data" / "raw" / "procurement" / f"{day.isoformat()}-smoke"
            write_jsonl(old_raw / "g2b_bid_notices.jsonl", [dummy_bid])

            with no_network_patches() as http_cls, patch(
                "app.run_g2b_mice_mvp.run_g2b_link", new=fake_link
            ):
                res = run_g2b_mice_mvp(
                    today=day,
                    smoke_test=True,
                    sources=["pre_notice"],
                    run_id="runIso2",
                    reuse_existing=False,
                    base_dir=base_dir,
                    max_records=5,
                    max_pages=1,
                )

            self.assertEqual(res["collect"]["auth_present"], False)
            self.assertEqual(res["normalize"]["normalized_total"], 0)
            self.assertEqual(res["normalize"]["bid_notice_count"], 0)
            self.assertEqual(res["link"]["procurement_count"], 0)
            http_cls.assert_not_called()

    def test_smoke_isolation_consecutive_runs_no_pollution(self):
        day = date(2026, 7, 16)
        dummy_bid = {
            "bidNtceNo": "7777777",
            "bidNtceOrd": "01",
            "bidNtceNm": "테스트 용역",
            "ntceInsttNm": "발주기관",
            "dminsttNm": "수요기관",
            "bidNtceDate": "20260701",
            "bidClseDate": "20260720",
            "bidNtceDtlUrl": "https://example.com/bid/3",
        }

        def fake_link(*, normalized_dir: Path, out_dir: Path | None = None, today: date | None = None, config=None, selected_sources=None, **kwargs):
            out_dir = out_dir or normalized_dir
            total = 0
            for fname in ("pre_notices.jsonl", "bid_notices.jsonl"):
                p = normalized_dir / fname
                if p.exists():
                    total += len(read_jsonl(p))
            write_jsonl(
                out_dir / "procurements.jsonl",
                [{"procurement_id": f"dummy:{i}"} for i in range(total)],
            )
            return {"procurement_count": total, "normalized_dir": str(normalized_dir)}

        def fake_bid_collect(self):
            out_path = Path(self.raw_dir) / "g2b_bid_notices.jsonl"
            write_jsonl(out_path, [dummy_bid])
            return ProcurementCollectResult(
                stage=self.stage,
                success=True,
                status="OK",
                fetched_count=1,
                parsed_count=1,
                error_count=0,
                raw_output_path=str(out_path),
                errors=[],
                warnings=[],
                request_log=[],
                metadata={"auth_present": True},
            )

        with tempfile.TemporaryDirectory() as td:
            base_dir = Path(td)

            with (
                patch.dict("os.environ", {k: "" for k in KEY_ENV_VARS}, clear=False),
                patch("app.procurement_collectors.base.resolve_service_key", return_value="DUMMYASCIIKEY"),
                patch("app.run_g2b_collect.resolve_service_key", return_value="DUMMYASCIIKEY"),
                patch("app.mice_collectors.http_client.PoliteHttpClient") as http_cls,
                patch("time.sleep"),
                patch("app.run_g2b_mice_mvp.run_g2b_link", new=fake_link),
                patch("app.run_g2b_collect.G2bBidNoticeCollector.collect", new=fake_bid_collect),
            ):
                http_cls.return_value.request_log = []
                res1 = run_g2b_mice_mvp(
                    today=day,
                    smoke_test=True,
                    sources=["bid_notice"],
                    run_id="runA",
                    reuse_existing=False,
                    base_dir=base_dir,
                    max_records=5,
                    max_pages=1,
                )
                http_cls.assert_not_called()

            self.assertGreater(res1["link"]["procurement_count"], 0)

            with no_network_patches() as http_cls, patch(
                "app.run_g2b_mice_mvp.run_g2b_link", new=fake_link
            ):
                res2 = run_g2b_mice_mvp(
                    today=day,
                    smoke_test=True,
                    sources=["bid_notice"],
                    run_id="runB",
                    reuse_existing=False,
                    base_dir=base_dir,
                    max_records=5,
                    max_pages=1,
                )
                http_cls.assert_not_called()

            self.assertEqual(res2["collect"]["auth_present"], False)
            self.assertEqual(res2["normalize"]["normalized_total"], 0)
            self.assertEqual(res2["link"]["procurement_count"], 0)
            self.assertEqual(res2["collect"]["fresh_raw_count"], 0)
            self.assertEqual(res2["collect"]["normalized_count"], 0)
            self.assertEqual(res2["collect"]["procurement_count"], 0)


if __name__ == "__main__":
    unittest.main()
