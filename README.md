# QRPick Opportunity Pipeline

공공·민간의 MICE·행사 관련 사업 및 조달 기회를 수집하고, QRPick·쇼다의 직접입찰·파트너 공급·낙찰사 영업 가능성을 우선순위화하여, 사람이 매주 실행할 상위 영업기회를 제공하는 **내부 매출지원 시스템**입니다.

이 저장소는 범용 조달 AI SaaS, 자동 입찰 시스템, CRM, 제안서 생성기 또는 대규모 웹 대시보드가 아닙니다. 자동 판정은 검토 순서를 만들 뿐이며 상세·첨부가 검증되지 않은 후보를 `GO` 또는 `ACTION_NOW`로 확정하지 않습니다.

## 제품 상태

- 제품 정의와 MVP 범위는 동결되었습니다.
- 신규 수집기, AI API, 첨부/RFP 파싱, OCR, 자동 이메일, 웹 UI, CRM 개발은 중단합니다.
- 허용되는 변경은 운영 중 발견된 데이터 손실·보안·오분류·재현성·테스트 결함 수정과 공식 소스의 불가피한 구조 변경 대응입니다.
- `skills/ir-search/`는 upstream 권위 영역이며 수정하지 않습니다.

정본 읽기 순서:

1. [`docs/product/QRPick_OPPORTUNITY_PIPELINE_PRD.md`](docs/product/QRPick_OPPORTUNITY_PIPELINE_PRD.md)
2. [`docs/product/MVP_SCOPE_AND_STOP_RULES.md`](docs/product/MVP_SCOPE_AND_STOP_RULES.md)
3. [`docs/product/OPPORTUNITY_OPERATING_PLAYBOOK.md`](docs/product/OPPORTUNITY_OPERATING_PLAYBOOK.md)
4. [`docs/product/DOCUMENT_CANONICAL_INDEX.md`](docs/product/DOCUMENT_CANONICAL_INDEX.md)
5. 도메인별 스키마·운영 가이드

## 현재 구현

- 공개 지원사업 수집과 Phase-2 정규화·보수적 중복 제거·규칙 기반 1차 분류
- 공개 MICE 행사 수집·정규화·영업신호 추출
- G2B 사전규격·입찰·낙찰·계약 수집과 생애주기 연결
- 직접입찰·컨소시엄·솔루션 파트너·낙찰사 영업 경로
- 근거, 미확인 사항, 부분성공 상태, 권장 다음 행동
- G2B 사전규격 운영자 Top 30과 전체 273개 후보 원장
- 날짜별 raw/normalized/report 산출물과 실행 manifest
- Windows 배치 실행과 `unittest` 회귀 테스트

현재 제품 부합성은 **부분 구현**입니다. G2B 사전규격 Top 30은 구현되었지만 일반 공고·행사·입찰·낙찰사 영업을 하나로 합친 제품 전체 Top 30, 담당자·처리상태를 유지하는 CRM형 행동 큐, 통합 end-to-end manifest는 구현하지 않았습니다. 이 항목들은 운영 검증 없이 신규 개발하지 않습니다.

## 운영자 기본 흐름

매주 다음 순서로 운영합니다.

`수집 → Top 30 확인 → Top 10 상세검토 → Top 3~5 행동 → 결과 기록`

기본 운영 파일:

- `reports/YYYY-MM-DD/g2b-pre-notice-top30.csv`: 운영자 기본 출력 30건
- `reports/YYYY-MM-DD/g2b-pre-notice-all-candidates.csv`: 전체 영업 후보 원장
- `data/normalized/procurement/YYYY-MM-DD/procurements.jsonl`: 전체 조달 데이터 원장

직접입찰 표시는 입찰 가능 확정이 아니라 **직접입찰 상세검토 경로**입니다. `primary_opportunity_route`는 우선 검토 경로이며 `secondary_opportunity_routes`는 함께 가능한 경로를 보존합니다.

## 실행

최초 준비:

```bat
cd C:\git_hub\work\qrpick-opportunity-pipeline
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

지원사업 Phase-2:

```bat
scripts\test_all_sources_collect.bat
scripts\run_phase2_pipeline.bat
```

MICE 행사:

```bat
scripts\run_mice_mvp.bat
```

G2B 조달:

```bat
set DATA_GO_KR_SERVICE_KEY=발급키
scripts\run_g2b_mice_mvp.bat
```

테스트:

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

API 키는 환경변수로만 주입하며 코드·문서·로그·manifest·커밋에 기록하지 않습니다.

## 데이터 계층

- `data/raw/`: 공개 원문의 날짜별 원장. 수정하지 않습니다.
- `data/normalized/`: 정규화 대표 레코드, 중복 근거, 오류, 통계.
- `reports/`: 사람이 읽는 Top 30, 전체 후보, 상태·경로별 CSV와 요약.
- `config/`: 실행 정책과 규칙.
- `app/`: QRPick 운영 코드.
- `scripts/`: Windows 배치 진입점.
- `skills/ir-search/`: upstream 수집 스킬. 수정 금지.

CSV는 Excel 한글 호환을 위해 UTF-8 BOM으로 생성합니다.

## 판정 원칙

- 규칙 기반 결과는 지원·입찰 가능 여부의 확정이 아닙니다.
- MICE 관련성, 영업 경로, 실행 대기열을 분리합니다.
- 목록 정보만으로 자격·예산·역할을 추정하지 않습니다.
- 없는 연락처를 생성하지 않고 공개 출처와 근거를 보존합니다.
- 실패한 소스가 있어도 가능한 범위는 처리하되 `PARTIAL_EXPECTED`, `PARTIAL_UNEXPECTED`, `FAILED`, truncation과 인증 부재를 명시합니다.
- 불확실한 중복은 합치지 않고 후보 관계로 남깁니다.

## 라이선스와 경계

upstream `ir-search` 플러그인의 라이선스는 루트 `LICENSE`를 따릅니다. QRPick 실제 서비스 저장소, 고객 데이터, CRM과 연결하지 않는 독립 로컬 운영체계입니다.
