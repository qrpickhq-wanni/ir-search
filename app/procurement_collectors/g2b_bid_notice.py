"""G2B 용역 입찰공고 collector (BidPublicInfoService)."""
from __future__ import annotations

from typing import Any

from app.procurement_collectors.base import ProcurementCollectResult, ProcurementCollector
from app.procurement_collectors.collect_helpers import all_keywords, collect_list_first, safe_request_log


class G2bBidNoticeCollector(ProcurementCollector):
    stage = "bid_notice"

    def collect(self) -> ProcurementCollectResult:
        return collect_list_first(
            self,
            openapi_key="bid_notice",
            raw_filename="g2b_bid_notices.jsonl",
            past_days_key="bid_notice_past_days",
            default_past_days=180,
            list_op_default="getBidPblancListInfoServc",
            search_op_default="getBidPblancListInfoServcPPSSrch",
            search_param_name="bidNtceNm",
            title_fields=("bidNtceNm",),
            record_key_fn=_notice_key,
            prefer_list_first=True,
        )


# Back-compat aliases used by older imports/tests
_all_keywords = all_keywords
_safe_request_log = safe_request_log


def _notice_key(row: dict[str, Any]) -> str | None:
    no = row.get("bidNtceNo") or row.get("bidntceNo")
    ord_ = row.get("bidNtceOrd") or row.get("bidntceOrd") or "00"
    if not no:
        return None
    return f"{no}:{ord_}"


def _title_matches_keywords(row: dict[str, Any], keywords: list[str]) -> bool:
    title = str(row.get("bidNtceNm") or row.get("bidntceNm") or "")
    if not title:
        return False
    return any(k in title for k in keywords)
