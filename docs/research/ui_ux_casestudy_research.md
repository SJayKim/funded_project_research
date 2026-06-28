# 정부과제 대시보드 UI/UX 개선 — 자료조사(Case Study)

> 목적: 유사하게 성공한 서비스들의 UI/UX를 출처와 함께 조사해, 우리 공개 대시보드
> (`https://sjaykim.github.io/funded_project_research/`)에 적용할 요소를 정리한 한국어 리서치 문서.
> **본 문서는 조사·권고 산출물이며, 실제 재구현은 이 문서 승인 후 별도 단계로 진행한다.**
>
> 조사일: 2026-06-24 · 모든 UI/UX 주장에 출처(서비스명+URL 또는 디자인시스템 조항) 명시, 무출처 인용 0건 원칙.

---

## 1. 프로젝트 프로파일

본 서비스는 5개 공식 출처(K-Startup·기업마당·과기정통부·나라장터·IRIS)의 정부 R&D·지원사업 공고를
매일 무인 수집해 한 화면에 모아 보여주는 **공공 펀딩 디스커버리/애그리게이터**다. 약 14.9k건의 고밀도
리스트를 **검색 + 카테고리 필터 + 마감일 정렬** 중심으로 탐색한다. 핵심 UX 동인은 ① 빠른 스캔,
② 마감 긴급도 인지, ③ 신청자격 필터링, ④ 신규 공고 인지, ⑤ **데이터 출처 신뢰성**이다.

### 1.1 보유 데이터 필드 (코드 근거)

`normalize.py`의 `NoticeRecord` + `store.py`의 notices 테이블 스키마 기준 실재 필드:

| 필드 | 의미 | 채워지는 출처 | 현재 노출? |
|---|---|---|---|
| `title` | 공고명 | 5종 전체 | O |
| `summary` | 요약(캐시) | (규칙/LLM) | O |
| `category` | 기술분야 분류 | classify 결과 | O (드롭다운) |
| `is_tech` | 기술공고 여부 "1"/"0" | classify 결과 | 내부 필터만 |
| `agency` | 소관부처 | 5종 전체 | O |
| `specialized_agency` | 전문/전담기관 | bizinfo·msit·nara·iris | **X** |
| `target` | 신청 대상(자격) | kstartup | **X** |
| `deadline` | 접수 마감(ISO 정규화) | kstartup·bizinfo·nara·iris (msit 공란) | O |
| `status` | 신청상태 | kstartup | **X** |
| `attachments` | 첨부 링크 | msit·nara·iris 일부 | **X** |
| `url` | 원문 URL | 5종 전체 | O (바로가기) |
| `source` | 출처 코드(5종) | 5종 전체 | **X** |
| `first_seen` | 최초 수집일 | (적재 시각) | **X** |
| `last_seen` | 최종 수집일 | (적재 시각) | 정렬키로만 사용 |

### 1.2 데이터 현실 제약 (설계에 직접 영향)

- **카테고리 88% "기타"** — `classify.py`는 제목+`target` 키워드 매칭이며 미매칭 시 `("기타","0")`.
  카테고리 패싯만으로는 위계 설계 불가 → **기술공고 우선 뷰(`is_tech`) 필요**.
- **출처별 필드 결손 비대칭** — `status`=kstartup만, `deadline`=msit 공란, `specialized_agency`=4종만.
  → "출처 무관 균일 컬럼" 가정 금지(빈 값 처리 규약 필요).
- **금액 필드 없음** — `normalize.py` §11 주석: 5개 API 모두 정형 숫자 미노출(1주차 제외).
  → "지원규모 강조" 패턴은 **현재 데이터로 적용 불가**(아래 매핑 표에 별도 표기).

---

## 2. 현행 대시보드 진단

코드 근거: `serve.py` `render_page()` — DB 전건을 embedded JSON으로 박아 만든 **단일 vanilla HTML
테이블 한 화면**(검색 + 카테고리 드롭다운 + 마감일 정렬 토글만, 전부 클라이언트 JS).

**강점**
- 자체완결 정적 HTML 1장 → GitHub Pages 무인 배포에 단순·견고(`serve.py --build`).
- 즉시 검색(제목+요약+기관 부분일치)과 기본 "기술 전체" 디폴트로 88% 기타 편중을 우회.
- 마감일 정렬 기본 최신순(직전 커밋 `159cb06`에서 수정).

