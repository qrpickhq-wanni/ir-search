# QRPick Opportunity Pipeline

> 공공·민간 MICE·행사 기회를 수집·우선순위화해 사람이 매주 실행할 영업기회를 제공하는 내부 매출지원 시스템

이 저장소는 범용 조달 AI SaaS, 자동 입찰 시스템, CRM, 제안서 생성기 또는 대규모 웹 대시보드가 아닙니다. 자동 판정은 검토 순서를 만들 뿐이며 상세·첨부가 검증되지 않은 후보를 `GO` 또는 `ACTION_NOW`로 확정하지 않습니다.

## 원본 프로젝트와 QRPick 맞춤 제품 범위

이 저장소는 MIT License로 공개된 `ir-search`의 수집 기능을 기반으로,
주식회사 쇼다와 QRPick의 사업·입찰·영업기회를 선별하기 위한
내부 매출지원 파이프라인으로 확장한 프로젝트입니다.

`skills/ir-search`는 원본 공개 수집기 영역으로 유지합니다.
QRPick 맞춤 정규화·분류·조달 생애주기·영업경로·통합 Top 30 기능은
별도의 `app/`, `config/`, `tests/`, `docs/` 영역에서 구현합니다.

### 데이터 출처 범위

1. 지원사업·실증 공고
   - K-Startup, 기업마당, NIPA, KOCCA, SMTECH 등

2. MICE 행사·기관 정보
   - 전시컨벤션센터
   - 컨벤션뷰로·관광기관
   - 협회·학회
   - 국가 MICE 플랫폼
   - 수출·상담회 운영기관
   - 민간 행사·전시 플랫폼

3. 나라장터 조달 생애주기
   - 사전규격정보
   - 입찰공고정보
   - 낙찰정보
   - 계약정보

4. 민간·상업 영업기회
   - 행사기획사·PCO
   - 민간 주최사
   - 호텔·리조트
   - 기업행사
   - 지역관광·콘텐츠 사업자

5. 내부·수동 입력 데이터
   - 기존 고객
   - 파트너·인맥
   - 상담·견적 이력
   - 과거 행사
   - 수동 발견 기회

현재 자동 수집이 구현되지 않은 출처도 제품의 데이터 범위에는 포함될 수 있지만,
구현 완료로 표현하지 않습니다. 실제 구현 상태는 아래 현재 상태와 PRD 매핑을 따릅니다.
특히 민간·상업 영업기회와 내부 데이터는 현재 자동 수집 완료 상태가 아니며,
입찰·낙찰·계약 입력이 smoke 표본인 실행은 전수 데이터로 해석하지 않습니다.

기본 사용자 출력은 전체 수집 데이터가 아니라
QRPick·쇼다 관점에서 우선 검토할 통합 Top 30입니다.

자동 분류는 지원·입찰 가능 여부를 확정하지 않습니다.
사람이 직접입찰 검토, 파트너 공급, 낙찰사 영업 등
다음 행동을 선택하도록 돕는 규칙·시나리오 기반 1차 선별 도구입니다.

### 라이선스와 원본 유지 원칙

- 원본 `ir-search`의 MIT License와 저작권 고지를 유지합니다.
- `skills/ir-search`는 원본 공개 수집기 영역으로 취급합니다.
- QRPick 맞춤 확장 기능은 원본 영역 밖에서 구현합니다.
- 원본 공개 프로젝트와 QRPick 내부 제품의 기능 범위를 혼동하지 않습니다.

## 제품 상태

- 제품 정의와 MVP 범위는 동결되었습니다.
- 신규 수집기, AI API, 첨부/RFP 파싱, OCR, 자동 이메일, 웹 UI, CRM 개발은 중단합니다.
- 허용되는 변경은 운영 중 발견된 데이터 손실·보안·오분류·재현성·테스트 결함 수정과 공식 소스의 불가피한 구조 변경 대응입니다.

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
- 지원사업·MICE 행사·G2B 생애주기를 공통축으로 재평가한 제품 전체 Top 30과 통합 원장
- 날짜별 raw/normalized/report 산출물과 실행 manifest
- Windows 배치 실행과 `unittest` 회귀 테스트

제품 전체 통합 Top 30까지 기능 기반 MVP가 구현되었습니다. 담당자·처리상태를 유지하는 CRM형 행동 큐와 자동 실행은 구현하지 않으며 운영 검증 없이 확장하지 않습니다.

## 운영자 기본 흐름

매주 다음 순서로 운영합니다.

`수집 → Top 30 확인 → Top 10 상세검토 → Top 3~5 행동 → 결과 기록`

기본 운영 파일:

- `reports/YYYY-MM-DD/unified-opportunity-top30.csv`: 제품 전체 운영자 기본 출력 30건
- `reports/YYYY-MM-DD/unified-opportunity-all.csv`: NO_ACTION을 포함한 통합 원장 CSV
- `data/normalized/YYYY-MM-DD/unified-opportunities.jsonl`: 통합 JSONL 원장
- 도메인별 기존 원장과 G2B 사전규격 Top 30은 감사·세부검토용으로 유지

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

제품 전체 통합 출력:

```bat
scripts\run_unified_output.bat --run-day YYYY-MM-DD
```

서로 다른 날짜·실험 폴더의 원장을 결합할 때는 `--support`, `--mice`, 반복 가능한
`--procurement` 인자로 입력 파일을 명시합니다. 통합 점수는 도메인 원점수를 사용하지 않습니다.

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

라이선스 전문과 저작권 고지는 루트 `LICENSE`를 따릅니다. QRPick 실제 서비스 저장소,
고객 데이터, CRM과 연결하지 않는 독립 로컬 운영체계입니다.
