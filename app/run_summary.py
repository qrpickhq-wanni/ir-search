"""Build Phase-2 markdown + CSV reports from scored opportunities."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.io_utils import QUEUE_CSV_MAP, ensure_dir, read_jsonl, sort_for_csv, write_csv_bom


CANDIDATE_STATUSES = {"HIGH_PRIORITY", "REVIEW", "DETAIL_REVIEW"}


def _md_table_row(cols: list[str]) -> str:
    return "| " + " | ".join(cols) + " |"


def build_summary_md(
    *,
    run_day: str,
    input_files: list[str],
    normalize_stats: dict,
    opportunities: list[dict],
    duplicates: list[dict],
) -> str:
    status_counts = Counter(r.get("first_pass_status") for r in opportunities)
    path_counts = Counter(r.get("primary_asset_fit_path") or r.get("asset_fit_path") for r in opportunities)
    kind_counts = Counter(r.get("opportunity_kind") for r in opportunities)
    otype_counts = Counter(r.get("opportunity_type") for r in opportunities)
    queue_counts = Counter(r.get("action_queue") for r in opportunities)
    conf_counts = Counter(r.get("fit_confidence") for r in opportunities)
    cat_counts = Counter((r.get("category") or "(없음)") for r in opportunities)
    auto_groups = [d for d in duplicates if d.get("type") == "auto_merged"]
    candidates = [r for r in opportunities if r.get("first_pass_status") in CANDIDATE_STATUSES]
    high = sort_for_csv([r for r in opportunities if r.get("first_pass_status") == "HIGH_PRIORITY"])
    detail = sort_for_csv([r for r in opportunities if r.get("first_pass_status") == "DETAIL_REVIEW"])

    occurrence_sum = sum(int(r.get("duplicate_count") or 1) for r in opportunities)
    # For unmerged reps, duplicate_count is 1 and equals one occurrence
    # Traceability: occurrence_sum + errors should equal input if all normalized rows are in reps via occurrences
    lines: list[str] = []
    lines.append(f"# QRPick 수집·정규화·1차필터 요약 — {run_day}")
    lines.append("")
    lines.append("> 경고: 자동 필터는 최종 지원 여부를 결정하지 않는다. 점수는 검토 순서용이다.")
    lines.append("")
    lines.append("## 실행 개요")
    lines.append(f"- 실행일: {run_day}")
    lines.append("- 입력 파일:")
    for p in input_files:
        lines.append(f"  - `{p}`")
    lines.append(f"- 입력 총건수: **{normalize_stats.get('input_total')}**")
    lines.append("- 소스별 입력건수:")
    for src, n in sorted((normalize_stats.get("source_counts") or {}).items()):
        lines.append(f"  - {src}: {n}")
    lines.append(f"- 정상 정규화 건수: **{normalize_stats.get('normalized_ok')}**")
    lines.append(f"- 오류 건수: **{normalize_stats.get('error_count')}**")
    lines.append(f"- 자동 병합 중복 그룹 수: **{normalize_stats.get('auto_merge_groups')}**")
    lines.append(f"- 중복으로 흡수된 추가 레코드 수: **{normalize_stats.get('absorbed_extra_records')}**")
    lines.append(f"- 대표 공고 수: **{len(opportunities)}**")
    lines.append(f"- 후보(HIGH/REVIEW/DETAIL) 수: **{len(candidates)}**")
    lines.append(f"- source_occurrences 합계(대표 기준): **{occurrence_sum}**")
    lines.append("")
    lines.append("## 상태별 건수")
    for st in ("HIGH_PRIORITY", "REVIEW", "DETAIL_REVIEW", "LOW_FIT", "EXPIRED", "UNKNOWN"):
        lines.append(f"- {st}: {status_counts.get(st, 0)}")
    lines.append("")
    lines.append("## primary_asset_fit_path 건수")
    for p in (
        "QRPICK_DIRECT",
        "QRPICK_EXTENSION",
        "SHOWDA_ASSET_REUSE",
        "CUSTOM_BUILD_SERVICE",
        "PARTNER_CONSORTIUM",
        "SALES_LEAD",
        "NO_REALISTIC_PATH",
    ):
        lines.append(f"- {p}: {path_counts.get(p, 0)}")
    lines.append("")
    lines.append("## opportunity_type 건수")
    for k, n in otype_counts.most_common():
        lines.append(f"- {k}: {n}")
    lines.append("")
    lines.append("## action_queue 건수")
    for q in ("ACTION_NOW", "QUALIFICATION_CHECK", "SALES_OUTREACH", "WATCHLIST", "NO_ACTION", "CLOSED"):
        lines.append(f"- {q}: {queue_counts.get(q, 0)}")
    lines.append("")
    lines.append("## fit_confidence 건수")
    for c in ("STRONG", "MEDIUM", "WEAK", "NONE"):
        lines.append(f"- {c}: {conf_counts.get(c, 0)}")
    lines.append("")
    lines.append("## action_queue × opportunity_type")
    otypes = sorted({r.get("opportunity_type") or "OTHER" for r in opportunities})
    queues = ["ACTION_NOW", "QUALIFICATION_CHECK", "SALES_OUTREACH", "WATCHLIST", "NO_ACTION", "CLOSED"]
    lines.append(_md_table_row(["queue\\\\type"] + otypes))
    lines.append(_md_table_row(["---"] * (1 + len(otypes))))
    for q in queues:
        row = [q]
        for ot in otypes:
            n = sum(1 for r in opportunities if r.get("action_queue") == q and (r.get("opportunity_type") or "OTHER") == ot)
            row.append(str(n))
        lines.append(_md_table_row(row))
    lines.append("")
    lines.append("## action_queue × primary_asset_fit_path")
    paths = [
        "QRPICK_DIRECT",
        "QRPICK_EXTENSION",
        "SHOWDA_ASSET_REUSE",
        "CUSTOM_BUILD_SERVICE",
        "PARTNER_CONSORTIUM",
        "SALES_LEAD",
        "NO_REALISTIC_PATH",
    ]
    lines.append(_md_table_row(["queue\\\\path"] + paths))
    lines.append(_md_table_row(["---"] * (1 + len(paths))))
    for q in queues:
        row = [q]
        for p in paths:
            n = sum(
                1
                for r in opportunities
                if r.get("action_queue") == q
                and (r.get("primary_asset_fit_path") or r.get("asset_fit_path")) == p
            )
            row.append(str(n))
        lines.append(_md_table_row(row))
    lines.append("")
    lines.append("> 판정 원칙: 사업 연관성(path/families)과 지금 할 행동(action_queue)을 분리한다. 자동 분류는 지원 가능 여부 확정이 아니다.")
    lines.append("")
    lines.append("## 기회 유형(legacy opportunity_kind) 건수")
    for k, n in kind_counts.most_common():
        lines.append(f"- {k}: {n}")
    lines.append("")
    lines.append("## 카테고리별 건수 (상위 20)")
    for cat, n in cat_counts.most_common(20):
        lines.append(f"- {cat}: {n}")
    lines.append("")
    lines.append("## 상위 후보 20건 (HIGH_PRIORITY → 점수순, 부족 시 REVIEW 포함)")
    top = sort_for_csv(high)[:20]
    if len(top) < 20:
        extra = sort_for_csv([r for r in candidates if r not in top])
        top = (top + extra)[:20]
    lines.append(_md_table_row(["점수", "상태", "경로", "공고명", "기관", "마감"]))
    lines.append(_md_table_row(["---", "---", "---", "---", "---", "---"]))
    for r in top:
        title = (r.get("title") or "")[:50]
        org = (r.get("organization") or "")[:20]
        lines.append(
            _md_table_row(
                [
                    str(r.get("first_pass_score")),
                    str(r.get("first_pass_status")),
                    str(r.get("asset_fit_path") or ""),
                    title.replace("|", "/"),
                    org.replace("|", "/"),
                    str(r.get("deadline") or ""),
                ]
            )
        )
    lines.append("")
    lines.append("## DETAIL_REVIEW 상위 20건")
    lines.append(_md_table_row(["점수", "공고명", "기관", "마감", "상세확인"]))
    lines.append(_md_table_row(["---", "---", "---", "---", "---"]))
    for r in detail[:20]:
        reasons = " / ".join(r.get("review_reasons") or [])[:80]
        lines.append(
            _md_table_row(
                [
                    str(r.get("first_pass_score")),
                    (r.get("title") or "")[:60].replace("|", "/"),
                    (r.get("organization") or "")[:30].replace("|", "/"),
                    str(r.get("deadline") or ""),
                    reasons.replace("|", "/"),
                ]
            )
        )
    lines.append("")
    lines.append("## 중복 판정 예시")
    for d in auto_groups[:10]:
        lines.append(
            f"- `{d.get('duplicate_group_id')}` reason={d.get('merge_reason')} "
            f"members={d.get('member_opportunity_ids')} count={d.get('duplicate_count')}"
        )
    if not auto_groups:
        lines.append("- (자동 병합 그룹 없음)")
    cand = [d for d in duplicates if d.get("type") == "candidate_duplicate"]
    lines.append(f"- candidate_duplicate 쌍: {len(cand)}")
    lines.append("")
    lines.append("## 오분류 가능성 및 한계")
    lines.append("- 제목·목록 필드만 사용한다. 자격요건·지원금·지역제한은 확정하지 않는다.")
    lines.append("- 회사 소재지·업력이 TODO이므로 지역·업력 요건은 항상 사람 확인이 필요하다.")
    lines.append("- 단일 산업 키워드(예: 바이오)만으로 제외하지 않으나, 배타적 맥락에서는 감점한다.")
    lines.append("- 전시·참가기업 모집은 판로 기회가 될 수 있어 무조건 LOW_FIT 하지 않는다.")
    lines.append("- 동일 사업이 다른 제목으로 게시되면 중복으로 잡히지 않을 수 있다.")
    lines.append("")
    lines.append("## 추적 무결성")
    lines.append(
        f"- 검증식: input_total({normalize_stats.get('input_total')}) "
        f"=? occurrence_sum({occurrence_sum}) + errors({normalize_stats.get('error_count')})"
    )
    ok = (
        int(normalize_stats.get("input_total") or 0)
        == occurrence_sum + int(normalize_stats.get("error_count") or 0)
    )
    lines.append(f"- 결과: **{'PASS' if ok else 'FAIL'}**")
    lines.append("")
    return "\n".join(lines) + "\n"


def run_summary(
    *,
    opportunities_path: Path,
    duplicates_path: Path,
    report_dir: Path,
    normalize_stats: dict,
    input_files: list[str],
    run_day: str | None = None,
) -> dict:
    run_day = run_day or date.today().isoformat()
    ensure_dir(report_dir)
    opportunities = read_jsonl(opportunities_path)
    duplicates = read_jsonl(duplicates_path) if duplicates_path.exists() else []

    md = build_summary_md(
        run_day=run_day,
        input_files=input_files,
        normalize_stats=normalize_stats,
        opportunities=opportunities,
        duplicates=duplicates,
    )
    summary_path = report_dir / "collection-summary.md"
    summary_path.write_text(md, encoding="utf-8")

    by_status = {
        "candidate-list.csv": [r for r in opportunities if r.get("first_pass_status") in CANDIDATE_STATUSES],
        "high-priority-list.csv": [r for r in opportunities if r.get("first_pass_status") == "HIGH_PRIORITY"],
        "review-list.csv": [r for r in opportunities if r.get("first_pass_status") == "REVIEW"],
        "needs-detail-review.csv": [r for r in opportunities if r.get("first_pass_status") == "DETAIL_REVIEW"],
        "low-fit-list.csv": [r for r in opportunities if r.get("first_pass_status") == "LOW_FIT"],
    }
    paths = {"collection-summary.md": str(summary_path)}
    for name, rows in by_status.items():
        p = report_dir / name
        write_csv_bom(p, rows)
        paths[name] = str(p)

    for queue, fname in QUEUE_CSV_MAP.items():
        rows = [r for r in opportunities if r.get("action_queue") == queue]
        p = report_dir / fname
        write_csv_bom(p, rows)
        paths[fname] = str(p)

    return {
        "report_dir": str(report_dir),
        "paths": paths,
        "status_counts": dict(Counter(r.get("first_pass_status") for r in opportunities)),
        "action_queue_counts": dict(Counter(r.get("action_queue") for r in opportunities)),
        "primary_path_counts": dict(
            Counter(r.get("primary_asset_fit_path") or r.get("asset_fit_path") for r in opportunities)
        ),
        "opportunity_type_counts": dict(Counter(r.get("opportunity_type") for r in opportunities)),
        "fit_confidence_counts": dict(Counter(r.get("fit_confidence") for r in opportunities)),
        "representative_count": len(opportunities),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write Phase-2 reports")
    ap.add_argument("--opportunities", type=Path, required=True)
    ap.add_argument("--duplicates", type=Path, required=True)
    ap.add_argument("--report-dir", type=Path, required=True)
    ap.add_argument("--normalize-stats", type=Path, required=True, help="JSON stats from normalize step")
    ap.add_argument("--run-day", type=str, default=None)
    args = ap.parse_args(argv)
    stats = json.loads(args.normalize_stats.read_text(encoding="utf-8"))
    input_files = [
        stats.get("raw_dir", "") + "/kstartup_all.jsonl",
        stats.get("raw_dir", "") + "/sources_all.jsonl",
    ]
    out = run_summary(
        opportunities_path=args.opportunities,
        duplicates_path=args.duplicates,
        report_dir=args.report_dir,
        normalize_stats=stats,
        input_files=input_files,
        run_day=args.run_day,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
