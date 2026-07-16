# QRPick Opportunity Classification Principles

## Purpose of automatic classification

자동 분류는 **지원 가능 여부를 확정하기 위한 것이 아니다.**

목적은 다음을 구분하여, 사람이 **다음 행동**을 결정하도록 돕는 것이다.

- 직접 적합 (QRPick/구축 즉시 검토)
- 상세확인 (자격·수요과제·과업 미확정)
- 영업·판로 (참가·부스·조달 시그널)
- 오탐 위험 / 우선순위 낮음 (교육생·입주·연관성 약함)

## ACTION_NOW gate (Phase-2 list data)

목록(JSONL title/meta)만으로는 **ACTION_NOW 금지**.

`detail_verification_status`가 `VERIFIED`이고 자격·과업·역할·마감·미확정이 해소된 뒤
(또는 `action_promotion_source=MANUAL`)에만 ACTION_NOW로 승격한다.

Phase-2 허용 대기열: QUALIFICATION_CHECK · SALES_OUTREACH · WATCHLIST · NO_ACTION · CLOSED

필드: `detail_verification_status`, `actionability_verified`, `actionability_gate_reasons`,
`blocking_unknowns`, `action_promotion_source`

## Direct bid / consortium gate (Showda · QRPick)

계약 상대방·수행기관을 선정하는 조달·용역·구축·운영사업자 공고에만 입찰 판정을 적용한다
(`bid_assessment_applicable=true`). 단순 지원금·입주·교육생·참가기업 모집 등은
`bid_assessment_applicable=false`이며 경로·NO_GO·직접입찰 CSV에 넣지 않는다.

적용 대상에 대해 다음 경로를 **독립** 평가한다.

- `DIRECT_PRIME_BID` / `CONSORTIUM_BID` / `SUBCONTRACT_OR_SOLUTION_PARTNER` / `AWARD_WINNER_SALES`

`direct_bid_fit_path`: QRPICK_STANDARD_SERVICE · QRPICK_PLUS_OPERATION · SHOWDA_CUSTOM_BUILD ·
SHOWDA_PLATFORM_AND_DATA · CONSORTIUM_REQUIRED · PARTNER_SPECIALIST_REQUIRED · NO_REALISTIC_DIRECT_BID_PATH

규칙:
- 산업명만으로 직접 입찰을 제외하지 않는다. SW·운영·구축 역할 신호가 있으면 경로를 연다.
- 제안요청서·과업지시서 미확보 시 `eligibility_status=UNKNOWN_NEEDS_DOCUMENT_REVIEW`,
  `bid_participation_readiness=QUALIFICATION_CHECK`. **VERIFIED_ELIGIBLE / GO / 직접입찰 ACTION_NOW 금지**.
- `sales_windows`에 `DIRECT_BID_WINDOW`, `CONSORTIUM_PARTNER_WINDOW`를 추가할 수 있다
  (`CONSORTIUM_PLATFORM_WINDOW`와 혼용하지 않음).

보고서 (나라장터 전용 collector 미구현):
`direct-bid-opportunities.csv` (`DIRECT_PRIME_BID`),
`consortium-opportunities.csv` (`CONSORTIUM_BID`),
`solution-partner-opportunities.csv` (`SUBCONTRACT_OR_SOLUTION_PARTNER`).
각 CSV에 `opportunity_routes`·`primary_route` 포함. 복수 경로는 해당 보고서에 각각 기록.
`source_scope=PHASE2_PROCUREMENT_LIKE_NOT_G2B_COLLECTOR`.
`eligibility_status`는 자격 조건만 표현하고, 마감 경과는 `bid_participation_readiness`/`bid_go_no_go`로만 반영한다.


## SHOWDA_ASSET_REUSE gate

반드시 `matched_asset_families`에 자산군을 명시한다.

허용 자산군:
- QRPICK_EVENT_OPERATIONS
- AI_PUBLIC_INFORMATION_SERVICE
- CONTENT_CURATION_PLATFORM
- B2B_MATCHING_OR_COMMERCE
- MOBILE_MARKETING_AND_COUPON
- DATA_CRM_AND_DASHBOARD
- WEB_SAAS_SERVICE_PLANNING

`AI`, `플랫폼`, `서비스`, `데이터`, `디지털` 단독으로는 부여 금지.

## CUSTOM_BUILD_SERVICE gate

구축·개발·고도화·운영시스템·플랫폼 제작·시스템/서비스 실증·운영대행·유지관리·정보화·기획/컨설팅 용역 등 **명시 키워드**가 있을 때만.

## Company profile warning

`verification_status: INTERNAL_COMPANY_PROFILE_ONLY` 이면  
설립일·소재지·대표 정보는 내부 확인용이며 공식 자격판정에 쓰지 않는다.
