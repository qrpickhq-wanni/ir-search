# Phase-2 정규화·1차 필터 정책

문서 목적: QRPick opportunity pipeline 2단계(정규화·보수적 중복·룰 기반 1차 선별)의
판단 기준을 재현 가능하게 고정한다. 유료 AI/LLM을 사용하지 않는다.

## 표준 스키마

설정: `config/normalization-schema.yaml`

대표 필드:
- 식별: `opportunity_id`, `canonical_id`, `source`, `source_id`, `source_occurrences`
- 표기: `title`(원문 유지), `title_normalized`(비교용)
- 기관: `organization`(원문), `organization_normalized`(비교용)
- 일정: `application_start`, `deadline`(YYYY-MM-DD 가능 시), `deadline_text`(원문)
- 추적: `url`/`detail_url`, `raw_file`, `collected_at`
- 1차 결과: `first_pass_status`, `first_pass_score`, `positive_reasons`, `negative_reasons`, `review_reasons`, `needs_detail_review`

`raw_record` 전체 복사는 하지 않는다. 없는 값은 `null` 또는 빈 배열이다.

소스별 입력 매핑:
- K-Startup: `pbancSn`→source_id, `org`, `start`/`deadline`, `category`, `agency_type`, `program`
- bizinfo/nipa/kocca/smtech: `id`→source_id, `org`, `apply_start`/`apply_end`, `reg_date`→posted_at, `field`→category/program

## 중복 정책

보수적. 불확실하면 별도 공고로 유지.

자동 병합(확정):
1. 동일 `source` + `source_id`
2. `title_normalized` + `organization_normalized` + `deadline` 전부 일치

후보만 기록(자동 병합 금지):
3. 제목 정규화 일치 + (기관 또는 마감 일치) — `duplicates.jsonl`에 `candidate_duplicate`

금지:
- 제목 유사도(fuzzy)만으로 병합
- 기관·마감이 다르면 병합하지 않음
- 연도·회차·지역이 다른 공고 병합

병합 시 가장 정보가 많은 레코드를 대표로 두고, 빈 필드만 보완한다.
충돌 값은 덮어쓰지 않고 `duplicates.jsonl`의 `conflicts`에 남긴다.

## 판정 최상위 질문

QRPick **기존 기능 일치**만 보지 않는다.

> QRPick 또는 쇼다의 기술·운영·기획·개발·마케팅 자산과 대표자 수행경력을 활용하여
> 직접 공급, 확장 개발, 신규 구축용역, 운영용역, 공동수행 또는 영업기회로 전환할 수 있는가?

모든 대표 공고에 `asset_fit_path`를 부여한다:
`QRPICK_DIRECT` | `QRPICK_EXTENSION` | `SHOWDA_ASSET_REUSE` | `CUSTOM_BUILD_SERVICE` | `PARTNER_CONSORTIUM` | `SALES_LEAD` | `NO_REALISTIC_PATH`

결과 CSV/JSONL에는 경로·활용 가능 QRPick 기능·쇼다 자산·신규개발·파트너·기회유형·다음행동도 함께 기록한다.

산업명(바이오·반도체 등)만으로 제외하지 않는다. 과업이 행사·등록·매칭·플랫폼·웹·데이터·마케팅·운영이면 최소 DETAIL_REVIEW 이상이다.
강한 저적합은 전문산업 산출물 + SW/운영역할 부재 + 구축경로 없음 + 파트너·영업 경로 약함이 **모두** 성립할 때만 적용한다.

## 점수 정책


설정: `config/filter-rules.yaml`  
점수는 **0~100**, 기본 **30**. 검토 순서용이며 지원 가능 여부가 아니다.

가점(요약):
- core_mice: +8/키워드, 최대 +32
- tourism_extension: +6/키워드, 최대 +24 (제목·프로그램·카테고리만 — 기관명의 ‘관광’ 오탐 방지)
- technology: +4/키워드, 최대 +16 (짧은 영문 AI/DX 등은 단어 경계 매칭)
- program_value: +7/키워드, 최대 +21
- export_market: +5/키워드, 최대 +10
- 고가치 그룹 2개 결합 +18 / 3개 결합 +28

감점(요약):
- 교육생·개인참가 중심 −25
- 입주공간만 −20
- 멘토링·컨설팅만 −12
- 강한 산업 전용 −35 (단독 단어 즉시 제외 금지, 배타 맥락·산업특화 결합 시)
- 예비창업자만 / 대학생만 −40

약한 단독어(`행사`, `콘텐츠`, `교육` 등)만으로는 core 가점을 주지 않는다.

## 상태 판정 정책

설정: `config/status-codes.yaml`

| 상태 | 의미 |
|------|------|
| HIGH_PRIORITY | QRPick 코어·확장과 직접 연관 신호 결합이 강해 상세검토 우선 |
| REVIEW | 연관 가능, 지원형태·효익 추가 검토 |
| DETAIL_REVIEW | 제목만으로 과제·자격 판단 불가 |
| LOW_FIT | 직접 관련성 낮거나 대상 명확 부적합 |
| EXPIRED | 마감일이 실행일 이전 |
| UNKNOWN | 필수 데이터 부족 |

판정 요지:
- `EXPIRED`는 점수와 별도로 마감 기준
- `HIGH_PRIORITY`: 점수≥70 + 고가치 그룹 ≥2, 또는 코어 MICE+관광 ≥55
- 오픈이노베이션·실증·R&D·사업화이면서 관광/MICE 신호가 없으면 `DETAIL_REVIEW`
- 판로·전시·조달·상담회는 전략적 `REVIEW` 가능 (무조건 LOW_FIT 금지)
- 회사 소재지·업력 TODO → 지역/업력 요건 확정 금지, `review_reasons`에 명시

## 오분류 방지 원칙

1. 자격요건을 목록 제목만으로 확정하지 않는다.
2. 불명확하면 제외하지 않고 DETAIL_REVIEW/VERIFY 성격으로 남긴다.
3. 바이오 등 산업 단어 단독으로 즉시 제외하지 않는다.
4. 특정 공고 제목 하드코딩 예외를 만들지 않는다. 규칙은 YAML/공통 로직으로만 수정한다.
5. 모든 결과에 source·source_id·URL·raw_file 추적을 유지한다.

## 상세검토로 넘기는 기준

- 오픈이노베이션 / PoC / 실증 / R&D / 사업화 / 구매·조달인데 과제 내용·자격 불명
- 회사 프로필 TODO로 지역·업력 판정 불가
- 마감일 파싱 실패
- HIGH_PRIORITY·REVIEW도 최종 GO가 아니며 `needs_detail_review=true`일 수 있음

## 자동 제외 금지 항목

- 단지 “AI”, “콘텐츠”, “행사”만 있다는 이유
- 공공 전시·상담회·참가기업 모집(판로 기회 가능)
- 산업 키워드 단독 출현
- 상세 공고를 읽지 않은 상태의 자격 미달 단정

## 현재 한계

- 목록 메타데이터만 사용. 상세 HTML/첨부 미수집.
- NIPA 등 보드 페이지에 과거 마감 공고가 다수 포함되면 EXPIRED가 커질 수 있음(수집기 동작).
- 동일 사업의 표기 차이가 크면 중복 미탐지 → candidate만 잡히거나 별도 유지.
- 점수는 상대 순위용. 지원 결정에 사용하지 말 것.
- 유료 AI 재랭킹/요약 없음.
