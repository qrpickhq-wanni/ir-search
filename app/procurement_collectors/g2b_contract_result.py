"""G2B 용역 계약정보 collector (CntrctInfoService)."""
from __future__ import annotations

from typing import Any

from app.procurement_collectors.base import ProcurementCollectResult, ProcurementCollector
from app.procurement_collectors.collect_helpers import collect_list_first


class G2bContractResultCollector(ProcurementCollector):
    stage = "contract_result"

    def collect(self) -> ProcurementCollectResult:
        return collect_list_first(
            self,
            openapi_key="contract_result",
            raw_filename="g2b_contract_results.jsonl",
            past_days_key="award_contract_past_days",
            default_past_days=548,
            list_op_default="getCntrctInfoListServc",
            search_op_default="getCntrctInfoListServcPPSSrch",
            # Official PPS request uses cntrctNm + inqryBgnDate/inqryEndDate (YYYYMMDD).
            search_param_name="cntrctNm",
            list_date_mode="datetime",
            search_date_mode="date",
            title_fields=("cntrctNm", "bidNtceNm"),
            record_key_fn=_key,
        )


def _key(row: dict[str, Any]) -> str | None:
    key = str(row.get("untyCntrctNo") or row.get("cntrctNo") or "").strip()
    if key:
        return key
    no = row.get("bidNtceNo")
    if no:
        return f"{no}:{row.get('cntrctNm')}"
    return None