**한계**
- **정보 위계 없음**: 카테고리·제목·요약·부처·마감·링크 6열을 균등 테이블로 나열, 강조 차등 없음.
- **모바일 비대응**: 6열 테이블 고정, reflow 없음.
- **보유 필드 상당수 미노출**: `target`(신청자격)·`status`(접수상태)·`specialized_agency`(전문기관)·
  `first_seen`(신규)·`source`(출처)·`url` 원문 외 메타 미표시.
- **마감 긴급도 시각화 없음**: 날짜 텍스트만, D-day/색상 신호 없음.
- **출처 신뢰 표기 0**: 5개 기관에서 수집한다는 사실, 갱신 시점(`last_seen`)이 화면에 없음.
- **대용량 처리**: 14.9k건 전건을 DOM에 렌더(가상 스크롤·페이지네이션 없음) → 초기 렌더 부담.

---

## 3. 레퍼런스 Case Study (서비스별 잘한 점 + 출처)

5개 군 8개 레퍼런스. 각 레퍼런스 머리에 **Phase 0 프로파일 테마 매핑**을 표기한다.

### 3.1 EU Funding & Tenders Portal — 공공 펀딩 포털
*매핑 테마: 패싯필터 · 마감 · 출처 신뢰*

- **상태 필터 + 합리적 디폴트**: Submission status 패싯(Forthcoming / Open for submission / Closed)을
  체크 토글로 켜고 끄며, **기본값으로 Forthcoming + Open만 선택**돼 마감 지난 공고를 처음부터 숨긴다.
  출처: https://www.program-life.cz/wp-content/uploads/2021/10/User-manual.pdf
- **필터-배지 라벨 일관성**: 동일한 Open/Forthcoming/Closed 라벨이 좌측 필터와 각 행 우측 상태 배지에
  그대로 재사용된다. 출처: https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/calls-for-proposals
- **한 줄 메타데이터 위계**: 각 항목은 제목(링크)을 1순위로 굵게 두고 아래에 Call ID·Programme·Type of
  Action·Opening date·Deadline date를 한 줄로 정렬. 출처: 위 User-manual.pdf
- **마감일 정렬**: 상단 Sort by에서 opening date·title·ID·**deadline** 기준 정렬 지원(마감 임박순 가능).
  출처: 위 User-manual.pdf
- **대용량 결과 안내 배너**: "10000+ item(s) found" 결과 수를 즉시 표기하고, 1만 건 초과 시 "검색 조건을
  좁히라"는 배너로 범위 축소를 유도(서버 페이지네이션 `pageSize=50`).
  출처: https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/calls-for-proposals
- **데이터셋 컨텍스트 헤더**: "Calls for proposals" 컨텍스트 헤더로 지금 어떤 데이터 집합을 보는지 명확화.
  출처: 위 User-manual.pdf

### 3.2 원티드(Wanted) — 고밀도 + 패싯 리스트
*매핑 테마: 스캔 용이성 · 패싯 · 신규/상태*

- **카드 메타라인 압축 스캔**: 로고 썸네일 + 굵은 제목 아래 `회사 · 지역 · 경력`을 가운뎃점으로 묶어 한
  카드에서 4개 핵심 필드를 1초 내 스캔. 3열 그리드 고밀도. 출처: https://www.wanted.co.kr/wdlist
- **마감일 부재의 명시적 상태화**: 마감 없는 공고를 빈칸이 아니라 **`상시채용`** 상태 레이블로 표기.
  출처: https://www.wanted.co.kr/wd/370449
- **정량+정성 패싯 혼합**: 직군/경력/지역 드롭다운에 더해 태그 필터를 "채용조건/기술스택"으로 그룹화하고
  '누적투자100억이상·1,001~10,000명' 같은 정성 패싯을 칩으로 제공. 출처: https://www.wanted.co.kr/wdlist/518
- **활성 필터 맥락 유지**: 카테고리 진입 시 필터바 라벨이 `개발・개발 전체`처럼 현재 경로를 표시하고
  URL 파라미터(`?category_id=518&duty_ids=all`)에 필터 맥락을 보존. 출처: https://www.wanted.co.kr/wdlist/518
