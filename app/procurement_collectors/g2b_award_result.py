"""G2B 용역 낙찰/개찰 collector (ScsbidInfoService)."""
from __future__ import annotations

from typing import Any

from app.procurement_collectors.base import ProcurementCollectResult, ProcurementCollector
from app.procurement_collectors.collect_helpers import collect_list_first
from app.procurement_collectors.g2b_bid_notice import _notice_key


class G2bAwardResultCollector(ProcurementCollector):
    stage = "award_result"

    def collect(self) -> ProcurementCollectResult:
        return collect_list_first(
            self,
            openapi_key="award_result",
            raw_filename="g2b_award_results.jsonl",
            past_days_key="award_contract_past_days",
            default_past_days=548,
            list_op_default="getScsbidListSttusServc",
            search_op_default="getScsbidListSttusServcPPSSrch",
            search_param_name="bidNtceNm",
            title_fields=("bidNtceNm",),
            prefer_list_first=True,
            record_key_fn=_key,
        )


def _key(row: dict[str, Any]) -> str | None:
    nk = _notice_key(row)
    if nk:
        return nk
    s = f"{row.get('bidwinnrNm') or ''}:{row.get('sucsfbidAmt') or ''}"
    return s if s != ":" else None
