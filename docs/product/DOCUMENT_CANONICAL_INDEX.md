# Document Canonical Index

상태: **CANONICAL**  
기준일: 2026-07-17  
원칙: 문서는 삭제하지 않고 권위·읽기 순서·drift 상태를 표시한다.

## 1. 분류 정의

- **CANONICAL:** 현재 제품·정책·스키마의 기준 문서
- **SUPPORTING:** 정본을 보완하는 구현·운영·외부 참고 문서
- **HISTORICAL:** 당시 조사·실행·의사결정 이력을 보존하는 문서
- **SUPERSEDED:** 내용이 정본에 흡수되었거나 upstream/중복본이라 먼저 읽지 않는 문서
- **REVIEW_REQUIRED:** 현재 코드 또는 정본과 중복·충돌·노후 내용이 있어 그대로 권위로 쓰면 안 되는 문서

## 2. 권위 순서

충돌 시 다음 순서를 따른다.

1. 법률, 공개 API 공식 문서, 서비스 이용약관
2. `AGENTS.md`의 저장소 안전·경계 규칙
3. `docs/product/QRPick_OPPORTUNITY_PIPELINE_PRD.md`
4. `docs/product/MVP_SCOPE_AND_STOP_RULES.md`
5. `docs/product/OPPORTUNITY_OPERATING_PLAYBOOK.md`
6. 도메인 분류·소스 감사 정책
7. 실행 코드와 config
8. 도메인 스키마·운영 가이드
9. historical 문서와 생성 보고서

런타임 필드·허용값·endpoint·threshold는 코드/config가 설명 문서보다 우선한다. 제품 목적·비범위·동결선은 product 정본이 우선한다. 코드와 문서가 다르면 어느 한쪽을 묵시적으로 정답 처리하지 않고 Code-Document Drift로 기록한다.

`skills/ir-search/SKILL.md`는 upstream `ir-search` 동작의 권위이며 이 제품 문서 작업에서 수정하지 않는다.

## 3. 권장 읽기 순서

1. `README.md`
2. `docs/product/QRPick_OPPORTUNITY_PIPELINE_PRD.md`
3. `docs/product/MVP_SCOPE_AND_STOP_RULES.md`
4. `docs/product/OPPORTUNITY_OPERATING_PLAYBOOK.md`
5. `docs/product/DOCUMENT_CANONICAL_INDEX.md`
6. 작업 도메인의 정책·스키마
7. 작업 도메인의 운영 가이드
8. supporting API reference
9. historical 문서

## 4. `docs/` 전체 분류

### CANONICAL

| 경로 | 권위 범위 | 비고 |
|---|---|---|
| `docs/product/QRPick_OPPORTUNITY_PIPELINE_PRD.md` | 제품 정의, 사용자, 요구사항, 범위, 구현 감사 | 제품 최상위 정본 |
| `docs/product/MVP_SCOPE_AND_STOP_RULES.md` | MVP 포함/비범위, 동결·중단·진입 조건 | 신규 기능 판단 정본 |
| `docs/product/OPPORTUNITY_OPERATING_PLAYBOOK.md` | 주간 Top 30→Top 10→Top 3~5 운영 | 운영 정본 |
| `docs/product/DOCUMENT_CANONICAL_INDEX.md` | 문서 권위·분류·읽기 순서 | 현재 문서 |
| `docs/mice-source-audit-policy.md` | 공개 소스 접근, 감사 등급, HOLD 원칙 | source별 사실은 registry 우선 |

### SUPPORTING

| 경로 | 보완 범위 | 주의 |
|---|---|---|
| `docs/phase2-normalization-and-filter-policy.md` | 지원사업 정규화·보수적 중복·규칙 점수 | legacy `asset_fit_path` 체계와 함께 읽음 |
| `docs/mice-event-schema.md` | 행사 provenance·연락·영업신호 스키마 | 필드 권위는 `app/mice_normalizers/schema.py` |
| `docs/g2b-mice-lifecycle-schema.md` | G2B 4단계·인증·link 개요 | 필드/endpoint 권위는 코드와 config |
| `docs/나라장터 API/조달청_OpenAPI참고자료_나라장터_계약정보서비스_1.0.docx` | 계약 API 스냅샷 | 최신 data.go.kr 문서 우선 |
| `docs/나라장터 API/조달청_OpenAPI참고자료_나라장터_입찰공고정보서비스_1.2.docx` | 입찰 API 스냅샷 | 최신 data.go.kr 문서 우선 |
| `docs/나라장터 API/조달청_OpenAPI참고자료_나라장터_낙찰정보서비스_1.1.docx` | 낙찰 API 스냅샷 | 최신 data.go.kr 문서 우선 |
| `docs/나라장터 API/조달청_OpenAPI참고자료_나라장터_사전규격정보서비스_1.0.docx` | 사전규격 API 스냅샷 | 최신 data.go.kr 문서 우선 |