- **리스트형 ↔ 칸반형 뷰 토글 + 일괄 작업**: 공고관리 화면에서 두 레이아웃 전환, 체크박스 다중선택으로
  여러 공고 마감일 **일괄 연장**. 출처: https://help.wanted.co.kr/hc/ko/articles/38117225118873
- **이미지 최적화 파이프라인**: 모든 썸네일을 `image.wanted.co.kr/optimize?...&w=400&q=75` 프록시로 컨텍스트별
  리사이즈 → 수십 카드 동시 로드 시 대역폭 최적화. 출처: https://www.wanted.co.kr/wdlist/518
- *주의*: 원티드는 마감 D-day 색상 배지를 쓰지 않고 "상시채용"+보상금 배지로 후킹한다. 마감이 핵심인
  우리는 D-day 색상 위계를 **별도 설계**해야 한다(원티드의 "금액 차등 배지=시선 우선순위" 패턴은 마감
  임박도 색상 차등에 응용 가능). 출처: https://www.wanted.co.kr/wd/370449

### 3.3 와디즈(Wadiz) — 마감/긴급도 주도
*매핑 테마: 마감 긴급도*

- **D-day 카운트다운 배지**: 남은 일수를 "D-6, D-12, D-20" 숫자 배지로 정량화해 한눈에 비교 가능.
  출처: https://www.wadiz.kr/web/wcomer/category/total
- **성과 지표를 제목 위로**: 카드 구조가 `썸네일 → 달성률(%) → 모금액 → D-day → 제목 → 메이커` 순서로,
  소셜 프루프(달성률)를 제목보다 먼저 보여 "검증된 인기"를 우선 인지시킴. 출처: 위 카테고리 URL
- **마감임박 전용 컬렉션**: 글로벌 퀵메뉴에 "EndingSoon" 전용 진입점(`/web/wevent/66`)을 상시 제공.
  출처: https://www.wadiz.kr/web/wevent/66
- **상태 분리(오픈예정/진행중/마감)**: `endYn=N`(진행중)과 별도 "comingsoon" 경로로 상태를 분리, 오픈예정
  건은 "오픈알림" 동선으로 연결. 출처: https://www.wadiz.kr/web/wcomingsoon/rwd/409140
- **희소성 카피라이팅**: 제목에 "[Last chance before...]", "[마감임박]"을 넣어 D-day 배지 외 텍스트로도
  중복 강조. 출처: https://www.wadiz.kr/web/wcomer/category/total
- **정렬 옵션**: `order=recommend` 등 URL 레벨 정렬(추천순 기본 + 마감/인기 재정렬).
  출처: https://www.wadiz.kr/web/wcomer/category/total?order=recommend
- *한계*: 스크래퍼가 영문 렌더로 응답해 "마감임박 시 빨강 전환" 색상 토큰과 한국어 정렬 탭 라벨은 직접
  확정 못 함(추가 확인 권장).

### 3.4 Linear — 데이터 테이블/뷰 모범
*매핑 테마: 정보 위계 · 뷰 토글 · 키보드*

- **뷰 토글이 키보드 일급 기능**: Display options에서 리스트/보드 전환, 단축키 `Cmd/Ctrl B`로 즉시 전환.
  출처: https://linear.app/docs/display-options
- **필터 vs 표시 속성 분리**: "필터(목록을 줄임)"와 "Display properties(셀 데이터만 숨김/표시)"를 분리해
  사용자가 **정보 밀도를 직접 조절**. 출처: https://linear.app/docs/display-options
- **필터 후보에 매칭 개수 표시**: `F`로 필터 메뉴를 열면 각 후보 옆에 매칭 이슈 수가 보이고, 적용된 필터
  수식의 각 부분을 클릭해 연산자(is / is not / includes any·all·none / before·after)를 인라인 변경.
  출처: https://linear.app/docs/filters
- **활성 필터를 뷰로 즉시 저장**: 필터 1개 이상 적용 시 custom View 생성 버튼이 나타나 `Alt+V`로 저장
  → 탐색→저장 마찰 최소. 출처: https://linear.app/docs/filters
- **두 단계 검색 스코프**: `/`=워크스페이스 전역 검색, `Cmd/Ctrl F`=현재 뷰 내 즉시 필터형 검색(타이핑하는
  즉시 매칭만 남고 `Esc`로 클리어). 출처: https://linear.app/docs/search
