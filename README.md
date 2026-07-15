# QRPick Opportunity Pipeline

주식회사 쇼다의 **QRPick** 전용 정부지원사업·실증·오픈이노베이션 공고 수집 및 제안 대응 운영체계(로컬 Python 자동화)입니다.

기반은 오픈소스 [ir-search](skills/ir-search/SKILL.md) 스킬의 검증된 공개 페이지 크롤러이며, 원본 수집기 코드는 수정하지 않고 **날짜별 저장·로그·배치·프로필·폴더 구조**만 이 저장소에서 운영합니다.

원본 ir-search 플러그인 설명은 [`docs/upstream-ir-search-README.md`](docs/upstream-ir-search-README.md) 및 [`README.en.md`](README.en.md)를 참고하세요.

## 프로젝트 목적

- K-Startup·기업마당·NIPA·KOCCA·SMTECH 등 공개 공고를 주기적으로 수집한다.
- 수집 원본은 `data/raw/YYYY-MM-DD/`에 날짜별로 보관하고 수정하지 않는다.
- 이후 단계에서 정규화·QRPick 적합성 평가·제안 대응으로 확장한다.
- QRPick 실제 서비스 저장소와는 연결하지 않는다 (독립 로컬 운영체계).

## 현재 구축 범위 (1단계)

포함:

- Python `.venv` + `requirements.txt` (`curl_cffi>=0.15`)
- 운영 폴더 구조 (`config/`, `data/`, `app/`, `logs/`, `scripts/` 등)
- `ir-search-profile.md` (QRPick 프로필 초안)
- Windows 배치 스모크 테스트
  - `scripts/test_kstartup_collect.bat`
  - `scripts/test_all_sources_collect.bat`
- 실행 로그 (`logs/`)

아직 포함하지 않음:

- 대시보드
- AI 평가 / 유료 AI API
- 추가 관광기관 크롤러
- 제안서 자동 생성 파이프라인 본구현

## 실행 방법

### 최초 준비

```bat
cd C:\git_hub\work\qrpick-opportunity-pipeline
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### K-Startup 수집 테스트

```bat
scripts\test_kstartup_collect.bat
```

### 기업마당·NIPA·KOCCA·SMTECH 통합 수집 테스트

```bat
scripts\test_all_sources_collect.bat
```

배치 파일은 프로젝트 루트로 이동 → `.venv` 활성화 → 오늘 날짜 폴더 생성 → 원본 `skills/ir-search/scripts/*.py` 호출 → 결과/로그 기록을 수행합니다.

## 생성되는 파일 위치

| 종류 | 경로 |
|------|------|
| K-Startup 원본 | `data/raw/YYYY-MM-DD/kstartup_all.jsonl` |
| 통합 소스 원본 | `data/raw/YYYY-MM-DD/sources_all.jsonl` |
| K-Startup 실행 로그 | `logs/YYYY-MM-DD_kstartup_test.log` |
| 통합 소스 실행 로그 | `logs/YYYY-MM-DD_sources_test.log` |
| QRPick 프로필 | `ir-search-profile.md` |
| (사전 수동 검증본) | `data/raw/manual-test/` |

원본 JSONL은 덮어쓰되 **내용을 편집하지 않는 것**을 원칙으로 합니다. 가공본은 이후 `data/normalized/` 등에서 다룹니다.

## 알려진 제약

- 공개 공고 페이지만 접근합니다. 로그인·CAPTCHA 우회·비공개 API는 하지 않습니다.
- `curl_cffi`가 없으면 TLS 지문 차단으로 실패할 수 있습니다. `.venv`에 `curl_cffi>=0.15`를 설치하세요.
- 사이트 개편·일시 장애 시 해당 소스만 0건 또는 부분 실패할 수 있습니다. 우회 코드는 추가하지 않고 로그에 원인을 남깁니다.
- 요청 간 지연(약 0.3~0.4초)이 있어 통합 수집은 수 분 이상 걸릴 수 있습니다.
- 업력·소재지 등 미확정 프로필 항목은 TODO로 두며 임의 작성하지 않습니다.
- 유료 AI API는 사용하지 않습니다.

### 1단계 실행 검증 메모 (2026-07-15)

- K-Startup (`scripts\test_kstartup_collect.bat`): **성공** — 217건 → `data/raw/2026-07-15/kstartup_all.jsonl` / `logs/2026-07-15_kstartup_test.log`
- sources `list all` (`scripts\test_all_sources_collect.bat`): **성공** — 825건 → `data/raw/2026-07-15/sources_all.jsonl` / `logs/2026-07-15_sources_test.log`
  - bizinfo 450 · nipa 300 · kocca 16 · smtech 59
- 사이트 접근 실패: **없음** (우회 코드 미작성)

## 원본 ir-search 코드와 QRPick 맞춤 코드의 경계

| 구분 | 경로 | 수정 정책 |
|------|------|-----------|
| 원본 수집기·스킬 | `skills/ir-search/` | **수정하지 않음** |
| QRPick 운영 래퍼 | `scripts/*.bat`, `ir-search-profile.md`, `README.md`, `config/`, `app/`(향후) | 이 저장소에서 관리 |
| 원본·로그 산출물 | `data/`, `logs/` | 원본 JSONL은 수정하지 않음 |
| QRPick 서비스 저장소 | (외부) | **연결·수정하지 않음** |

향후 `app/collectors/` 등에 래퍼를 둘 때도 원본 스크립트를 fork해 고치지 말고, 서브프로세스로 호출하는 방식을 유지합니다.

## 다음 단계 (2단계 이후 후보)

1. 프로필 TODO(업력·소재지 등) 확정
2. `data/normalized/` 스키마·정규화 스크립트
3. QRPick 적합 키워드/룰 기반 1차 필터 (유료 AI 없이)
4. 상세공고(`detail`) 선택적 수집과 자격요건 체크리스트
5. 대시보드·제안 파이프라인·추가 관광기관 소스 (별도 착수)

## 라이선스

업스트림 ir-search 플러그인 라이선스는 루트 `LICENSE`를 따릅니다.
