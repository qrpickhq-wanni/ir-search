"""Shared IO helpers for Phase-2 runners."""
from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[1]


def project_root() -> Path:
    return ROOT


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be mapping: {path}")
    return data


def find_latest_raw_dir(raw_root: Path | None = None) -> Path:
    raw_root = raw_root or (ROOT / "data" / "raw")
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    dirs = [p for p in raw_root.iterdir() if p.is_dir() and date_re.match(p.name)]
    if not dirs:
        raise FileNotFoundError(f"No YYYY-MM-DD folders under {raw_root}")
    return sorted(dirs, key=lambda p: p.name)[-1]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    ensure_dir(path.parent)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    return rows


def sort_for_csv(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(r: dict[str, Any]):
        score = r.get("first_pass_score")
        if score is None:
            score = -1
        deadline = r.get("deadline") or "9999-99-99"
        return (-int(score), deadline, r.get("title") or "")

    return sorted(rows, key=key)


CSV_COLUMNS = [
    ("행동대기열", "action_queue"),
    ("상세검증상태", "detail_verification_status"),
    ("실행가능검증", "actionability_verified"),
    ("승격출처", "action_promotion_source"),
    ("신뢰도", "fit_confidence"),
    ("주경로", "primary_asset_fit_path"),
    ("보조경로", "secondary_asset_fit_paths"),
    ("자산군", "matched_asset_families"),
    ("기회유형", "opportunity_type"),
    ("상태", "first_pass_status"),
    ("점수", "first_pass_score"),
    ("공고ID", "canonical_id"),
    ("공고명", "title"),
    ("기관", "organization"),
    ("카테고리", "category"),
    ("소스", "source"),
    ("중복출처수", "duplicate_count"),
    ("시작일", "application_start"),
    ("마감일", "deadline"),
    ("D-day", "dday"),
    ("적합근거", "fit_evidence"),
    ("미확정사항", "blocking_unknowns"),
    ("ACTION_NOW게이트", "actionability_gate_reasons"),
    ("근거출처", "evidence_source"),
    ("활용가능_QRPick기능", "usable_qrpick_features"),
    ("활용가능_쇼다자산", "usable_showda_assets"),
    ("신규개발범위", "new_development_scope"),
    ("파트너필요범위", "partner_required_scope"),
    ("다음행동", "recommended_next_action"),
    ("긍정근거", "positive_reasons"),
    ("부정근거", "negative_reasons"),
    ("상세확인사항", "review_reasons"),
    ("원문URL", "url"),
]

QUEUE_CSV_MAP = {
    "ACTION_NOW": "action-now.csv",
    "QUALIFICATION_CHECK": "qualification-check.csv",
    "SALES_OUTREACH": "sales-outreach.csv",
    "WATCHLIST": "watchlist.csv",
    "NO_ACTION": "no-action.csv",
}

# Phase-2 procurement-like bid assessment CSVs (not G2B-native collector output).
# One notice may appear in multiple CSVs when it has multiple opportunity_routes.
_BID_ROUTE_COMMON = [
    ("데이터범위", "source_scope"),
    ("입찰판정적용", "bid_assessment_applicable"),
    ("기회경로", "opportunity_routes"),
    ("대표경로", "primary_route"),
    ("입찰판정", "bid_go_no_go"),
    ("직접입찰적합경로", "direct_bid_fit_path"),
    ("입찰참여준비상태", "bid_participation_readiness"),
    ("자격충족상태", "eligibility_status"),
    ("사업명", "title"),
    ("발주기관", "organization"),
    ("공고번호", "source_id"),
    ("사업예산", "support_amount"),
    ("공고일", "posted_at"),
    ("제안마감일", "deadline"),
    ("남은일수", "dday"),
]

DIRECT_BID_COLUMNS = [
    *_BID_ROUTE_COMMON,
    ("입찰자격", "mandatory_qualification_requirements"),
    ("유사실적요건", "performance_requirements"),
    ("공동수급허용", "joint_contract_allowed"),
    ("하도급허용", "subcontract_allowed"),
    ("필수인력", "required_personnel"),
    ("QRPick·Showda수행범위", "qrpick_showda_delivery_scope"),
    ("파트너필요범위", "partner_needed_scope"),
    ("차단요인", "bid_blocking_reasons"),
    ("권장다음행동", "recommended_bid_action"),
    ("제안요청서URL", "attachment_urls"),
    ("원문URL", "url"),
]

CONSORTIUM_COLUMNS = [
    *_BID_ROUTE_COMMON,
    ("입찰역할", "bid_role"),
    ("공동수급허용", "joint_contract_allowed"),
    ("하도급허용", "subcontract_allowed"),
    ("QRPick·Showda수행범위", "qrpick_showda_delivery_scope"),
    ("파트너필요범위", "partner_needed_scope"),
    ("파트너의존도", "estimated_partner_dependency"),
    ("차단요인", "bid_blocking_reasons"),
    ("권장다음행동", "recommended_bid_action"),
    ("원문URL", "url"),
]

SOLUTION_PARTNER_COLUMNS = [
    *_BID_ROUTE_COMMON,
    ("입찰역할", "bid_role"),
    ("공동수급허용", "joint_contract_allowed"),
    ("하도급허용", "subcontract_allowed"),
    ("QRPick·Showda수행범위", "qrpick_showda_delivery_scope"),
    ("파트너필요범위", "partner_needed_scope"),
    ("파트너의존도", "estimated_partner_dependency"),
    ("차단요인", "bid_blocking_reasons"),
    ("권장다음행동", "recommended_bid_action"),
    ("원문URL", "url"),
]

# Backward-compatible aliases
G2B_DIRECT_BID_COLUMNS = DIRECT_BID_COLUMNS
G2B_CONSORTIUM_COLUMNS = CONSORTIUM_COLUMNS


def write_mapped_csv_bom(
    path: Path,
    columns: list[tuple[str, str]],
    rows: list[dict[str, Any]],
    *,
    preserve_order: bool = False,
) -> None:
    ensure_dir(path.parent)
    ordered = rows if preserve_order else sort_for_csv(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([c[0] for c in columns])
        for row in ordered:
            url = row.get("url") or row.get("detail_url") or ""
            cells = []
            for _header, key in columns:
                if key == "url":
                    cells.append(_cell(url))
                else:
                    cells.append(_cell(row.get(key)))
            writer.writerow(cells)



def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " | ".join(str(x) for x in value)
    return str(value)


def write_csv_bom(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    ordered = sort_for_csv(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([c[0] for c in CSV_COLUMNS])
        for row in ordered:
            url = row.get("url") or row.get("detail_url") or ""
            cells = []
            for header, key in CSV_COLUMNS:
                if key == "url":
                    cells.append(_cell(url))
                else:
                    cells.append(_cell(row.get(key)))
            writer.writerow(cells)


def iso_today() -> str:
    return date.today().isoformat()