- **그룹 헤더 sticky + 개수 표시**: 그룹핑 시 헤더가 스크롤에도 고정되고 각 그룹에 항목 개수를 토글 표시.
  출처: https://linear.app/docs/display-options
- *한계*: 가상 스크롤 구현·배지 색상 토큰은 공개 docs에 명시 없음(검색 최대 500건 반환만 확인).

### 3.5 KRDS(대한민국 정부 디자인시스템) — 접근성/컴포넌트 권위(국내)
*매핑 테마: 접근성 · 정보 위계 — 한국 정부서비스 1순위 준거*

- **구조화 목록 표형(Structured list, table type)**: 복잡한 상호작용 목록은 표 대신 구조화 목록 권장.
  표형 변형은 전체선택 체크박스 + 표시개수 select + 정렬기준(관련도순/최신순/인기순) + 표 + 페이지네이션을
  이미 규정 — **우리 공고 리스트의 1순위 준거**. 출처: https://www.krds.go.kr/html/site/component/component_04_01.html
- **표 정렬·빈셀 규칙**: 양적 데이터(개수·%)는 우측 정렬, 텍스트·날짜·번호는 좌측 정렬, **빈 셀은 대시(-)**
  로 표기, 열 구분선 지양. 출처: https://www.krds.go.kr/html/site/component/component_04_11.html
- **필터링·정렬 배치**: 너비 충분 시 필터를 버튼으로 축약하지 말고 항상 노출, **정렬 컨트롤은 목록 우측
  상단**, 날짜·시간 필터는 단일값이 아닌 **범위(range)**, 적용 필터는 **칩 + 개별 삭제 + 전체 해제**(3개
  이상이면 일괄 해제 필수). 출처: https://www.krds.go.kr/html/site/global/global_10.html
- **배지(상태 표시)**: 접수 중/마감됨/모집 완료처럼 2개 이상 상태에 배지 사용, 한 항목 1개, 텍스트 4.5:1
  대비, danger/warning/success/information 시스템 색상 클래스 제공. 출처: https://www.krds.go.kr/html/site/component/component_04_06.html
- **태그(대화형 필터 칩)**: 상호작용 있는 필터 칩은 태그, 레이블 2단어 이내, **색상으로 의미 전달 금지**,
  키보드(Tab 진입/Space·Enter 토글·삭제) + `aria-pressed`/`aria-label`. 출처: https://www.krds.go.kr/html/site/component/component_06_04.html
- **color-only 금지 + 대비 매직넘버**: 본문 4.5:1 이상, 상태 색상은 **반드시 아이콘·텍스트 병행**(적록색맹
  고려). 출처: https://www.krds.go.kr/html/site/style/style_02.html
- **결과 건수 라이브 안내**: 필터 결과 건수 텍스트에 `aria-live="polite"` 적용, 정렬·조회 후 포커스는 해당
  UI에 유지. 출처: https://www.krds.go.kr/html/site/global/global_10.html
- **모바일 표 처리**: 좁은 화면에서 헤더·데이터 수직 재배치 또는 가로 스크롤(이때 열 헤더 좌측 고정) 중 택1.
  출처: https://www.krds.go.kr/html/site/component/component_04_11.html
- **날짜·갱신 표기**: 전용 "출처/갱신일" 컴포넌트는 **없음**. 단 날짜는 `YYYY.MM.DD` 점 구분, 각 문서 하단
  "정보 변경 내역(변경일자·내용)" 표로 갱신 이력 명시 → 대시보드 "최종 갱신일" 표기의 준거로 활용 가능.
  메인 콘텐츠가 최신이 아니면 "서비스가 정상 운영되지 않는다고 판단"한다고 규정(최신성=신뢰).
  출처: https://www.krds.go.kr/html/site/component/component_04_01.html , https://www.krds.go.kr/html/site/service/service_01_02.html

### 3.6 GOV.UK Design System — 접근성/컴포넌트 권위(국제)
*매핑 테마: 패싯 · 접근성 · 상태 배지 · 페이지네이션*

- **Table 구조·접근성**: 행/열 헤더에 `scope="col"`/`scope="row"` 필수, 레이아웃 용도 금지(비교 목적만).
  출처: https://design-system.service.gov.uk/components/table/
