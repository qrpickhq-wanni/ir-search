"""G2B 용역 사전규격 collector (HrcspSsstndrdInfoService)."""
from __future__ import annotations

from typing import Any

from app.procurement_collectors.base import ProcurementCollectResult, ProcurementCollector
from app.procurement_collectors.collect_helpers import collect_list_first


class G2bPreNoticeCollector(ProcurementCollector):
    stage = "pre_notice"

    def collect(self) -> ProcurementCollectResult:
        return collect_list_first(
            self,
            openapi_key="pre_notice",
            raw_filename="g2b_pre_notices.jsonl",
            past_days_key="bid_notice_past_days",
            default_past_days=180,
            list_op_default="getPublicPrcureThngInfoServc",
            search_op_default="getPublicPrcureThngInfoServcPPSSrch",
            search_param_name="prdctClsfcNoNm",
            title_fields=("prdctClsfcNoNm", "bidNtceNm", "orderPlanNm"),
            # Keyword PPS first historically yielded MICE-relevant pre-specs.
            prefer_list_first=False,
            record_key_fn=_key,
        )


def _key(row: dict[str, Any]) -> str | None:
    no = str(row.get("bfSpecRgstNo") or row.get("bfspecRgstNo") or "").strip()
    return no or None
