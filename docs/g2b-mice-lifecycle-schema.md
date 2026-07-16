# G2B MICE Procurement Lifecycle Schema

## Source

Official Public Data Portal (data.go.kr) OpenAPIs operated by 조달청:

| Stage | Dataset | Portal URL | Service URL |
|-------|---------|------------|-------------|
| Bid notice | 나라장터 입찰공고정보서비스 | https://www.data.go.kr/data/15129394/openapi.do | `https://apis.data.go.kr/1230000/ad/BidPublicInfoService` |
| Award | 나라장터 낙찰정보서비스 | https://www.data.go.kr/data/15129397/openapi.do | `https://apis.data.go.kr/1230000/as/ScsbidInfoService` |
| Pre-spec | 나라장터 사전규격정보서비스 | https://www.data.go.kr/data/15129437/openapi.do | `https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService` |
| Contract | 나라장터 계약정보서비스 | https://www.data.go.kr/data/15129427/openapi.do | `https://apis.data.go.kr/1230000/ao/CntrctInfoService` |

MVP uses **용역(service)** operations only (e.g. `getBidPblancListInfoServc`, `getBidPblancListInfoServcPPSSrch`).

## Auth

- Env: `DATA_GO_KR_SERVICE_KEY` (alts: `G2B_SERVICE_KEY`, `PUBLIC_DATA_SERVICE_KEY`)
- Apply for use on each dataset page above (PC).
- Keys are never written to logs, manifests, or git.

Without a key the collectors return `PARTIAL_EXPECTED` and still emit empty JSONL + reports.

## Raw layout

`data/raw/procurement/YYYY-MM-DD/`

- `g2b_pre_notices.jsonl`
- `g2b_bid_notices.jsonl`
- `g2b_award_results.jsonl`
- `g2b_contract_results.jsonl`
- `collection_manifest.json`
- `collection_errors.jsonl`

## Normalized record

`record_domain=PROCUREMENT_OPPORTUNITY`, `source_scope=G2B_OFFICIAL_OPENAPI`.

See `app/procurement_normalizers/schema.py` for the full field list.

## Lifecycle linking

Strong only: `notice_number` (+ revision), award/contract referencing notice number.

Change/re-notices share `lifecycle_group_id`; representative = highest revision.

Ambiguous links → `lifecycle_candidate_links` (manual review).

## Sales windows

Configured in `config/g2b-mice-lifecycle.yaml`. Bid assessment from `app/evaluators/bid_assessment.py` is reused (not rewritten).
