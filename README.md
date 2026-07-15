# QRPick Opportunity Pipeline

주식회사 쇼다의 **QRPick** 전용 정부지원사업·실증·오픈이노베이션 공고 수집 및 제안 대응 운영체계(로컬 Python 자동화)입니다.

기반은 오픈소스 [ir-search](skills/ir-search/SKILL.md) 스킬의 검증된 공개 페이지 크롤러이며, 원본 수집기 코드는 수정하지 않고 **날짜별 저장·로그·배치·프로필·폴더 구조**만 이 저장소에서 운영합니다.

원본 ir-search 플러그인 설명은 [`docs/upstream-ir-search-README.md`](docs/upstream-ir-search-README.md) 및 [`README.en.md`](README.en.md)를 참고하세요.

## 프로젝트 목적

- K-Startup·기업마당·NIPA·KOCCA·SMTECH 등 공개 공고를 주기적으로 수집한다.
- 수집 원본은 `data/raw/YYYY-MM-DD/`에 날짜별로 보관하고 수정하지 않는다.
- 이후 단계에서 정규화·QRPick 적합성 평가·제안 대응으로 확장한다.
- QRPick 실제 서비스 저장소와는 연결하지 않는다 (독립 로컬 운영체계).

## 현재 구축 범위

### 1단계 — 수집 기반환경

- Python `.venv` + `requirements.txt` (`curl_cffi>=0.15`, `PyYAML`)
- 운영 폴더 구조, `ir-search-profile.md`, 수집 배치/로그

### 2단계 — 정규화·보수적 중복·룰 기반 1차 필터 (이번 단계)

목적: 원본 JSONL을 QRPick 표준 레코드로 정규화하고, 보수적으로 중복을 묶은 뒤,
유료 AI 없이 설명 가능한 규칙으로 검토 후보를 선별한다.

포함:
- `config/qrpick-profile.yaml`, `normalization-schema.yaml`, `filter-rules.yaml`, `status-codes.yaml`
- `app/normalizers/*`, `app/evaluators/*`
- `app/run_normalize.py`, `app/run_first_pass.py`, `app/run_summary.py`, `app/run_phase2.py`
- `scripts/run_phase2_pipeline.bat`
- `tests/test_*.py`
- 정책 문서: [`docs/phase2-normalization-and-filter-policy.md`](docs/phase2-normalization-and-filter-policy.md)

아직 포함하지 않음:
- 웹 대시보드, SQLite, LLM/유료 AI API
- 상세공고·첨부 전수 다운로드
- 관광기관·컨벤션뷰로 신규 크롤러(구현 전)
- 자동 이메일·제안서 작성·최종 GO/NO-GO·자동 제출

### MICE 소스 레지스트리 (크롤러 미구현)

- **기준 데이터(source of truth):** [`config/mice-source-registry.yaml`](config/mice-source-registry.yaml)
- **생성 산출물:** [`reports/mice-source-audit.csv`](reports/mice-source-audit.csv) — YAML을 읽어 검증·생성하며 수동 편집하지 않는다.
- 검증·CSV 생성: `python scripts/build_mice_source_registry.py`
- 지도·정책: [`docs/mice-source-landscape.md`](docs/mice-source-landscape.md), [`docs/mice-source-audit-policy.md`](docs/mice-source-audit-policy.md)

## 실행 방법

### 최초 준비

