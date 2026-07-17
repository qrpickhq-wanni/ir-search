"""Build the product-wide lightweight unified opportunity ledger and Top 30."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.io_utils import ensure_dir, project_root, read_jsonl, write_jsonl, write_mapped_csv_bom
from app.unified_opportunities import (
    adapt_record,
    merge_unified_records,
    public_record,
    unified_sort_key,
)


UNIFIED_CSV_COLUMNS = [
    ("순위", "_rank"),
    ("우선순위", "priority_band"),
    ("기회유형", "domain_type"),
    ("현재단계", "opportunity_stage"),
    ("주경로", "primary_opportunity_route"),
    ("보조경로", "secondary_opportunity_routes"),
    ("사업명", "title"),
    ("기관", "organization"),
    ("공개일", "posted_at"),
    ("마감일", "deadline"),
    ("통합점수", "unified_priority_score"),
    ("행동시급성", "urgency_score"),
    ("사업적합성", "business_fit_score"),
    ("매출가능성", "revenue_potential_score"),
    ("접촉가능성", "contactability_score"),
    ("정보완성도", "information_completeness_score"),
    ("기한위험", "deadline_risk_score"),
    ("적합근거", "relevance_reasons"),
    ("예상 QRPick·쇼다 역할", "expected_qrpick_role"),
    ("권장 다음 행동", "recommended_next_action"),
    ("미확인 사항", "blocking_unknowns"),
    ("원문 URL", "source_urls"),
    ("통합기회ID", "unified_opportunity_id"),
    ("원본레코드ID", "source_record_ids"),
]

OUTPUT_FILENAMES = (
    "unified-opportunity-top30.csv",
    "unified-opportunity-all.csv",
    "unified-opportunity-summary.md",
)
NORMALIZED_FILENAMES = (
    "unified-opportunities.jsonl",
    "unified-opportunity-manifest.json",
)


class UnifiedOutputError(RuntimeError):
    """Raised when a unified run cannot safely publish complete outputs."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rooted_path(path: Path, root: Path) -> Path:
    """Resolve CLI paths against the repository root, never the caller's cwd."""
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _physical_line_count(path: Path) -> int:
    with path.open("rb") as fh:
        return sum(1 for _ in fh)


