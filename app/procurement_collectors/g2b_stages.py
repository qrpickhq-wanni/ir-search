"""G2B procurement stage registry — raw/normalized file mapping."""
from __future__ import annotations

from typing import Any, Callable

from app.procurement_normalizers.notice_normalizer import (
    normalize_award_result,
    normalize_bid_notice,
    normalize_contract_result,
    normalize_pre_notice,
)

ALL_G2B_STAGES = ("pre_notice", "bid_notice", "award_result", "contract_result")

# CLI alias → internal stage id (subset of run_g2b_collect.SOURCE_ALIASES values)
STAGE_RAW_FILES: dict[str, str] = {
    "pre_notice": "g2b_pre_notices.jsonl",
    "bid_notice": "g2b_bid_notices.jsonl",
    "award_result": "g2b_award_results.jsonl",
    "contract_result": "g2b_contract_results.jsonl",
}

STAGE_NORMALIZED_FILES: dict[str, str] = {
    "pre_notice": "pre_notices.jsonl",
    "bid_notice": "bid_notices.jsonl",
    "award_result": "award_results.jsonl",
    "contract_result": "contract_results.jsonl",
}

STAGE_COUNT_KEYS: dict[str, str] = {
    "pre_notice": "pre_notice_count",
    "bid_notice": "bid_notice_count",
    "award_result": "award_result_count",
    "contract_result": "contract_result_count",
}

STAGE_NORMALIZERS: dict[str, Callable[..., dict[str, Any]]] = {
    "pre_notice": normalize_pre_notice,
    "bid_notice": normalize_bid_notice,
    "award_result": normalize_award_result,
    "contract_result": normalize_contract_result,
}


def normalize_selected_sources(selected: list[str] | None) -> list[str]:
    if not selected:
        return list(ALL_G2B_STAGES)
    out: list[str] = []
    for stage in selected:
        if stage not in ALL_G2B_STAGES:
            raise ValueError(f"Unknown G2B stage: {stage!r}")
        if stage not in out:
            out.append(stage)
    return out