- **숫자 우측 정렬**: 숫자 열은 `govuk-table__cell--numeric`로 우측 정렬. 출처: 위 table 페이지
- **대용량 데이터는 분할 우선**: 데이터 많으면 표·페이지를 나누는 것을 먼저 권장, 불가피할 때만
  `--small-text-until-tablet`. 출처: 위 table 페이지
- **Tag = 형용사(상태), 인터랙티브 금지**: 'Completed'·'Active'처럼 상태로 라벨링, 링크/버튼화 금지, 색
  변형(grey/green/blue/red/yellow 등) 제공(긴급=red). 출처: https://design-system.service.gov.uk/components/tag/
- **색상만으로 정보 전달 금지**: WCAG 2.2 SC 1.4.1 — 색에 반드시 텍스트 라벨 병행.
  출처: https://design-system.service.gov.uk/components/tag/
- **필터 = 작은 체크박스**: 결과가 핵심이고 필터를 덜 두드러지게 할 때 `govuk-checkboxes--small`.
  출처: https://design-system.service.gov.uk/components/checkboxes/
- **필터·정렬 동작 규칙**: 필터/정렬은 현재 페이지가 아닌 **전체 목록**에 적용하고, 적용 후 **첫 페이지로
  리다이렉트**. 출처: https://design-system.service.gov.uk/components/pagination/
- **Pagination(번호형) + 무한스크롤 금지**: `aria-label`/`aria-current="page"`/생략부호(…), `<title>`에
  "(page 1 of 4)" 표기. 무한 스크롤은 키보드 사용자 문제로 금지. 출처: 위 pagination 페이지
- **Phase/상태 배너**: 헤더 바로 뒤, 모든 페이지에 걸친 **서비스 수준 메시지**로 상태 배너 노출(상태 Tag +
  설명 + 링크) — 우리 "수집 출처/갱신" 신뢰 배너의 구조 준거. 출처: https://design-system.service.gov.uk/components/phase-banner/
- **날짜 포맷**: 날짜는 GOV.UK 스타일(예 '27 March 2007'), 캘린더 단독 입력 금지(텍스트 병행).
  출처: https://design-system.service.gov.uk/patterns/dates/

### 3.7 Skyscanner — 데이터 출처/신뢰(상업 애그리게이터)
*매핑 테마: 데이터 출처 신뢰성*