def _csv_data_row_count(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return sum(1 for _ in csv.DictReader(fh))


def _input_specs(
    *,
    run_day: str,
    support_path: Path | None,
    mice_path: Path | None,
    procurement_paths: list[Path] | None,
) -> list[tuple[str, Path]]:
    root = project_root()
    support = _rooted_path(
        support_path or Path("data") / "normalized" / run_day / "opportunities.jsonl",
        root,
    )
    mice = _rooted_path(
        mice_path or Path("data") / "normalized" / "mice" / run_day / "events.jsonl",
        root,
    )
    procurements = procurement_paths or [
        Path("data") / "normalized" / "procurement" / run_day / "procurements.jsonl"
    ]
    return [
        ("support", support),
        ("mice", mice),
        *[("procurement", _rooted_path(path, root)) for path in procurements],
    ]


def _read_inputs(
    specs: list[tuple[str, Path]],
) -> tuple[list[tuple[str, dict[str, Any]]], list[dict[str, Any]], list[str]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    statuses: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, (domain, path) in enumerate(specs):
        status: dict[str, Any] = {
            "input_id": f"{domain}:{index}",
            "domain": domain,
            "path": str(path),
            "status": "MISSING",
            "row_count": 0,
            "physical_line_count": 0,
            "sha256": None,
            "size_bytes": None,
        }
        if not path.exists():
            warnings.append(f"MISSING_INPUT:{domain}:{path}")
            statuses.append(status)
            continue
        try:
            input_rows = read_jsonl(path)
            status.update(
                {
                    "status": "OK" if input_rows else "EMPTY",
                    "row_count": len(input_rows),
                    "physical_line_count": _physical_line_count(path),
                    "sha256": _sha256(path),
                    "size_bytes": path.stat().st_size,
                }
            )
            rows.extend((domain, row) for row in input_rows)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            status["status"] = "ERROR"
            status["error"] = f"{type(exc).__name__}: {exc}"
            warnings.append(f"INPUT_ERROR:{domain}:{path}")
        statuses.append(status)
    return rows, statuses, warnings


def _ranked_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for rank, row in enumerate(rows, start=1):
        out = public_record(row)
        out["_rank"] = rank
        ranked.append(out)
    return ranked


def _score_average(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(float(row.get(key) or 0) for row in rows) / len(rows), 2)


def _summary_markdown(
    *,
    run_day: str,
    input_statuses: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
    top_rows: list[dict[str, Any]],
    duplicate_count: int,
    warnings: list[str],
) -> str:
    input_by_domain = Counter()
    for status in input_statuses:
        input_by_domain[status["domain"]] += int(status.get("row_count") or 0)
    unified_by_domain = Counter(str(row.get("domain_type")) for row in all_rows)
    action_by_domain = Counter(
        str(row.get("domain_type"))
        for row in all_rows
        if row.get("priority_band") != "NO_ACTION"
    )
    priority_counts = Counter(str(row.get("priority_band")) for row in all_rows)
    top_domains = Counter(str(row.get("domain_type")) for row in top_rows)
    max_domain, max_count = ("NONE", 0)
    if top_domains:
        max_domain, max_count = top_domains.most_common(1)[0]
    monopoly_reason = (
        f"{max_domain}가 {max_count}/{len(top_rows)}건으로 가장 많다. "
        "도메인 할당량은 적용하지 않았으며 공통축 점수·기한·최근성 결과다."
        if top_rows
        else "Top 30 후보가 없다."
    )

    over_risk = sorted(
        top_rows,
        key=lambda row: (
            int(row.get("information_completeness_score") or 0),
            -len(row.get("blocking_unknowns") or []),
            -float(row.get("unified_priority_score") or 0),
        ),
    )[:10]
    under_risk = sorted(
        [row for row in all_rows if row.get("priority_band") == "NO_ACTION"],
        key=lambda row: (
            -float(row.get("unified_priority_score") or 0),
            str(row.get("unified_opportunity_id") or ""),
        ),
    )[:10]

    lines = [
        f"# Unified Opportunity Summary ({run_day})",
        "",
        "## Run status",
        f"- inputs: **{sum(input_by_domain.values())}**",
        f"- unified ledger: **{len(all_rows)}**",
        f"- duplicate merges: **{duplicate_count}**",
        f"- Top 30 rows: **{len(top_rows)}**",
        f"- warnings: **{len(warnings)}**",
        "",
        "## Input counts",
    ]
    for domain in ("support", "mice", "procurement"):
        lines.append(f"- {domain}: {input_by_domain.get(domain, 0)}")
    lines += ["", "## Unified counts by domain"]
    for domain, count in sorted(unified_by_domain.items()):
        lines.append(f"- {domain}: {count}")
    lines += ["", "## Action candidates by domain"]
    for domain in sorted(unified_by_domain):
        lines.append(f"- {domain}: {action_by_domain.get(domain, 0)}")
    lines += ["", "## Priority bands"]
    for band in ("P0_IMMEDIATE", "P1_THIS_WEEK", "P2_REVIEW", "P3_WATCH", "NO_ACTION"):
        lines.append(f"- {band}: {priority_counts.get(band, 0)}")
    lines += ["", "## Top 30 domain composition"]
    for domain, count in sorted(top_domains.items()):
        lines.append(f"- {domain}: {count}")
    lines += [
        "",
        f"- composition note: {monopoly_reason}",
        "",
        "## Top opportunities",
        "",
        "| Rank | Band | Domain | Score | Title | Recommended next action |",
        "|---:|---|---|---:|---|---|",
    ]
    for index, row in enumerate(top_rows, start=1):
        title = str(row.get("title") or "").replace("|", "/")
        action = str(row.get("recommended_next_action") or "").replace("|", "/")
        lines.append(
            f"| {index} | {row.get('priority_band')} | {row.get('domain_type')} | "
            f"{row.get('unified_priority_score')} | {title} | {action} |"
        )
    lines += [
        "",
        "## Common-axis averages by Top 30 domain",
        "",
        "| Domain | Rows | Urgency | Fit | Revenue | Contact | Completeness | Deadline risk |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in top_rows:
        grouped[str(row.get("domain_type"))].append(row)
    for domain, domain_rows in sorted(grouped.items()):
        lines.append(
            f"| {domain} | {len(domain_rows)} | "
            f"{_score_average(domain_rows, 'urgency_score')} | "
            f"{_score_average(domain_rows, 'business_fit_score')} | "
            f"{_score_average(domain_rows, 'revenue_potential_score')} | "
            f"{_score_average(domain_rows, 'contactability_score')} | "
            f"{_score_average(domain_rows, 'information_completeness_score')} | "
            f"{_score_average(domain_rows, 'deadline_risk_score')} |"
        )
    lines += [
        "",
        "## Over-classification risk sample",
        "- Top rows with low completeness or many blocking unknowns; human review required.",
    ]
    for row in over_risk:
        lines.append(
            f"- [{row.get('domain_type')}] {row.get('title')} — "
            f"completeness={row.get('information_completeness_score')}, "
            f"unknowns={len(row.get('blocking_unknowns') or [])}"
        )
    lines += [
        "",
        "## Under-classification risk sample",
        "- Highest common scores among native NO_ACTION rows; inspect only as an audit sample.",
    ]
    for row in under_risk:
        lines.append(
            f"- [{row.get('domain_type')}] {row.get('title')} — "
            f"score={row.get('unified_priority_score')}"
        )
    if warnings:
        lines += ["", "## Warnings"]
        lines.extend(f"- {warning}" for warning in warnings)
    lines += [
        "",
        "> Native domain scores are not inputs to unified_priority_score.",
        "> Unverified detail/eligibility can never produce P0_IMMEDIATE.",
        "> The operator selects 5–10 actual actions from this Top 30.",
        "",
    ]
    return "\n".join(lines)


def _require_complete_inputs(input_statuses: list[dict[str, Any]]) -> None:
    invalid = [status for status in input_statuses if status["status"] != "OK"]
    if not invalid:
        return
    details = "; ".join(
        f"{status['status']}:{status['domain']}:{status['path']}"
        for status in invalid
    )
    raise UnifiedOutputError(f"Unified input validation failed: {details}")


def _validate_staged_outputs(
    *,
    normalized_dir: Path,
    report_dir: Path,
    expected_all: int,
    action_candidates: int,
    top_n: int,
) -> dict[str, int]:
    jsonl_count = len(read_jsonl(normalized_dir / "unified-opportunities.jsonl"))
    all_csv_count = _csv_data_row_count(report_dir / "unified-opportunity-all.csv")
    top_csv_count = _csv_data_row_count(report_dir / "unified-opportunity-top30.csv")
    expected_top = min(top_n, action_candidates)
    failures = []
    if jsonl_count <= 0 or jsonl_count != expected_all:
        failures.append(f"jsonl={jsonl_count}, expected={expected_all}>0")
    if all_csv_count <= 0 or all_csv_count != expected_all:
        failures.append(f"all_csv={all_csv_count}, expected={expected_all}>0")
    if action_candidates <= 0:
        failures.append("action_candidates=0, expected>0")
    if top_csv_count != expected_top:
        failures.append(f"top_csv={top_csv_count}, expected={expected_top}")
    if failures:
        raise UnifiedOutputError(
            "Unified staged output validation failed: " + "; ".join(failures)
        )
    return {
        "jsonl_row_count": jsonl_count,
        "all_csv_data_row_count": all_csv_count,
        "top_csv_data_row_count": top_csv_count,
    }


def _publish_staged_outputs(
    *,
    staged_normalized_dir: Path,
    staged_report_dir: Path,
    normalized_dir: Path,
    report_dir: Path,
) -> None:
    pairs = [
        *[
            (staged_normalized_dir / name, normalized_dir / name)
            for name in NORMALIZED_FILENAMES
        ],
        *[
            (staged_report_dir / name, report_dir / name)
            for name in OUTPUT_FILENAMES
        ],
    ]
    with tempfile.TemporaryDirectory(
        prefix=".unified-output-backup-", dir=normalized_dir.parent
    ) as backup_name:
        backup_dir = Path(backup_name)
        backups: dict[Path, Path] = {}
        originally_missing: set[Path] = set()
        for index, (_staged, final) in enumerate(pairs):
            if final.exists():
                backup = backup_dir / f"{index}-{final.name}"
                shutil.copy2(final, backup)
                backups[final] = backup
            else:
                originally_missing.add(final)
        try:
            for staged, final in pairs:
                os.replace(staged, final)
        except OSError:
            for final, backup in backups.items():
                shutil.copy2(backup, final)
            for final in originally_missing:
                if final.exists():
                    final.unlink()
            raise


def run_unified_output(
    *,
    run_day: str,
    support_path: Path | None = None,
    mice_path: Path | None = None,
    procurement_paths: list[Path] | None = None,
    normalized_dir: Path | None = None,
    report_dir: Path | None = None,
    top_n: int = 30,
) -> dict[str, Any]:
    if top_n <= 0:
        raise UnifiedOutputError(f"top_n must be positive: {top_n}")
    today = date.fromisoformat(run_day)
    root = project_root()
    normalized_dir = _rooted_path(
        normalized_dir or Path("data") / "normalized" / run_day,
        root,
    )
    report_dir = _rooted_path(report_dir or Path("reports") / run_day, root)

    specs = _input_specs(
        run_day=run_day,
        support_path=support_path,
        mice_path=mice_path,
        procurement_paths=procurement_paths,
    )
    raw_rows, input_statuses, warnings = _read_inputs(specs)
    _require_complete_inputs(input_statuses)
    adapted_domain_counts = Counter(domain for domain, _record in raw_rows)
    adapted = [
        adapt_record(record, source_domain=domain, today=today)
        for domain, record in raw_rows
    ]
    merged, duplicate_count = merge_unified_records(adapted)
    all_rows = sorted(merged, key=unified_sort_key)
    action_rows = [row for row in all_rows if row.get("priority_band") != "NO_ACTION"]
    top_rows = action_rows[: max(0, top_n)]
    if not all_rows:
        raise UnifiedOutputError("Unified transformation produced zero rows")
    if not action_rows:
        raise UnifiedOutputError("Unified transformation produced zero action candidates")

    priority_counts = Counter(str(row.get("priority_band")) for row in all_rows)
    unified_domain_counts = Counter(str(row.get("domain_type")) for row in all_rows)
    top_domain_counts = Counter(str(row.get("domain_type")) for row in top_rows)
    action_domain_counts = Counter(
        str(row.get("domain_type")) for row in action_rows
    )
    manifest = {
        "schema_version": "unified-opportunity-v1",
        "run_day": run_day,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "OK",
        "working_directory": str(Path.cwd().resolve()),
        "project_root": str(root.resolve()),
        "inputs": input_statuses,
        "input_row_count": len(raw_rows),
        "adapted_row_count": len(adapted),
        "adapted_source_domain_counts": dict(adapted_domain_counts),
        "unified_row_count": len(all_rows),
        "duplicate_merge_count": duplicate_count,
        "action_candidate_count": len(action_rows),
        "top_n": top_n,
        "top_row_count": len(top_rows),
        "priority_band_counts": dict(priority_counts),
        "unified_domain_counts": dict(unified_domain_counts),
        "action_candidate_domain_counts": dict(action_domain_counts),
        "top_domain_counts": dict(top_domain_counts),
        "top_unified_opportunity_ids": [
            row.get("unified_opportunity_id") for row in top_rows
        ],
        "warnings": warnings,
        "scoring_policy": {
            "native_scores_used": False,
            "weights": {
                "urgency": 0.20,
                "business_fit": 0.25,
                "revenue_potential": 0.15,
                "contactability": 0.10,
                "information_completeness": 0.15,
                "recency": 0.10,
                "deadline_safety": 0.05,
            },
            "p0_requires_verified_detail_and_eligibility": True,
            "domain_quotas": False,
        },
        "outputs": {
            "jsonl": str(normalized_dir / "unified-opportunities.jsonl"),
            "top_csv": str(report_dir / "unified-opportunity-top30.csv"),
            "all_csv": str(report_dir / "unified-opportunity-all.csv"),
            "summary": str(report_dir / "unified-opportunity-summary.md"),
            "manifest": str(normalized_dir / "unified-opportunity-manifest.json"),
        },
    }

    ensure_dir(normalized_dir)
    ensure_dir(report_dir)
    with tempfile.TemporaryDirectory(
        prefix=".unified-output-stage-", dir=normalized_dir.parent
    ) as staged_normalized_name, tempfile.TemporaryDirectory(
        prefix=".unified-output-stage-", dir=report_dir.parent
    ) as staged_report_name:
        staged_normalized_dir = Path(staged_normalized_name)
        staged_report_dir = Path(staged_report_name)
        public_all = [public_record(row) for row in all_rows]
        write_jsonl(
            staged_normalized_dir / "unified-opportunities.jsonl",
            public_all,
        )
        write_mapped_csv_bom(
            staged_report_dir / "unified-opportunity-all.csv",
            UNIFIED_CSV_COLUMNS,
            _ranked_rows(all_rows),
            preserve_order=True,
        )
        write_mapped_csv_bom(
            staged_report_dir / "unified-opportunity-top30.csv",
            UNIFIED_CSV_COLUMNS,
            _ranked_rows(top_rows),
            preserve_order=True,
        )
        summary = _summary_markdown(
            run_day=run_day,
            input_statuses=input_statuses,
            all_rows=all_rows,
            top_rows=top_rows,
            duplicate_count=duplicate_count,
            warnings=warnings,
        )
        (staged_report_dir / "unified-opportunity-summary.md").write_text(
            summary,
            encoding="utf-8",
        )
        output_validation = _validate_staged_outputs(
            normalized_dir=staged_normalized_dir,
            report_dir=staged_report_dir,
            expected_all=len(all_rows),
            action_candidates=len(action_rows),
            top_n=top_n,
        )
        manifest["output_validation"] = output_validation
        (staged_normalized_dir / "unified-opportunity-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _publish_staged_outputs(
            staged_normalized_dir=staged_normalized_dir,
            staged_report_dir=staged_report_dir,
            normalized_dir=normalized_dir,
            report_dir=report_dir,
        )
    return manifest


def _print_input_selection(
    specs: list[tuple[str, Path]],
    *,
    stream: TextIO,
) -> None:
    print(f"working_directory={Path.cwd().resolve()}", file=stream)
    print(f"project_root={project_root().resolve()}", file=stream)
    for index, (domain, path) in enumerate(specs):
        exists = path.exists()
        line_count = _physical_line_count(path) if exists else 0
        print(
            f"input[{index}] domain={domain} path={path} "
            f"exists={exists} physical_lines={line_count}",
            file=stream,
        )
    stream.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-day", default=date.today().isoformat())
    parser.add_argument("--support", type=Path)
    parser.add_argument("--mice", type=Path)
    parser.add_argument("--procurement", type=Path, action="append")
    parser.add_argument("--normalized-dir", type=Path)
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--top-n", type=int, default=30)
    args = parser.parse_args(argv)
    specs = _input_specs(
        run_day=args.run_day,
        support_path=args.support,
        mice_path=args.mice,
        procurement_paths=args.procurement,
    )
    _print_input_selection(specs, stream=sys.stdout)
    try:
        manifest = run_unified_output(
            run_day=args.run_day,
            support_path=args.support,
            mice_path=args.mice,
            procurement_paths=args.procurement,
            normalized_dir=args.normalized_dir,
            report_dir=args.report_dir,
            top_n=args.top_n,
        )
    except UnifiedOutputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for status in manifest["inputs"]:
        print(
            f"loaded domain={status['domain']} path={status['path']} "
            f"rows={status['row_count']}"
        )
    print(
        "counts "
        f"loaded={manifest['input_row_count']} "
        f"adapted={manifest['adapted_row_count']} "
        f"adapted_by_domain={manifest['adapted_source_domain_counts']} "
        f"unified={manifest['unified_row_count']} "
        f"action_candidates={manifest['action_candidate_count']} "
        f"top={manifest['top_row_count']}"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
