# MICE 소스 감사·수집 정책

기준일: 2026-07-15  
관련: `docs/mice-source-feasibility-audit.md`(기존 3사이트), `config/mice-source-registry.yaml`(기준 데이터), `docs/mice-source-landscape.md`  
산출물: `reports/mice-source-audit.csv`는 YAML에서 생성하는 파생 파일이며, 소스 메타데이터의 기준이 아니다.

## 1. 절대 원칙

1. 공개 웹페이지·공개 API·공개 다운로드만 조사·수집한다.
2. 로그인·CAPTCHA·접근제한을 우회하지 않는다.
3. robots 또는 이용약관이 불명확하면 **대량 수집을 보류(HOLD)** 한다.
4. 상업 사이트는 **기술적 가능성**과 **데이터 이용 권한**을 분리 평가한다.
5. 감사·어댑터 검증은 목록·상세 각각 최대 3페이지 표본만 사용한다.
6. 기존 3사이트(`mice.or.kr`, `k-mice`, `myfair`) 감사 결과를 임의로 덮어쓰지 않는다.
7. 등급 변경 시 **새 근거 URL/파일**과 변경 이유를 레지스트리 `notes`에 기록한다.
8. `skills/ir-search`, `data/raw`는 이 작업에서 수정하지 않는다.

## 2. 기존 감사 인수 규칙

- 기준 문서: `docs/mice-source-feasibility-audit.md`
- 원문 샘플(로컬, gitignore): `logs/mice-feasibility-audit/`
- `audit_status=INHERITED_EXISTING_AUDIT`로 표시한다.
- 기존 single grade(A/A/C)는 최소한 `technical_grade` / `legal_operational_grade`로 매핑하되, 기존 문장 판정을 뒤집지 않는다.
- 재검증은 파일 부재·근거 부재·구조 변경·충돌·구현 필수 누락일 때만 한다.

## 3. 등급 정의

### technical_grade
- **A**: 공개 API·다운로드·안정 SSR HTML
- **B**: 공개 XHR/JS 분석 또는 개별 어댑터 필요
- **C**: 브라우저 자동화 필요 또는 구조 불안정
- **D**: 기술적으로 수집 부적합(접속 불가 포함)

### legal_operational_grade
- **A**: 이용조건 명확, 내부 수집 가능(공공데이터·조달 등)
- **B**: 제한적 내부 활용 가능, 예의적 수집·약관 추가확인
- **C**: 사전 허락·제휴 필요 또는 robots 상 대량 수집 보류
- **D**: 수집 제외

### business_value_grade
- **A**: QRPick 직접 영업·입찰·시스템 공급 정보 풍부
- **B**: 기관·행사 발견·영업단서 유용
- **C**: 중복·보조 정보
- **D**: 현재 기대가치 낮음

### implementation_priority
- **P0 / P1 / P2 / HOLD / EXCLUDE**

## 4. 공식 원 출처 우선순위

1. 행사 공식 홈페이지  
2. 주최기관 공식 사이트  
3. 개최 시설 공식 일정  
4. 공공 MICE 포털  
5. 협회·산업단체 일정  
6. 상업 집계 플랫폼  

상업 플랫폼은 **discovery source**로만 쓰고, 일정·연락처는 상위 우선순위에서 재확인한다.

## 5. 중복 이벤트 모델(설계)

삭제하지 않고 연결한다.

- `canonical_event`: 정규화된 행사 키(이름+기간+도시/베뉴 기반, 추후 규칙)
- `source_occurrences[]`: 소스별 관측
- `official_source`: 위 우선순위로 선정
- `discovery_source`: 최초 발견에 사용한 집계/미디어

## 6. QRPick 사업가치 축

행사 참가 여부만이 아니라 아래를 함께 본다.

- 행사 시스템(등록·체크인·발권·배지·매칭·온라인부스·결과보고)
- 주최·사무국·PCO 영업
- 차기 회차 선제 제안
- 지역관광·다국어·바이어매칭 확장
- 입찰·운영용역·유지관리

## 7. P0 선정 조건

공식성 + 지속 갱신 + 주최/공식URL + 구조화 필드 + QRPick 영업대상 + (가능하면) 입찰/연락 경로 + 기술·법적 명확성.
