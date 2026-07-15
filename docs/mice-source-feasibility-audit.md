# MICE 소스 수집 가능성 감사 (크롤러 미구현)

감사일: 2026-07-15  
범위: 공개 페이지 소수 샘플만(사이트당 목록·상세 최대 3). 로그인/CAPTCHA/접근제한 우회·비공개 API·전량 수집 없음.

등급: **A** 공개 API/정적 HTML 가능 · **B** 브라우저·추가 검증 · **C** 허락·제휴 후 · **D** 제외

## 종합

| 사이트 | 등급 | 요약 |
|---|---|---|
| https://mice.or.kr/ | **A** | Gnuboard SSR HTML. robots는 `/adm/`, `/install/`만 차단 |
| https://k-mice.visitkorea.or.kr/ | **A** (POST 의존 → 구현 시 B 검증) | SSR. 상세·페이지는 공개 form POST |
| https://myfair.co/ | **C** | Next HTML 가능하나 약관상 사전 승낙 없는 복제·배포 금지 |

권장 우선순위(구현 전): k-mice → mice(행사+지원사업) → 전시장 공식 → 다아라/콘텐츄어. **myfair는 제휴 전 제외.**

---

## mice.or.kr (마이스워크넷) — A

1. **robots.txt**: `Disallow: /adm/`, `/install/`  
2. **sitemap.xml**: 없음(404)  
3. **약관**: 사전 승낙 없는 복제·출판·제3자 제공 제한. 운영 (사)부산관광마이스진흥회  
4. **목록**: `/bbs/board.php?bo_table=event` (지원사업: `bo_table=announcement`)  
5. **상세**: `bo_table=event&wr_id={id}`  
6. **페이지네이션**: GET `page=N`  
7. **SSR**: 예  
8. **JSON API**: 미확인(불필요)  
9. **로그인**: 목록·상세 불필요  
10. **CAPTCHA**: 샘플에서 미관찰  
11. **필드**: 제목, 기간, 시간, 장소, 본문, 출처·공식 홈페이지  
12. **담당/홈페이지**: 글별 출처 URL 다수  
13. **원 출처**: 개별 행사 홈페이지 인용  
14. **갱신**: 게시형  
15. **대량 수집**: robots 개방적이나 약관상 정중한 주기·인용; 전량 재배포 비권장  

---

## k-mice.visitkorea.or.kr — A

1. **robots.txt**: `Disallow: /*search*`  
2. **sitemap.xml**: 없음(404)  
3. **약관·저작권**: KTO ⓒ, RSS 안내, 전자우편 무단수집거부  
4. **목록**: `/miceCalendar.kto?func_name=list`  
5. **상세**: GET view는 500. **POST** `func_name=calView` + `miceCalendarDTO.EVENT_NO` (공개 HTML form)  
6. **페이지네이션**: GET `pageIndex` 무효 → **POST** `curr_page=N`  
7. **SSR**: 예  
8. **JSON API**: 미확인  
9. **로그인**: 캘린더 열람 불필요  
10. **CAPTCHA**: 샘플에서 미관찰  
11. **필드**: 한/영 행사명, 카테고리, 기간, 주최, 지역·장소, 공식 웹사이트 등  
12. **담당/홈페이지**: 웹사이트 필드; 담당자 개인정보는 샘플에서 약함  
13. **원 출처**: KTO 집계 + 주최/공식 사이트  
14. **갱신**: 연·월 필터, 장기 캘린더  
15. **대량 수집**: 저속·소량; search 경로 금지; 가능하면 RSS/공식 채널 우선  

---

## myfair.co — C

1. **robots.txt**: Allow이나 `/participation/`, `/workspaces/`, `/term/use` 등 Disallow. Sitemap 명시  
2. **sitemap**: `sitemap_location.xml` → expo_list/detail/slug (`changefreq: daily`)  
3. **약관**: 회사 IP. 사전 승낙 없는 복제·송신·출판·배포 금지  
4. **목록**: `/exhibition-list?v=1&zn={n}`  
5. **상세**: `/exhibitions/{slug}`, `/exhibition/{id}`  
6. **페이지네이션**: `zn`/필터·앱형 UI  
7. **SSR**: Next.js, 행사 핵심 필드는 HTML에 포함  
8. **JSON API**: 공개 `/api` 미검출 → 비공개 API 사용 금지  
9. **로그인**: 일부 공개; 예산·인사이트는 기업회원 전용  
10. **CAPTCHA**: 샘플에서 미관찰  
11. **필드**: 박람회명·일정·국가·부스 CTA·(게이트) 인사이트  
12. **담당/홈페이지**: 중개 플랫폼 포지션  
13. **원 출처**: 해외 주최사 + myfair 가공 데이터  
14. **갱신**: sitemap daily  
15. **대량 수집**: **제휴·이용 허락 후**  

---

## 구글 상위·파이프라인 누락 후보 (robots만)

| 후보 | 예비 등급 | 메모 |
|---|---|---|
| daara.co.kr | B→A 후보 | 산업전시 캘린더. 일부 AI봇 Disallow |
| contentour.co.kr | A 후보 | WP + sitemap. ToS 추가 감사 필요 |
| coex.co.kr / kintex.com | A 후보 | 전시장 공식 일정 |
| micetoday.co.kr | B/C | 뉴스·주간 일정 |
| newswire.co.kr 박람회 | C에 가까움 | 언론 DB |

스크레이프 원문 덤프(`logs/mice-feasibility-audit/`)는 저장소에 넣지 않는다.
