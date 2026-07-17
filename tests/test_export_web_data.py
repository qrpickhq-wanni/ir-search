"""Tests for the static web deployment-data exporter."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.export_web_data import ExportError, OUTPUT_FIELDS, export_web_data


RUN_DAY = "2026-07-17"


def _row(index: int, **overrides):
    row = {
        "unified_opportunity_id": f"uop:{index:04d}",
        "domain_type": "MICE_EVENT" if index % 2 else "SUPPORT_PROGRAM",
        "title": f"행사 기회 {index}",
        "organization": f"기관 {index}",
        "opportunity_stage": "REVIEW",
        "primary_opportunity_route": "ORGANIZER_OUTREACH",
        "priority_band": "P1_THIS_WEEK",
        "unified_priority_score": 80 - index / 10,
        "relevance_reasons": ["행사 운영", "등록 시스템"],
        "expected_qrpick_role": ["등록", "체크인"],
        "recommended_next_action": "담당 부서 확인",
        "blocking_unknowns": ["구매 주체 확인"],
        "posted_at": "2026-07-16",
        "deadline": "2026-08-01",
        "source_urls": [f"https://example.com/opportunity/{index}"],
    }
    row.update(overrides)
    return row


def _write_run(
    normalized_root: Path,
    *,
    day: str = RUN_DAY,
    rows: list[dict] | None = None,
    status: str = "OK",
    top_ids: list[str] | None = None,
    manifest_count: int | None = None,
    write_manifest: bool = True,
    write_jsonl: bool = True,
) -> tuple[Path, list[dict]]:
    rows = rows if rows is not None else [_row(index) for index in range(1, 4)]
    run_dir = normalized_root / day
    run_dir.mkdir(parents=True)
    if write_jsonl:
        with (run_dir / "unified-opportunities.jsonl").open(
            "w", encoding="utf-8"
        ) as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    selected_ids = top_ids
    if selected_ids is None:
        selected_ids = [
            str(row["unified_opportunity_id"]) for row in rows[:30]
        ]
    actionable_count = sum(
        1 for row in rows if row.get("priority_band") != "NO_ACTION"
    )
    manifest = {
        "run_day": day,
        "status": status,
        "unified_row_count": len(rows) if manifest_count is None else manifest_count,
        "action_candidate_count": actionable_count,
        "top_row_count": len(selected_ids),
        "top_unified_opportunity_ids": selected_ids,
        "warnings": [],
        "outputs": {"jsonl": r"C:\private\source.jsonl"},
    }
    if write_manifest:
        (run_dir / "unified-opportunity-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False),
            encoding="utf-8",
        )
    return run_dir, rows


class ExportWebDataTests(unittest.TestCase):
    def test_creates_valid_latest_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            _write_run(normalized)
            output = root / "web" / "data" / "latest.json"

            payload = export_web_data(
                run_day=RUN_DAY,
                normalized_root=normalized,
                output_path=output,
            )
            persisted = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(payload["total_count"], 3)
            self.assertEqual(persisted["top30_count"], 3)
            self.assertEqual(len(persisted["opportunities"]), 3)
            self.assertEqual(persisted["run_status"], "OK")

    def test_missing_manifest_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            _write_run(normalized, write_manifest=False)
            with self.assertRaisesRegex(ExportError, "manifest missing"):
                export_web_data(
                    run_day=RUN_DAY,
                    normalized_root=normalized,
                    output_path=root / "latest.json",
                )

    def test_non_ok_manifest_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            _write_run(normalized, status="PARTIAL")
            with self.assertRaisesRegex(ExportError, "status must be OK"):
                export_web_data(
                    run_day=RUN_DAY,
                    normalized_root=normalized,
                    output_path=root / "latest.json",
                )

    def test_missing_jsonl_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            _write_run(normalized, write_jsonl=False)
            with self.assertRaisesRegex(ExportError, "JSONL missing"):
                export_web_data(
                    run_day=RUN_DAY,
                    normalized_root=normalized,
                    output_path=root / "latest.json",
                )

    def test_empty_jsonl_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            _write_run(normalized, rows=[])
            with self.assertRaisesRegex(ExportError, "zero rows"):
                export_web_data(
                    run_day=RUN_DAY,
                    normalized_root=normalized,
                    output_path=root / "latest.json",
                )

    def test_manifest_jsonl_count_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            _write_run(normalized, manifest_count=99)
            with self.assertRaisesRegex(ExportError, "count mismatch"):
                export_web_data(
                    run_day=RUN_DAY,
                    normalized_root=normalized,
                    output_path=root / "latest.json",
                )

    def test_failure_preserves_existing_latest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            _write_run(normalized, status="ERROR")
            output = root / "web" / "data" / "latest.json"
            output.parent.mkdir(parents=True)
            output.write_text('{"preserved": true}\n', encoding="utf-8")
            before = output.read_bytes()

            with self.assertRaises(ExportError):
                export_web_data(
                    run_day=RUN_DAY,
                    normalized_root=normalized,
                    output_path=output,
                )
            self.assertEqual(output.read_bytes(), before)

    def test_publish_failure_cleans_temp_and_preserves_latest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            _write_run(normalized)
            output = root / "web" / "data" / "latest.json"
            output.parent.mkdir(parents=True)
            output.write_text('{"preserved": true}\n', encoding="utf-8")
            before = output.read_bytes()

            with patch(
                "scripts.export_web_data.os.replace",
                side_effect=OSError("locked"),
            ):
                with self.assertRaisesRegex(ExportError, "publication failed"):
                    export_web_data(
                        run_day=RUN_DAY,
                        normalized_root=normalized,
                        output_path=output,
                    )

            self.assertEqual(output.read_bytes(), before)
            self.assertEqual(list(output.parent.glob(".latest-*.tmp")), [])

    def test_top30_is_limited_to_thirty(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            rows = [_row(index) for index in range(1, 36)]
            _write_run(normalized, rows=rows)
            output = root / "latest.json"

            payload = export_web_data(
                run_day=RUN_DAY,
                normalized_root=normalized,
                output_path=output,
            )
            self.assertEqual(payload["top30_count"], 30)
            self.assertEqual(len(payload["opportunities"]), 30)

    def test_missing_required_top_field_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            row = _row(1)
            del row["recommended_next_action"]
            _write_run(normalized, rows=[row])

            with self.assertRaisesRegex(ExportError, "missing required fields"):
                export_web_data(
                    run_day=RUN_DAY,
                    normalized_root=normalized,
                    output_path=root / "latest.json",
                )

    def test_api_key_patterns_are_redacted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            row = _row(
                1,
                recommended_next_action=(
                    "api_key=supersecret serviceKey:anothersecret "
                    "Bearer abc.def.ghi"
                ),
            )
            _write_run(normalized, rows=[row])

            payload = export_web_data(
                run_day=RUN_DAY,
                normalized_root=normalized,
                output_path=root / "latest.json",
            )
            serialized = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("supersecret", serialized)
            self.assertNotIn("anothersecret", serialized)
            self.assertNotIn("abc.def.ghi", serialized)
            self.assertIn("[REDACTED]", serialized)

    def test_local_absolute_paths_are_removed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            row = _row(
                1,
                blocking_unknowns=[
                    r"see C:\Users\operator\private\debug.json",
                    "/home/operator/private/input.json",
                ],
            )
            _write_run(normalized, rows=[row])

            payload = export_web_data(
                run_day=RUN_DAY,
                normalized_root=normalized,
                output_path=root / "latest.json",
            )
            serialized = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn(r"C:\Users", serialized)
            self.assertNotIn("/home/operator", serialized)
            self.assertIn("[REDACTED_PATH]", serialized)

    def test_disallowed_urls_are_removed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            row = _row(
                1,
                source_urls=[
                    "javascript:alert(1)",
                    "data:text/html,bad",
                    "file:///C:/secret.txt",
                    "ftp://example.com/file",
                ],
            )
            _write_run(normalized, rows=[row])

            payload = export_web_data(
                run_day=RUN_DAY,
                normalized_root=normalized,
                output_path=root / "latest.json",
            )
            self.assertEqual(payload["opportunities"][0]["source_urls"], [])

    def test_only_http_urls_remain_and_secret_query_is_removed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            row = _row(
                1,
                source_urls=[
                    "http://example.com/a",
                    "https://example.com/b?serviceKey=SECRET&view=full#section",
                ],
            )
            _write_run(normalized, rows=[row])

            payload = export_web_data(
                run_day=RUN_DAY,
                normalized_root=normalized,
                output_path=root / "latest.json",
            )
            urls = payload["opportunities"][0]["source_urls"]
            self.assertEqual(
                urls,
                [
                    "http://example.com/a",
                    "https://example.com/b?view=full",
                ],
            )

    def test_opportunities_match_manifest_top_ids_exactly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            rows = [_row(index) for index in range(1, 6)]
            selected = ["uop:0004", "uop:0002", "uop:0005"]
            _write_run(normalized, rows=rows, top_ids=selected)

            payload = export_web_data(
                run_day=RUN_DAY,
                normalized_root=normalized,
                output_path=root / "latest.json",
            )
            self.assertEqual(
                [row["unified_opportunity_id"] for row in payload["opportunities"]],
                selected,
            )

    def test_rank_order_is_stable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            rows = [_row(index) for index in range(1, 6)]
            selected = ["uop:0005", "uop:0001", "uop:0003"]
            _write_run(normalized, rows=rows, top_ids=selected)

            first = export_web_data(
                run_day=RUN_DAY,
                normalized_root=normalized,
                output_path=root / "first.json",
            )
            second = export_web_data(
                run_day=RUN_DAY,
                normalized_root=normalized,
                output_path=root / "second.json",
            )
            self.assertEqual(
                [(row["rank"], row["unified_opportunity_id"]) for row in first["opportunities"]],
                [(row["rank"], row["unified_opportunity_id"]) for row in second["opportunities"]],
            )

    def test_auto_selects_latest_ok_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            _write_run(normalized, day="2026-07-16", status="OK")
            _write_run(normalized, day="2026-07-17", status="PARTIAL")

            payload = export_web_data(
                normalized_root=normalized,
                output_path=root / "latest.json",
            )
            self.assertEqual(payload["run_date"], "2026-07-16")

    def test_output_row_contains_only_approved_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            row = _row(1, private_note="do not publish", contact_email="private@example.com")
            _write_run(normalized, rows=[row])

            payload = export_web_data(
                run_day=RUN_DAY,
                normalized_root=normalized,
                output_path=root / "latest.json",
            )
            self.assertEqual(
                set(payload["opportunities"][0]),
                {"rank", *OUTPUT_FIELDS},
            )
            serialized = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("private_note", serialized)
            self.assertNotIn("private@example.com", serialized)


if __name__ == "__main__":
    unittest.main()
