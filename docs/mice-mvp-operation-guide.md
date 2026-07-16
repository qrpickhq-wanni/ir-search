# MICE MVP 운영 가이드 (1B-1A)

## 실행 방법

```bat
cd C:\git_hub\work\qrpick-opportunity-pipeline
.venv\Scripts\activate
scripts\run_mice_mvp.bat
```

또는:

```bat
.venv\Scripts\python.exe app\run_mice_mvp.py
```

단계별:

```bat
.venv\Scripts\python.exe app\run_mice_collect.py
.venv\Scripts\python.exe app\run_mice_normalize.py
.venv\Scripts\python.exe app\run_mice_summary.py
.venv\Scripts\python.exe -m unittest discover -s tests -p test_mice_*.py -v
```

KINTEX만 재수집:

```bat
.venv\Scripts\python.exe app\run_mice_collect.py --sources opendata_kintex_gg
.venv\Scripts\python.exe app\run_mice_normalize.py
.venv\Scripts\python.exe app\run_mice_summary.py
```

## 환경변수

| 변수 | 용도 | 필수 |
|---|---|---|
| `SONGDO_OPENAPI_KEY` | 송도컨벤시아 OpenAPI serviceKey | 선택(문서상 권장). 미설정 시 비인증 호출 가능 |
| `GG_OPENAPI_KEY` | 경기데이터드림 OpenAPI 인증키 | KINTEX 오픈데이터 행 수집에 필요 |
| `GG_KINTEX_OPENAPI_SERVICE` | Sheet Open API 팝업의 서비스명 | KINTEX 오픈데이터 행 수집에 필요 |

발급:

1. https://data.gg.go.kr/portal/openapi/insertApikeyPage.do 에서 키 발급
2. KINTEX 데이터셋 Sheet 화면의 **Open API**에서 서비스명을 확인 후 `GG_KINTEX_OPENAPI_SERVICE`에 설정
3. **키·서비스명을 코드·문서·커밋에 기록하지 말 것**

키가 없으면 `opendata_kintex_gg`는 **PARTIAL(0건)** 로 남긴다. 실패로 과장하지 않는다.

## 적용 가능성 vs 영업신호

| 필드 | 의미 |
|---|---|
| `qrpick_service_matches` | 행사 유형 기반 **잠재** QRPick 적용 가능성 |
| `sales_signal_types` | 원문/구조화 필드에서 **확인된** 영업 단서만 |
| `sales_signal_basis` | 단서가 발견된 근거 필드 목록 |
| `sales_readiness` | DIRECT_OPPORTUNITY / CONTACTABLE / RESEARCH / WATCH / NONE |

금지: 행사 유형만으로 `sales_signal_types` 부여, 모든 행사에 `ORGANIZER_OUTREACH`, 홈페이지만으로 CONTACTABLE, 연락처 추정.

## 입력·출력 경로

정책: `config/mice-collection-policy.yaml`  
레지스트리: `config/mice-source-registry.yaml`

원본:

- `data/raw/mice/YYYY-MM-DD/{source_id}.jsonl`
- `data/raw/mice/YYYY-MM-DD/collection_errors.jsonl`
- `data/raw/mice/YYYY-MM-DD/collection_manifest.json`

정규화:

- `data/normalized/mice/YYYY-MM-DD/events.jsonl`
- `data/normalized/mice/YYYY-MM-DD/duplicates.jsonl`
- `data/normalized/mice/YYYY-MM-DD/normalization_errors.jsonl`

보고서(UTF-8 BOM CSV):

- `mice-events.csv` — 전체 대표 행사 + 적용 가능성
- `mice-sales-signals.csv` — readiness∈{DIRECT,CONTACTABLE,RESEARCH} **그리고** basis 비어 있지 않음
- `mice-contact-presence.csv` — 공개 업무 연락처 또는 공식 문의 경로(출처 URL 필수)
- `mice-collection-summary.md`

로그: `logs/YYYY-MM-DD_mice_mvp.log`

## 소스별 제약

### opendata_kintex_gg

- data.go.kr는 GG Sheet URL만 연결 (첨부 CSV blob 없음)
- HTTP 전용 수집기는 OpenAPI env 필요
- 키 없으면 PARTIAL 유지

### songdo_convenia

- 문서화 파라미터: `resultType`, `stdate`, `eddate` 만 (`/page/openApiEvent.do`)
- 응답 키: `resultCode`, `resultMessage`, `itemList` — **totalCount/page\* 없음**
- 관측: 호출당 `itemList` 최대 **10건** (페이지네이션 파라미터 문서·응답에 없음 → 추정 금지)
- 대응: 문서화된 날짜 구간을 월 단위·필요 시 이분 분할로 재조회해 중복 제거
- `collection_manifest.metadata.completeness`에 판정 기록
  - `IMPROVED_VIA_DATE_SPLIT` / `COMPLETE_*` / `PARTIAL_DAY_CAP`
- 단일 wide window 10건은 **불완전**할 수 있음 (월 분할로 더 복구)

### k_mice

- `POST` `curr_page` + `calView` + `miceCalendarDTO.YEAR`/`MONTH`
- robots `/*search*` 미사용
- 날짜 창 밖 행사는 정규화에서 `outside_date_window`로 제외 (오류 로그)

## 오류 처리

- 소스 하나 실패해도 다른 소스 계속
- `outside_date_window`: 필터(날짜 파싱 실패와 구분)
- 제목 유효 + 날짜 파싱 실패: 행사 보존, dates=null, `needs_official_verification=true`
- 종료코드: `0` 전부 OK / `2` 일부 PARTIAL·실패 / `1` 전체·테스트 실패

## 결과 파일 활용

1. `mice-events.csv` — 전체·적용 가능성
2. `mice-sales-signals.csv` — 근거 있는 영업 후보만
3. `mice-contact-presence.csv` — 연락·문의 경로
4. `duplicates.jsonl`의 `CANDIDATE` 수동 확인

## 다음 소스 추가 방법

1. registry 등록 → collector → runner 맵 → policy 메모 → 테스트·실수집

브라우저 자동화·비공개 API·로그인 우회는 사용하지 않는다.
탐색용 `scripts/_probe_*.py`는 사용하지 않으며 저장소에 두지 않는다.
