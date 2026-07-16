"""Build review CSVs and markdown summary for MICE MVP."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from app.io_utils import ensure_dir, project_root, read_jsonl


EVENTS_COLUMNS = [
    ("행사ID", "event_id"),
    ("행사명", "title"),
    ("행사유형", "event_type"),
    ("시작일", "start_date"),
    ("종료일", "end_date"),
    ("개최장소", "venue_name"),
    ("지역", "region"),
    ("주최기관", "host_organizations"),
    ("주관기관", "organizer_organizations"),
    ("운영기관", "operator_organizations"),
    ("공식홈페이지", "official_event_url"),
    ("소스", "source_id"),
    ("공개연락처여부", "_has_contact"),
    ("영업준비상태", "sales_readiness"),
    ("영업신호", "sales_signal_types"),
    ("QRPick적용가능서비스", "qrpick_service_matches"),
    ("권장다음행동", "suggested_sales_action"),
    ("원문URL", "source_url"),
]

SALES_CSV_COLUMNS = [
    "행사ID",
    "행사명",
    "시작일",
    "종료일",
    "상태",
    "행사유형",
    "영업준비상태",
    "영업신호",
    "영업신호근거",
    "확인된 기관",
    "공개연락경로",
    "권장다음행동",
    "QRPick적용가능서비스",
    "소스",
    "원문URL",
]


def _join(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return "; ".join(str(x) for x in v if x)
    return str(v)


def _has_contact(e: dict) -> str:
    if e.get("contact_email") or e.get("contact_phone") or e.get("contact_name") or e.get("contact_department"):
        return "Y"
    return "N"


def _orgs(e: dict) -> str:
    parts = []
    for k in ("host_organizations", "organizer_organizations", "operator_organizations", "pco_organizations"):
        parts.extend(e.get(k) or [])
    return "; ".join(dict.fromkeys(str(x) for x in parts if x))


def _public_contact_path(e: dict) -> str:
    bits = []
    if e.get("contact_email"):
        bits.append(f"email:{e['contact_email']}")
    if e.get("contact_phone"):
        bits.append(f"phone:{e['contact_phone']}")
    if e.get("contact_department"):
        bits.append(f"dept:{e['contact_department']}")
    if e.get("official_event_url"):
        bits.append(f"homepage:{e['official_event_url']}")
    return "; ".join(bits)


def write_bom_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def sort_sales_key(e: dict, today: date):
    readiness_rank = {
        "DIRECT_OPPORTUNITY": 0,
        "CONTACTABLE": 1,
        "RESEARCH": 2,
        "WATCH": 3,
        "NONE": 4,
    }
    start = e.get("start_date") or "9999-99-99"
    return (readiness_rank.get(e.get("sales_readiness") or "NONE", 9), start, e.get("title") or "")


def run_summary(*, day: str | None = None, root: Path | None = None) -> dict:
    root = root or project_root()
    base = root / "data" / "normalized" / "mice"
    if day:
        norm_dir = base / day
    else:
        dirs = sorted([p for p in base.iterdir() if p.is_dir()], key=lambda p: p.name)
        if not dirs:
            raise FileNotFoundError(f"No normalized mice folders under {base}")
        norm_dir = dirs[-1]
        day = norm_dir.name

    events = read_jsonl(norm_dir / "events.jsonl")
    dups = read_jsonl(norm_dir / "duplicates.jsonl") if (norm_dir / "duplicates.jsonl").exists() else []
    nerr = (
        read_jsonl(norm_dir / "normalization_errors.jsonl")
        if (norm_dir / "normalization_errors.jsonl").exists()
        else []
    )
    raw_manifest = root / "data" / "raw" / "mice" / day / "collection_manifest.json"
    collect_meta = {}
    if raw_manifest.exists():
        collect_meta = json.loads(raw_manifest.read_text(encoding="utf-8"))

    today = date.fromisoformat(day)
    reports = ensure_dir(root / "reports" / day)

    event_rows = []
    for e in events:
        row = {}
        for col, key in EVENTS_COLUMNS:
            if key == "_has_contact":
                row[col] = _has_contact(e)
            else:
                row[col] = _join(e.get(key))
        event_rows.append(row)
    write_bom_csv(reports / "mice-events.csv", [c for c, _ in EVENTS_COLUMNS], event_rows)

    # Sales CSV: readiness in DIRECT/CONTACTABLE/RESEARCH AND non-empty basis
    sales_events = [
        e
        for e in events
        if e.get("sales_readiness") in {"DIRECT_OPPORTUNITY", "CONTACTABLE", "RESEARCH"}
        and e.get("sales_signal_basis")
    ]
    sales_events.sort(key=lambda e: sort_sales_key(e, today))
    sales_rows = []
    for e in sales_events:
        sales_rows.append(
            {
                "행사ID": e.get("event_id") or "",
                "행사명": e.get("title") or "",
                "시작일": e.get("start_date") or "",
                "종료일": e.get("end_date") or "",
                "상태": e.get("event_status") or "",
                "행사유형": e.get("event_type") or "",
                "영업준비상태": e.get("sales_readiness") or "",
                "영업신호": _join(e.get("sales_signal_types")),
                "영업신호근거": _join(e.get("sales_signal_basis")),
                "확인된 기관": _orgs(e),
                "공개연락경로": _public_contact_path(e),
                "권장다음행동": e.get("suggested_sales_action") or "",
                "QRPick적용가능서비스": _join(e.get("qrpick_service_matches")),
                "소스": e.get("source_id") or "",
                "원문URL": e.get("source_url") or "",
            }
        )
    write_bom_csv(reports / "mice-sales-signals.csv", SALES_CSV_COLUMNS, sales_rows)

    # Contact CSV: real contact OR official inquiry with source URL required
    contact_events = []
    for e in events:
        has_contact = _has_contact(e) == "Y"
        has_home = bool(e.get("official_event_url"))
        src = e.get("contact_source_url") or (e.get("source_url") if has_contact else None)
        if has_contact and src:
            contact_events.append(e)
        elif has_home and e.get("source_url"):
            # Official inquiry path — not venue facility phone
            contact_events.append(e)
    contact_rows = []
    for e in contact_events:
        contact_rows.append(
            {
                "행사ID": e.get("event_id") or "",
                "행사명": e.get("title") or "",
                "담당자명": e.get("contact_name") or "",
                "부서": e.get("contact_department") or "",
                "이메일": e.get("contact_email") or "",
                "전화번호": e.get("contact_phone") or "",
                "연락처신뢰도": e.get("contact_confidence") or "",
                "출처URL": e.get("contact_source_url") or e.get("source_url") or "",
                "공식홈페이지": e.get("official_event_url") or "",
                "공개업무연락처": _has_contact(e),
                "공식문의경로": "Y" if e.get("official_event_url") else "N",
                "시설대표번호여부": "N",
                "소스": e.get("source_id") or "",
            }
        )
    write_bom_csv(
        reports / "mice-contact-presence.csv",
        [
            "행사ID",
            "행사명",
            "담당자명",
            "부서",
            "이메일",
            "전화번호",
            "연락처신뢰도",
            "출처URL",
            "공식홈페이지",
            "공개업무연락처",
            "공식문의경로",
            "시설대표번호여부",
            "소스",
        ],
        contact_rows,
    )

    host_n = sum(1 for e in events if e.get("host_organizations"))
    home_n = sum(1 for e in events if e.get("official_event_url"))
    contact_n = sum(1 for e in events if _has_contact(e) == "Y")
    inquiry_n = sum(1 for e in events if e.get("official_event_url"))
    sales_signal_n = sum(1 for e in events if e.get("sales_signal_types"))
    service_n = sum(1 for e in events if e.get("qrpick_service_matches"))
    readiness = Counter(e.get("sales_readiness") or "NONE" for e in events)
    dated = [e for e in events if e.get("start_date")]
    date_rate = (len(dated) / len(events) * 100) if events else 0.0
    err_types = Counter(e.get("error") or "unknown" for e in nerr)

    by_source: dict[str, int] = {}
    for e in events:
        by_source[e.get("source_id") or "?"] = by_source.get(e.get("source_id") or "?", 0) + 1

    songdo_meta = {}
    for s in collect_meta.get("sources") or []:
        if s.get("source_id") == "songdo_convenia":
            songdo_meta = s.get("metadata") or {}

    lines = [
        f"# MICE MVP 수집 요약 ({day})",
        "",
        "## 수집",
    ]
    for s in collect_meta.get("sources") or []:
        lines.append(
            f"- `{s.get('source_id')}`: status={s.get('status')} fetched={s.get('fetched_count')} "
            f"errors={s.get('error_count')} path={s.get('raw_output_path')}"
        )
        meta = s.get("metadata") or {}
        if s.get("source_id") == "songdo_convenia":
            lines.append(
                f"  - completeness={meta.get('completeness')} "
                f"observed_row_cap={meta.get('observed_row_cap')} "
                f"pagination_documented={meta.get('pagination_params_documented')} "
                f"totalCount_present={meta.get('totalCount_field_present')}"
            )
        for w in (s.get("warnings") or [])[:6]:
            lines.append(f"  - warning: {w}")
        for e in (s.get("errors") or [])[:5]:
            lines.append(f"  - error: {e}")

    lines += [
        "",
        "## 정규화·중복",
        f"- 대표 행사 수: {len(events)}",
        f"- 정규화 오류: {len(nerr)} (유형: {dict(err_types)})",
        f"- 중복 로그 행: {len(dups)}",
        f"- 확정 병합: {sum(1 for d in dups if d.get('relation')=='CONFIRMED_MERGE')}",
        f"- 후보 중복: {sum(1 for d in dups if d.get('relation')=='CANDIDATE')}",
        f"- 소스별 대표 건수: {by_source}",
        "",
        "## 적용 가능성 vs 영업신호",
        f"- qrpick_service_matches 보유: {service_n}",
        f"- sales_signal_types(근거 기반) 보유: {sales_signal_n}",
        f"- sales_readiness: {dict(readiness)}",
        f"- 영업 CSV 포함(DIRECT/CONTACTABLE/RESEARCH + basis): {len(sales_rows)}",
        "",
        "## 품질 지표",
        f"- 주최기관 존재: {host_n}",
        f"- 공식 홈페이지(문의경로): {inquiry_n}",
        f"- 공개 업무 연락처: {contact_n}",
        f"- 날짜 파싱 성공률: {date_rate:.1f}% ({len(dated)}/{len(events)})",
        "",
        "## KINTEX",
        "- API 키 미설정 시 PARTIAL 유지. `GG_OPENAPI_KEY` + `GG_KINTEX_OPENAPI_SERVICE` 설정 후 "
        "`python app/run_mice_collect.py --sources opendata_kintex_gg` 재실행.",
        "",
        "## 산출물",
        f"- `{reports / 'mice-events.csv'}` (전체·적용가능성)",
        f"- `{reports / 'mice-sales-signals.csv'}` (근거 있는 영업 후보만)",
        f"- `{reports / 'mice-contact-presence.csv'}`",
        "",
        "## 참고",
        "- qrpick_service_matches = 유형 기반 잠재 적용 가능성",
        "- sales_signal_types = 원문·구조화 필드 근거가 있는 영업 단서만",
        "- 연락처는 공개 원문만 보관하며 추정하지 않는다.",
    ]
    md_path = reports / "mice-collection-summary.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "day": day,
        "events": len(events),
        "host_n": host_n,
        "home_n": home_n,
        "contact_n": contact_n,
        "inquiry_n": inquiry_n,
        "sales_signal_n": sales_signal_n,
        "service_match_n": service_n,
        "sales_csv_n": len(sales_rows),
        "readiness": dict(readiness),
        "error_types": dict(err_types),
        "date_rate": date_rate,
        "songdo_completeness": songdo_meta.get("completeness"),
        "reports_dir": str(reports),
        "summary_md": str(md_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", default=None)
    args = parser.parse_args(argv)
    out = run_summary(day=args.day)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
