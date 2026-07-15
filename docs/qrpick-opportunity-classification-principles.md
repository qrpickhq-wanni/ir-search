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
