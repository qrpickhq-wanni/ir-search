# MICE 행사 공통 스키마 (Service 1B-1A)

기준일: 2026-07-15  
코드: `app/mice_normalizers/schema.py`

`record_domain`은 항상 `MICE_EVENT`이다. 공고(지원사업·입찰) 스키마와 물리적으로 분리한다.

## 표준 필드

| 필드 | 설명 |
|---|---|
| event_id / canonical_event_id | 소스·식별자·제목·시작일 기반 안정 해시 ID |
| source_id / source_event_id | 레지스트리 소스 ID, 원천 행사 키 |
| source_occurrences | 병합 전 발견 출처 목록 |
| title / title_en / title_normalized | 원문 제목 보존 + 비교용 정규화 |
| event_type / event_status | 허용 유형 상수 / UPCOMING·ONGOING·ENDED |
| start_date / end_date / date_text | ISO 날짜 + 원문 기간 문자열 |
| venue_* / city / region / country | 장소·지역 |
| host_organizations | 주최 |
| organizer_organizations | 주관 |
| operator_organizations | 운영·사무국 |
| pco_organizations | 명시된 PCO만 |
| official_event_url / source_url | 공식 홈페이지 / 수집 원문 |
| contact_* | 공개 연락처만 |
| sales_signal_types / qrpick_service_matches / suggested_sales_action | 보수적 영업 신호 |
| needs_official_verification | 역할·연락처 불확실 시 true |
| duplicate_group_id / duplicate_count | 중복 그룹 |
| collected_at / raw_file | 추적 |

없는 값: 문자열·숫자 `null`, 목록 `[]`.

## 기관 역할

역할을 섞지 않는다. 원문이 주최/주관/운영을 구분하지 않으면 임의 추정하지 않고 `needs_official_verification=true`로 둔다.  
기관명 비교 시에만 `(주)`, 주식회사, 재단법인 등을 완화한다(원문은 유지).

## 연락처 정책

- 공개 페이지·공개 API에 있는 값만 저장
- 이메일 패턴 추정·이름 기반 생성 금지
- 저장 시 `contact_source_url` + `collected_at` 필수
- `contact_confidence`: `VERIFIED_PUBLIC_EVENT_PAGE` · `VERIFIED_PUBLIC_OFFICIAL_SOURCE` · `DEPARTMENT_ONLY` · `GENERAL_CONTACT` · `UNKNOWN`

## 영업 신호 / 적용 가능성

| 필드 | 역할 |
|---|---|
| `qrpick_service_matches` | 행사 유형 기반 잠재 QRPick 기능 (영업 확정 아님) |
| `sales_signal_types` | 원문·구조화 필드에서 확인된 영업 단서만 |
| `sales_signal_basis` | 단서 근거 (registration_url, contact_email, procurement_notice 등) |
| `sales_readiness` | DIRECT_OPPORTUNITY · CONTACTABLE · RESEARCH · WATCH · NONE |

`sales_signal_types`에 행사 유형만으로 값을 넣지 않는다. 모든 행사에 ORGANIZER_OUTREACH를 자동 부여하지 않는다.
홈페이지만으로 CONTACTABLE로 판정하지 않는다.

## 중복 정책

확정 병합만 자동 수행:

1. 공식 행사 URL 동일
2. source_id + source_event_id 동일
3. title_normalized + start_date + venue_normalized 동일

후보 중복(제목+시작일만 같음, 연도·회차 상이 등)은 `duplicates.jsonl`에 `CANDIDATE`로 기록하고 병합하지 않는다.  
제목 유사도만으로 병합하지 않는다.

## 원 출처 정책

- 수집 원본 JSONL은 수정하지 않음
- `source_occurrences`에 모든 발견 소스 보존
- 공개 포털·공개 HTML form·문서화된 OpenAPI만 사용
- 로그인·CAPTCHA·robots 충돌 경로 사용 금지