### HISTORICAL

| 경로 | 보존 이유 | 현재 사용 |
|---|---|---|
| `docs/mice-source-feasibility-audit.md` | 2026-07-15 기존 3개 소스 감사 | 당시 근거 확인용 |
| `docs/mice-source-landscape.md` | 2026-07-15 38개 소스 탐색·우선순위 | 신규 collector backlog로 사용 금지 |

### SUPERSEDED

| 경로 | 이유 | 대체 권위 |
|---|---|---|
| `docs/upstream-ir-search-README.md` | vendored upstream 소개이며 QRPick 제품 정본 아님 | `skills/ir-search/SKILL.md`, 루트 README |
| `docs/나라장터 API/조달청_OpenAPI참고자료_나라장터_입찰공고정보서비스_1.2 (1).docx` | 동일 버전 파일의 중복본으로 보임 | `(1)` 없는 파일. 삭제 전 binary 비교 필요 |

### REVIEW_REQUIRED

| 경로 | 충돌·노후 내용 | 검토 방향 |
|---|---|---|
| `docs/qrpick-opportunity-classification-principles.md` | “나라장터 전용 collector 미구현” 문장이 현재 G2B 구현과 충돌 | gate 원칙은 유효, 구현 현황 문장 갱신 필요 |
| `docs/mice-mvp-operation-guide.md` | report filter에 `DIRECT`를 사용하나 코드·문서 enum은 `DIRECT_OPPORTUNITY`; 확장 안내가 동결선과 충돌 | 운영 사실만 유지하고 신규 소스 안내에 동결 주석 필요 |
| `docs/g2b-mice-sales-operation-guide.md` | 새 pre-notice Top 30/all-candidates, priority 체계가 빠짐; registry promotion 문장이 노후 가능 | product playbook과 현재 보고서 기준으로 갱신 필요 |

## 5. 루트·정책 인접 문서

| 경로 | 분류 | 역할·주의 |
|---|---|---|
| `README.md` | CANONICAL | 제품 입구와 실행 요약 |
| `AGENTS.md` | CANONICAL | 저장소 경계·윤리·분류 상설 원칙 |
| `.cursor/rules/qrpick-opportunity-classification.mdc` | CANONICAL | 에이전트 적용 분류 gate |
| `README.en.md` | SUPERSEDED | upstream 영문 README이며 현재 제품 소개가 아님 |
| `SKILL.md` | SUPPORTING | upstream skill compatibility pointer |
| `ir-search-profile.md` | REVIEW_REQUIRED | TODO 자격 필드가 있어 공식 자격판정에 사용 금지 |
| `config/mice-source-registry.yaml` | CANONICAL DATA | source별 구현·감사 사실의 데이터 권위 |
| `reports/mice-source-audit.csv` | DERIVED | registry에서 생성되는 파생물, 수동 편집 금지 |

## 6. 코드·문서 Drift 목록

1. 분류 원칙 문서의 “G2B collector 미구현” 문장과 현재 collector 코드가 충돌한다.
2. MICE 운영 가이드의 `DIRECT`와 실제 `DIRECT_OPPORTUNITY` enum이 다르다.
3. G2B 운영 가이드에 pre-notice priority, Top 30, 273 all-candidates가 없다.
4. 루트 `README.en.md`는 현재 제품의 영문 README로 오해될 수 있다.
5. source registry에서 구현 상태가 변경되어도 historical landscape와 생성 audit CSV는 자동으로 최신 정본이 되지 않는다.
6. 문서의 통합 제품 그림과 달리 현재 Top 30은 G2B 사전규격에 한정된다.

이번 작업에서는 요구된 5개 정본 문서만 생성·정리하며 기존 문서를 삭제하거나 drift 문장을 직접 수정하지 않는다.

## 7. 문서 변경 규칙

- 제품 목적·MVP 범위를 바꾸려면 PRD와 Stop Rules를 함께 갱신한다.
- 운영 절차 변경은 Playbook과 README를 함께 갱신한다.
- 새 문서를 만들기 전에 이 index에서 기존 권위와 중복 여부를 확인한다.
- historical 문서의 과거 수치·판단을 현재형으로 고치지 않는다.
- binary API reference는 원본 보존하며 중복 삭제는 별도 승인과 hash 비교 후 수행한다.
- 문서만으로 런타임 허용값을 변경하지 않는다.