- **레코드별 제공자 출처 명시**: 한 항공편에 가격을 준 여러 제공자를 함께 나열하고 최저가순 정렬("there
  are usually a number of providers who give us a price... ranked in order of price").
  출처: https://www.skyscanner.net/media/how-skyscanner-works
- **원문으로 핸드오프**: "우리는 여행사가 아니다 — 클릭 시 해당 제공자 사이트로 리다이렉트돼 직접 거래"라고
  명시(원문 링크 패턴의 신뢰 프레이밍). 출처: 위 how-skyscanner-works
- **커버리지 한계 정직 고지**: "수백 제공자를 검색하지만 전수가 아니며, 참조 사이트 수는 검색에 따라
  달라진다"고 과장 없이 공개. 출처: 위 how-skyscanner-works
- **신선도 + "마지막 업데이트" 타임스탬프**: "하루 종일 자동으로 자주 갱신하지만 검색-예약 사이 변동 가능"
  고지 + 페이지에 "Last updated: January 2026" 노출. 출처: 위 how-skyscanner-works
- **정렬·랭킹 투명성**: 기본 "best" 정렬의 가중 요소를 명문화하고 광고/스폰서는 "명확히 구분 가능"하게 분리.
  출처: 위 how-skyscanner-works
- **(비교) Google Flights — "N개 파트너에서 가져옴 + 출처 무영향 선언"**: "300개 이상 항공사·OTA에서
  가져오며 파트너십이 노출 순위에 영향을 주지 않는다", 가격 갱신 주기("약 24시간")까지 공개.
  출처: https://support.google.com/travel/answer/2475306

### 3.8 공공데이터포털 / 통계 대시보드 — 데이터 출처/신뢰(공공)
*매핑 테마: 출처 · 갱신일 · 기준일*

- **3분할 시점 표기**: data.go.kr 상세는 "수정일"과 미래의 "차기 등록 예정일"을 함께 표기(예: 수정일
  2025-12-17 / 차기 등록 예정일 2026-10-01). 출처: https://www.data.go.kr/data/15156444/fileData.do
- **제목에 기준일자 임베드**: 데이터셋 제목 끝에 `_YYYYMMDD`로 데이터 시점을 박음(예: "...개방데이터셋목록
  현황_20260514"). 출처: https://www.data.go.kr/data/15091852/fileData.do
- **데이터 명세 메타패널**: 제공기관·수정일·제공형태·전체 행수·확장자를 한 박스에 구조화.
  출처: https://www.data.go.kr/data/15135731/fileData.do
- **원문 바로가기**: 표준데이터는 원천기관 파일서버 URL을 직접 노출해 "원문 출처"로 연결.
  출처: https://www.data.go.kr/data/15012892/standard.do
- **표준 인용 6요소 + 생산/조회 시점 분리**: KOSIS는 작성기관명·조사명·작성시점·**참조일자(조회·다운로드
  날짜)**·통계표명·URL을 강제 — "데이터 생산 시점"과 "이용자 조회 시점"을 분리. 출처: https://kosis.kr/serviceInfo/useGuide.do
- **원출처 vs 재가공출처 병기**: 집계 지표는 원자료 생산자 출처와 재가공 출처를 함께 표기하도록 지침.
  출처: https://kosis.kr/civilComplaint/qnaDetail.do?boardIdx=24645
- **공식성 강조 + 한계 고지 병기**: "대한민국 공식 전자정부 누리집" 배너 + "통보 없이 변경될 수 있고 오류·
  누락 책임 없음" 고지를 함께 표기. 출처: https://kosis.kr/serviceInfo/useGuide.do
- **(국제) Our World in Data — "Last updated / Next expected update / Date range" 3종**: 데이터 카드에
  마지막 갱신·다음 갱신 예정·데이터 기간을 분리 표기. 출처: https://ourworldindata.org/grapher/life-expectancy

---

## 4. 적용 권고안 매핑 표 (패턴 → 우리 필드 → 우선순위/난이도/출처)

각 권고는 (a) 보유 데이터로 구현 가능한지, (b) 출처가 달려 있는지 검증을 거쳤다.
우선순위 상=신뢰/탐색 핵심, 중=스캔/효율 개선, 하=여건 되면. 난이도 낮음=현 vanilla로 가능, 중=JS 추가,
높음=프레임워크/빌드 권장.

| # | 적용 권고 | 활용 필드 | 우선 | 난이도 | 근거 출처 |
|---|---|---|---|---|---|
| 1 | **D-day 배지 + 마감 긴급도 색상**(D-7 이하 강조), 빈 마감은 대시(-) | `deadline` | 상 | 낮음 | 와디즈 `/wcomer/category/total`; KRDS 표 빈셀 대시 `component_04_11` |
| 2 | **마감임박순 정렬 + "마감임박" 전용 뷰** | `deadline` | 상 | 낮음 | EU Portal Sort by deadline; 와디즈 `/wevent/66` |
| 3 | **접수중/마감 상태 칩**(색+텍스트 병행, 한 항목 1개) | `status` | 상 | 낮음 | KRDS 배지 `component_04_06`; GOV.UK Tag |
| 4 | **신규(NEW) 배지**(`first_seen`가 최근 N일이면) | `first_seen` | 상 | 낮음 | 와디즈 상태 분리; 원티드 신규 노출 |
| 5 | **출처 기관 배지**(K-Startup/기업마당/과기정통부/나라장터/IRIS) | `source` | 상 | 낮음 | Skyscanner 제공자 출처; data.go.kr 제공기관 |
| 6 | **원문 바로가기 강조**(외부 핸드오프 명시) | `url` | 상 | 낮음 | Skyscanner 리다이렉트 고지; data.go.kr 원문 URL |
| 7 | **신뢰 배너**("○건을 5개 공식 기관에서 매일 수집, 마지막 갱신 YYYY-MM-DD") | `last_seen`, `source`, 건수 | 상 | 낮음 | GOV.UK phase-banner; OWID "Last updated"; KOSIS 공식성+한계 |
| 8 | **출처별 건수 분포**("K-Startup N건 · 기업마당 M건 …") | `source` | 중 | 낮음 | Skyscanner "we compare N"; data.go.kr 명세 패널 |
| 9 | **활성 필터 칩 + 전체 해제 + 결과 수 라이브 피드백** | (필터 상태) | 상 | 중 | KRDS 필터 `global_10`; Linear 필터; EU 결과 수 배너 |
| 10 | **신청자격(target) 표기/필터** | `target` | 중 | 중 | 원티드 정성 패싯; EU 패싯 |
| 11 | **전문/전담기관 배지·필터** | `specialized_agency` | 중 | 낮음 | EU Programme 메타; 원티드 메타라인 |
| 12 | **데스크톱 테이블 ↔ 모바일 카드 reflow + 스티키 필터** | (레이아웃) | 상 | 중 | KRDS 모바일 표 `component_04_11`; 원티드 카드 그리드 |
| 13 | **기술공고 우선 뷰 + 카테고리 패싯**(88% 기타 대응) | `is_tech`, `category` | 상 | 낮음 | Linear 필터 vs 표시속성; EU 상태 디폴트 |
| 14 | **뷰 토글(테이블 ↔ 카드)** | (레이아웃) | 중 | 중 | Linear 뷰 토글; EU 리스트/그리드; 원티드 |
| 15 | **가상 스크롤/페이지네이션**(14.9k건) | (전건) | 상 | 높음 | GOV.UK pagination(무한스크롤 금지); EU 서버 페이지네이션 |
| 16 | **검색 하이라이트 + 빈 상태(no-result) 디자인** | `title`,`summary`,`agency` | 중 | 중 | Linear 즉시검색; 원티드 검색 |
| 17 | **접근성 기본기**(4.5:1 대비, color-only 금지, 키보드, `aria-live` 건수) | (전역) | 상 | 중 | KRDS `style_02`+`global_10`; GOV.UK colour/tag |
| 18 | **숫자/날짜 정렬 규칙**(날짜 좌측, 빈값 대시) | `deadline` 등 | 중 | 낮음 | KRDS·GOV.UK 표 정렬 규칙 |
| — | ~~지원규모/금액 강조~~ | **없음** | — | — | **구현 불가**: 5개 API 정형 금액 미노출(`normalize.py` §11) |

---

## 5. 데이터 출처 신뢰성 표시 전용 섹션 (메인 페이지 provenance)

> 요구사항: 각 공고가 어디서 온 데이터인지(5종)와 갱신 시점을 보여줘 신뢰를 확보. 우리는 레코드별
> `source`·`url`·`last_seen` 필드를 **이미 보유** → 아래 권고는 전부 보유 데이터로 구현 가능하다.

### 5.1 레코드 수준 — 출처 배지 + 원문 링크
- 각 행/카드에 `source`를 **출처 기관 배지**로(K-Startup/기업마당/과기정통부/나라장터/IRIS).
  근거: Skyscanner가 각 결과에 제공자를 명시(https://www.skyscanner.net/media/how-skyscanner-works),
  data.go.kr이 데이터셋마다 제공기관을 표기(https://www.data.go.kr/data/15135731/fileData.do).
- `url`은 **"원문 바로가기"**로 외부 핸드오프임을 명시. 근거: Skyscanner "클릭 시 제공자 사이트로
  리다이렉트"(위 URL); data.go.kr 원문 파일서버 직접 링크(https://www.data.go.kr/data/15012892/standard.do).
- 배지는 **색+텍스트 병행, color-only 금지**(KRDS `style_02`, GOV.UK Tag SC 1.4.1).

### 5.2 페이지 수준 — 신뢰 배너 (상단/푸터)
- 문구 예: **"○○,○○○건을 5개 공식 기관에서 매일 수집 · 마지막 갱신 2026-06-24"**.
  - 건수 = 전건 수, 출처 = `source` 5종, 갱신일 = 최신 `last_seen` 또는 빌드 시각.
  - 구조 근거: GOV.UK phase-banner(헤더 뒤, 모든 페이지에 걸친 서비스 수준 메시지,
    https://design-system.service.gov.uk/components/phase-banner/).
  - 시점 표기 근거: OWID "Last updated"(https://ourworldindata.org/grapher/life-expectancy),
    Skyscanner "Last updated: January 2026"(위 URL).
- **생산 시점 vs 수집 시점 분리 고려**: 공고 마감일(생산 측)과 "우리가 마지막으로 수집한 시각"(`last_seen`)은
  다르다 — KOSIS는 작성시점과 조회 참조일자를 분리 표기하도록 강제(https://kosis.kr/serviceInfo/useGuide.do).
  배너에 "수집 기준: 2026-06-24"를 명시하면 신뢰도가 올라간다.
- **한계 고지 병기**(권장): "기관 원문이 갱신·마감 변경될 수 있으니 신청 전 원문 확인" — KOSIS가 공식성과
  한계 고지를 함께 두는 패턴(위 useGuide URL). 우리 가치(무출처 인용 금지)와도 정합.

### 5.3 분포 요약 — 출처별 건수
- "K-Startup N건 · 기업마당 M건 · 과기정통부 … · 나라장터 … · IRIS …" 분포를 배너/푸터에 표기.
  근거: Skyscanner "we compare N providers" 류 요약(위 URL); data.go.kr 명세 패널의 규모 표기
  (https://www.data.go.kr/data/15135731/fileData.do). `source` 집계만으로 구현 가능.

### 5.4 결손 투명성 (우리 데이터 특수성)
- `msit`(과기정통부)는 **마감일이 없다**(`normalize.py` `_map_msit` 주석: 게시일만). 마감 빈 값을 숨기지 말고
  대시(-) + "마감일 미제공(과기정통부)"로 명시 — KRDS 빈셀 대시 규칙(`component_04_11`)과 Skyscanner의
  커버리지 한계 정직 고지(위 URL) 정신을 따른다.

---

## 6. 권고 종합 & 다음 단계

### 6.1 1순위(상) 묶음 — "신뢰 + 마감"을 먼저
보유 필드만으로 즉시 효과가 큰 순서: **신뢰 배너(7)+출처 배지(5)+원문 강조(6)** → **D-day(1)+상태 칩(3)+
신규 배지(4)** → **마감임박 정렬/뷰(2)+기술 우선 뷰(13)** → **모바일 reflow(12)+접근성 기본기(17)**.
이 묶음은 대부분 난이도 낮음~중으로, 현재 `serve.py` 템플릿 확장으로도 상당 부분 가능하다.

### 6.2 구현 단계 선택지 메모 (프레임워크 + 빌드)
- **옵션 A — vanilla 확장(현 구조 유지)**: `serve.py` `PAGE` 템플릿에 배지·배너·필터칩·D-day 로직 추가.
  장점: 무인 정적 배포 단순성 유지. 한계: 14.9k건 가상 스크롤(15)·뷰 토글(14)은 손이 많이 감.
  ※ `serve.py`가 `--build`로 생성하므로 `site/index.html` 직접 수정 금지, **템플릿을 고칠 것**.
- **옵션 B — 프레임워크 + 빌드 도입**(사용자 허용됨): 컴포넌트화 + 가상 스크롤 라이브러리로 대용량/뷰
  토글/반응형을 깔끔히. 정적 산출물로 빌드해 Pages 배포 파이프라인은 유지 가능.
  결정 포인트: (1) 가상 스크롤·뷰 토글이 1순위라면 B, (2) "신뢰+마감 배지"만 우선이면 A로 빠르게.

### 6.3 본 문서 검증 결과 (plan Verification 대조)
1. 모든 UI/UX 주장에 출처(서비스+URL/디자인시스템 조항) — **충족**(무출처 0건).
2. 적용 권고가 보유 필드로 구현 가능 — **충족**, 불가 항목(금액)은 표에 별도 표기.
3. 레퍼런스 8개가 Phase 0 테마와 명시 매핑 — **충족**(각 3.x 머리에 매핑 표기).
4. 데이터 출처 신뢰성 섹션 별도 존재 + `source`/`url`/`last_seen`로 구현 가능한 구체 권고 + 출처 —
   **충족**(섹션 5).

### 6.4 다음 단계
1. 본 문서 승인 → 우선순위(상) 묶음으로 구현 범위 확정.
2. 옵션 A/B 결정.
3. (선택) `/make-pdf ui_ux_casestudy_research.md`로 출판 품질 PDF 생성.