```bat
cd C:\git_hub\work\qrpick-opportunity-pipeline
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 1단계 수집 테스트

```bat
scripts\test_kstartup_collect.bat
scripts\test_all_sources_collect.bat
```

### 2단계 정규화·1차 필터

```bat
scripts\run_phase2_pipeline.bat
```

또는:

```bat
.venv\Scripts\python.exe app\run_phase2.py --raw-dir data\raw\2026-07-15 --today 2026-07-15
```

입력은 `data/raw` 아래 가장 최근 `YYYY-MM-DD` 폴더의 `kstartup_all.jsonl` + `sources_all.jsonl`이다.
원본 JSONL은 읽기 전용이며 수정하지 않는다.

### 단위 테스트

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 생성되는 파일 위치

| 종류 | 경로 |
|------|------|
| K-Startup 원본 | `data/raw/YYYY-MM-DD/kstartup_all.jsonl` |
| 통합 소스 원본 | `data/raw/YYYY-MM-DD/sources_all.jsonl` |
| 정규화 대표 공고 | `data/normalized/YYYY-MM-DD/opportunities.jsonl` |
| 중복 로그 | `data/normalized/YYYY-MM-DD/duplicates.jsonl` |
| 정규화 오류 | `data/normalized/YYYY-MM-DD/normalization_errors.jsonl` |
| 요약 보고서 | `reports/YYYY-MM-DD/collection-summary.md` |
| 후보 CSV (HIGH/REVIEW/DETAIL) | `reports/YYYY-MM-DD/candidate-list.csv` |
| 상태별 CSV | `high-priority-list.csv`, `review-list.csv`, `needs-detail-review.csv`, `low-fit-list.csv` |
| Phase-2 로그 | `logs/YYYY-MM-DD_phase2.log` |

CSV는 Excel 한글 호환을 위해 **UTF-8 BOM(`utf-8-sig`)** 으로 저장한다.

## 상태코드와 점수의 의미

| 상태 | 의미 |
|------|------|
| HIGH_PRIORITY | QRPick 코어·확장과 직접 연관 신호가 강해 상세검토 우선 (지원 확정 아님) |
| REVIEW | 연관 가능, 지원형태·효익 추가 검토 |
| DETAIL_REVIEW | 제목만으로 과제·자격 판단 불가 |
| LOW_FIT | 직접 관련성 낮음 또는 대상 명확 부적합 |
| EXPIRED | 마감 종료 |
| UNKNOWN | 데이터 부족 |

점수는 **검토 순서용(0~100)** 이며 지원 가능 여부가 아니다.
상세 정책은 `docs/phase2-normalization-and-filter-policy.md`를 본다.

## 중복 제거 방식

- 자동 병합: 동일 source+source_id, 또는 정규화 제목+기관+마감 완전 일치
- 후보만 기록: 제목 일치 + (기관 또는 마감) — fuzzy 병합 없음
- 불확실하면 별도 공고로 유지

## 자동 필터의 한계 / 회사 TODO 영향

- 목록 메타데이터만 사용한다. 자격·예산·지역제한은 확정하지 않는다.
- `headquarters_region`·업력이 TODO이면 지역/업력 요건을 판정하지 않고 `DETAIL_REVIEW`/`review_reasons`에 남긴다.
- NIPA 등에서 과거 마감 공고가 섞이면 EXPIRED가 커질 수 있다.
- 따라서 **다음 단계에서는 HIGH/REVIEW/DETAIL 후보의 상세공고를 반드시 검증**해야 한다.

### 1단계 실행 검증 메모 (2026-07-15)

- K-Startup: **성공** 217건
- sources `list all`: **성공** 825건 (bizinfo 450 · nipa 300 · kocca 16 · smtech 59)

### 2단계 실행 검증 메모 (행동 대기열 분리 후, 2026-07-15)

- 입력 1,042 / 대표 1,041 / 오류 0 / 자동병합 1
- **action_queue**: ACTION_NOW **5** · QUALIFICATION_CHECK **38** · SALES_OUTREACH **108** · WATCHLIST **52** · NO_ACTION **511** · CLOSED **327**
- **primary_asset_fit_path**: SHOWDA_ASSET_REUSE **29** ← 이전 787에서 감소 · NO_REALISTIC_PATH 819 · SALES_LEAD 116 · CUSTOM_BUILD 55 · EXTENSION 7 · DIRECT 1 · PARTNER 14
- 즉시 사람 손길 필요한 작업열(ACTION_NOW+QUAL+SALES) ≈ **151건** (유효 714 대비 운영 가능)
- 회사 프로필: 설립 2021-02-14·서울·대표 신석원 (`INTERNAL_COMPANY_PROFILE_ONLY`)
- 추적 무결성 PASS (1042)
- 대기열 CSV: `reports/2026-07-15/action-now.csv` 등

## 원본 ir-search 코드와 QRPick 맞춤 코드의 경계

| 구분 | 경로 | 수정 정책 |
|------|------|-----------|
| 원본 수집기·스킬 | `skills/ir-search/` | **수정하지 않음** |
| QRPick 운영 코드 | `scripts/`, `config/`, `app/`, `tests/`, `docs/` | 이 저장소에서 관리 |
| 원본·로그 산출물 | `data/raw`, `logs/` | 원본 JSONL은 수정하지 않음 |
| QRPick 서비스 저장소 | (외부) | **연결·수정하지 않음** |

## 다음 단계

1. 프로필 TODO(업력·소재지) 확정
2. HIGH/REVIEW/DETAIL 후보 상세공고 선택 수집·자격 체크리스트
3. 사람 검토 워크플로(스프레드시트/노션) 정착
4. (이후) 대시보드·제안 파이프라인·추가 관광기관 소스

## 라이선스

업스트림 ir-search 플러그인 라이선스는 루트 `LICENSE`를 따릅니다.
