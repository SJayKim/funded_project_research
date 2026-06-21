# 정부과제 데이터 소스 접근성·합법성 조사 (Phase 2.75 산출물)

> **목적**: "한국 정부과제 소스를 실제로 어떻게 수집하는가(공개 API vs 스크래핑 vs 합법성)" — 에이전트 설계를
> 가르는 단 하나의 미지수를 사실로 확인한다. 핸드오프 문서(`office_hours_session_context.md`) §4 표의 가설을
> 검증한 결과다.
>
> **방법**: 6개 클러스터 병렬 웹 리서치 + 클러스터별 핵심 주장 적대적 재검증(독립 에이전트가 1차 출처로
> 확인/반박). 모든 항목에 출처 URL 명시. 직접 확인 못 한 것은 "미확인"으로 표기.
> 조사일: 2026-06-21 · 브랜치 `main` · repo `SJayKim/funded_project_research`
>
> **주의**: 본 문서는 법률자문이 아니라 "확인된 사실 + 출처"다. API 응답 필드 영문명 일부는 추정이며
> 운영 전 실호출로 스키마 확정이 필요하다(아래 각 항목의 미확인 사항 참조).

---

## 0. 한 줄 결론

> **"가능한 모든 자료를 긁는다"는 스크래핑 문제가 아니라 대부분 공개 Open API 문제였다.**
> 핵심 소스(K-Startup·과기정통부 R&D·기업마당·중소벤처24·나라장터 용역)는 **공공데이터포털(data.go.kr)
> 표준 Open API**로 합법·자동승인·무료 수집이 가능하다. **스크래핑이 꼭 필요한 곳은 사실상 IRIS(범부처 R&D
> 공고)와 일부 전문기관**뿐이고, NTIS는 robots.txt가 전면 차단이라 **API로만** 접근해야 한다.

---

## 1. 소스별 판정표 (핸드오프 §4.1 검증 결과)

판정: **API** = 공개 Open API 있음(권장) · **스크래핑** = API 없음, 웹 수집 필요 · **하이브리드** = 둘 혼용 ·
신뢰도는 1차 출처 직접 확인 정도(★ = 검증 에이전트가 confirmed/partly_confirmed로 교차확인).

| 소스 | 무엇 | 판정 | 접근 방법 (확인됨) | 신뢰 |
|---|---|---|---|---|
| **K-Startup 사업공고** | 창업지원사업 공고 | **API ★** | data.go.kr `15125364`. 엔드포인트 `nidapi.k-startup.go.kr/api/kisedKstartupService/v1/getAnnouncementInformation`. serviceKey, **자동승인**, **10,000회/일**, JSON/XML. 공고명·접수시작/종료(YYYYMMDD)·신청대상·지원지역·업력·모집진행여부·상세URL 구조화 | 8~9 |
| **과기정통부 사업공고(정부 R&D)** | 정부 R&D·국제협력·인프라 공모 | **API ★** | data.go.kr `15074634`. 엔드포인트 `apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList`. **자동승인**(승인 후 ~20~30분), 10,000회/일. 필드: 공고제목·담당부서·연락처·게시일·상세URL·첨부 다운로드URL | 8~9 |
| **기업마당(bizinfo)** | 중기부 지원사업 통합 공고(비R&D 다수) | **API ★** | 자체 API `bizinfo.go.kr/uss/rss/bizinfoApi.do` (RSS2.0 XML, 자체 발급 **crtfcKey** 필수). 동일 데이터가 data.go.kr `3034791`(REST JSON/XML/CSV)로도 제공 | 7~8 |
| **중소벤처24 공고정보** | 중기부 유관기관 공고 | **API ★** | data.go.kr `15113191`. serviceKey. 공고명·접수기간·지원기관·신청상태·신청대상·지원규모·상세URL·첨부 | 6 |
| **나라장터 G2B(용역)** | 정부 실증·용역성 과제 입찰공고 | **API ★** | data.go.kr `15129394`(입찰공고) + `15058815`(입찰→낙찰→계약 개방표준, 10,000/일) + 낙찰 `15129397`/계약 `15129427`. 업무구분에 **'용역' 포함**. serviceKey, 자동승인 | 7~8 |
| **NTIS — 과제·성과** | 국가R&D 과제/논문/특허/보고서 | **API ★** | data.go.kr LINK형: 과제검색 `15077315`, 성과 `15077316`, 연구보고서 `15102622`, 수행기관현황 `15138962`. 무료, 공공저작물 **제1유형(출처표시)** (단 15138962는 '제한없음'). LINK형이라 NTIS 자체 인증키가 필요할 수 있음 | 7~8 |
| **NTIS — 사업공고(공고 자체)** | 전 부처 R&D 통합공고 | **스크래핑/하이브리드 ★** | **NTIS OpenAPI에 공고 API 없음**(포털 14종은 과제·성과·기관·연구자·분류 검색뿐). 공고는 통합공고 웹 `rndgate/eg/un/ra/mng.do`(JS 렌더링) 또는 '리스트 다운로드', 혹은 위 과기정통부 API로 우회. **단 NTIS robots.txt = `Disallow: /` 전면 차단 → 스크래핑 금지, API 경로만 사용** | 8 |
| **IRIS(범부처통합연구지원)** | 범부처 R&D 공고·접수 | **스크래핑 ★** | 공개 OpenAPI 없음(IRIS는 오히려 외부 API 소비측). 목록 `iris.go.kr/contents/retrieveBsnsAncmListView.do`, 상세 `…/retrieveBsnsAncmView.do?ancmId=NNNNNN`. **로그인 불요**, **robots.txt가 `/contents/` 공고경로 안 막음**(Disallow 57건 전부 `/wklounge/`·`/sysadmn/`). **서버사이드 렌더 정적 HTML** → 단순 GET+파싱으로 공고명·소관부처·전담기관·공고번호·공고일자·접수기간·첨부 추출 가능 | 8 |
| **부처·전문기관 (개별)** | IITP·KEIT·KIAT·TIPA·NIPA·창업진흥원·KHIDI·KAIA·KEITI | **대부분 스크래핑 ★** | 아래 §2 상세 | 6~9 |
| **지자체·테크노파크(TP)** | 지역 공고(롱테일) | (미조사) | 표준 없음, 1차 범위 제외 후보 | — |

---

## 2. 부처·전문기관 개별 수집 방법 (확인됨)

| 기관 | 판정 | 방법 (확인됨) |
|---|---|---|
| **KAIA**(국토교통과기진흥원) | **RSS** | 작동하는 공개 RSS: `kaia.re.kr/portal/bbs/rss/B0000029.do`. 전문기관 중 **사실상 유일하게 작동하는 공고 RSS** |
| **KEIT**(산업기술기획평가원) | 스크래핑 | SROME `srome.keit.re.kr/srome/biz/perform/opnnPrpsl/retrieveTaskAnncmListView.do?prgmId=XPG201040000` (정적, 숫자 페이징) |
| **IITP**(정보통신기획평가원) | 하이브리드 | 자체 목록 `iitp.kr/.../businessApiList.it`은 **JS/Angular 렌더링 → 정적 GET 불가**. **IRIS 상세로 우회** 권장 |
| **TIPA**(중기기술정보진흥원) | 스크래핑 | TIPA 홈은 링크아웃 포털일 뿐, 실데이터는 **SMTECH** `smtech.go.kr/front/ifg/no/notice02_list.do`(정적 HTML) |
| **NIPA**(정보통신산업진흥원) | 스크래핑 | `nipa.kr/home/2-2` (+ `nipa.kr/rss/2.do` 확인 필요) |
| **KIAT**(산업기술진흥원) | 스크래핑 | `kiat.or.kr/front/board/boardContentsListPage.do?board_id=90` (**AJAX 렌더링**, 헤드리스 필요). ※ KIAT는 산업부 소관으로 IRIS 백본 대상 아님 |
| **KHIDI**(보건산업진흥원) | 하이브리드 | 사업공고 `khidi.or.kr/board?menuId=MENU01108` + RSS 안내 `…/menu?menuId=MENU00623` |
| **KEITI**(환경산업기술원) | 스크래핑 | R&D 공고 `keiti.re.kr/site/keiti/rnd/selectRndNoticeList.do` |

> **시사점**: IITP·KEIT·KIAT·NRF 등 R&D 전문기관 공고의 **공통 백본은 IRIS 상세 페이지**(정적 HTML로
> 전문기관·예산·접수기간 노출)로 쓰는 것이 개별 기관 JS 스크래퍼 N개를 만드는 것보다 유지보수가 싸다.
> 단 KIAT(산업부)·KEITI(환경부) 등 IRIS에 안 실리는 기관은 개별 스크래퍼가 필요하다.

---

## 3. 합법성 정리 (확인됨)

핵심: **공식 Open API 경로가 법적으로 가장 안전하다.** 스크래핑은 공개·무인증·적정량·출처표시·재배포자제로 한정.

1. **공공데이터법 §3(4)**: 공공데이터는 **영리적 이용도 원칙적으로 보장**(금지·제한 불가). **단 예외 있음** —
   타 법률 특별규정(개인정보보호법·저작권법 등) 또는 §28①(업무지장·제3자 권리 현저 침해·범죄 악용 등).
   '무조건 허용'이 아니라 '예외를 제외하고 보장'. (출처: 법제처 `law.go.kr/lsInfoP.do?lsiSeq=218743`)
2. **재배포·2차가공 가능 여부 = 데이터별 공공누리(KOGL) 유형이 최종 결정**:
   제1·3유형 상업적 이용 가능, 제2·4유형 비상업만, 제3·4유형 변경(2차가공) 금지, **전 유형 출처표시 필수**.
   (출처: `kogl.or.kr/info/license.do`)
3. **사실정보 자체엔 저작권 없음**(저작권법 §93④) — 공고의 사업명·접수기간·지원규모 같은 사실은 보호 안 됨.
   **그러나 특정 사이트 DB의 상당부분을 그대로 복제하면 '데이터베이스제작자 권리' 침해**(§93①②).
   판례: **잡코리아 v 사람인** — 크롤링을 DB제작자 권리 침해로 인정, 손배 2.5억 + (강제조정 위반)간접강제금
   2억 = 총 4.5억. (출처: `lawtimes.co.kr/news/121766`)
4. **위법/적법을 가르는 결정적 기준 = ① 기술적 접근제한의 존부 ② DB 통상이용 방해·과부하 여부.**
   **야놀자 v 여기어때** 형사 대법원(2021도1533, 2022.5.12): 회원가입 없이 접근 가능한 **공개·무인증 데이터의
   적정량 수집은 무죄**(정보통신망 침입·DB침해·업무방해 모두 무죄). **단 형사 무죄 ≠ 민사 적법** — 민사 책임은
   별개로 다툼. (출처: `law.go.kr/LSW/precInfoP.do?precSeq=226943`)
5. **부정경쟁방지법 §2(1)카목**(2022.4.20 시행): 데이터 부정사용행위. 타인의 상당한 투자·노력 성과 무단사용
   금지. (출처: 김·장 `kimchang.com/ko/insights/detail.kc?idx=24264`)
6. **robots.txt 실측**: **NTIS = `Disallow: /` 전면 차단**(→ API only), data.go.kr = Googlebot 일부 경로만,
   기업마당 = 시스템 경로만, **IRIS = `/contents/` 공고경로 미차단**. robots.txt는 법적 강제규범은 아니나
   '명시적 거부 무시'는 고의성·위법성 판단에서 불리. (출처: 각 사이트 `/robots.txt`)

> **운영 원칙(권고)**: ① 가능한 건 전부 공식 API로. ② 스크래핑은 robots 허용 + 무인증 공개 + 적정 호출간격
> (rate-limit·캐싱) + 출처표시. ③ 수집 데이터는 KOGL 유형 확인 후 재배포 여부 결정(내부 도구는 재배포 아님).
> ④ NTIS는 절대 스크래핑하지 말 것(robots 전면차단) — API로만.

---

## 4. 선행사례·재사용 (바퀴 재발명 방지)

| 프로젝트 | 라이선스 | 무엇 | 재사용 가치 |
|---|---|---|---|
| **boam79/gov_support_mcp** (37★) | ISC | 기업마당+K-Startup+중소벤처24 **3종 통합** + **중복제거 3단계**(source-id → title+agency 정확매칭 → Jaccard≥0.75) + 알림 **프로파일 CRUD**(발송채널은 없음) | **통합·중복제거 로직 차용에 최적**. `github.com/boam79/gov_support_mcp` |
| **leokim90/gov-data-mcp** | MIT | 중기부·정부24·나라장터·기업마당·중소벤처24 **5종 커넥터**(비캐싱·비재배포 원칙) | **소스 커버리지 가장 넓음**. `github.com/leokim90/gov-data-mcp` |
| **whalelake/bizinfo** | (Python) | 크롤링+API 혼합 자동화 파이프라인(일 2회 스케줄) | 파이프라인 구조 참고. `github.com/whalelake/bizinfo` |
| **정부24 보조금24 / 혜택알리미** | 공식 | 복지·개인 수혜 보조금 중심, gov24 API `api.odcloud.kr/api/gov24/v3` | **직접 경쟁자 아님 → 보완 소스**. 기업 R&D·창업 커버리지 약함 |

> **직접 제작이 필요한 부분**(기존 도구에 없음): ① **NTIS R&D 통합공고 수집기**(오픈소스 대부분이 안 다룸),
> ② **실제 발송 채널**(슬랙/이메일/카톡 — boam79는 프로파일만 있고 발송 없음), ③ R&D 특화 매칭/태깅(2단계).

---

## 5. HWP/PDF 원문 처리 (1차 웨지엔 불필요로 확인)

> **결론: 1차 웨지(수집+알림)에는 HWP/PDF 원문 파싱이 필수가 아니다.** API·목록이 기관·사업명·접수기간·
> 지원규모·신청자격을 이미 구조화 메타로 주므로, **상세 HTML + 첨부파일 링크만 수집**해도 "새 공고 감지 →
> 알림"이 성립한다. 원문 파싱은 **2단계(요약·세부 필드추출)**로 분리.

준비된 도구(2단계용):
- **HWPX**(ZIP+XML, OWPML): `python-hwpx`(활발 유지), 한컴 공식 `hancom-io/hwpx-contents-extract`
- **HWP v5**(OLE2 바이너리): `pyhwp`, 통합 분기 `hwp-hwpx-parser`(HWP5/HWPX 자동감지), `kordoc`(올인원 TS)
- **서버측 변환**: LibreOffice headless는 **반드시 H2Orestart 확장 필요**(맨 LibreOffice 내장 필터는 한글97만
  지원, 현대 v5 못 엶). `github.com/ebandal/H2Orestart`
- **PDF**: 디지털 → `pdfplumber`/`PyMuPDF`, 스캔 → OCR, 상용 대안 → Upstage Document Parse
- **미래정합성**: 2026.10부터 공공기관 기본 문서포맷 **HWPX 의무화** → 신규 공고는 HWPX·PDF로 수렴(검증:
  발표 사실이나 시행세부는 partly_confirmed). 구형 .hwp 비중은 감소 전망.

---

## 6. 권고 — 1차 수집 범위 (Phase 3 입력)

**API 우선 코어**(빠짐없음 + 최소 유지보수 + 최대 합법성):

```text
[A. data.go.kr 표준 API — serviceKey 1개로]
  · K-Startup 사업공고 (15125364)          ← 창업지원
  · 과기정통부 사업공고 (15074634)          ← 정부 R&D
  · 중소벤처24 공고정보 (15113191)          ← 중기부 유관
  · 나라장터 용역 (15129394/15058815)       ← 실증·용역 과제
[B. 기업마당 자체 API — crtfcKey]            ← 비R&D 중소기업/창업
[C. NTIS 과제·성과 API (LINK형)]             ← 과제/성과 메타(매칭·중복판정 보강)
[D. IRIS 스크래핑 (1종)]                      ← 범부처 R&D 공고 백본(IITP·KEIT 등 우회 수집)
  ───────────── 여기까지가 1차 웨지 권장 범위 ─────────────
[2차] KAIA RSS + KIAT/KEITI/NIPA/KHIDI 개별 스크래퍼 + HWP/PDF 파싱 + 매칭/랭킹
```

근거: API 5~6종 + 스크래퍼 1종(IRIS)이면 **R&D(과기정통부+IRIS+NTIS) + 비R&D(기업마당+K-Startup+중소벤처24)
+ 용역/실증(나라장터)** 을 거의 빠짐없이 덮으면서, 깨지기 쉬운 JS 스크래퍼(IITP·KIAT 등) N개를 1차에서 회피한다.

---

## 7. 운영 전 반드시 확정할 미해결 사항

- **응답 스키마 실호출 검증**: 각 API의 정확한 영문 필드명·페이징·**지원규모(금액) 필드 존부**. 점검한 5개 공고
  API 모두 **금액을 정형 숫자 필드로 노출하지 않음**(공고명·접수기간·상세URL·첨부 링크만) → 금액·자격은 상세/
  첨부 파싱 필요. **운영 전 실호출로 스키마 확정 필수.**
- **NTIS 과제/성과 LINK형 API**: data.go.kr 미러가 아니라 LINK형 → NTIS 자체 인증키/승인 절차의 실제 난이도
  (대국민 vs 전문기관 구분) 직접 확인 필요.
- **IRIS 대량 수집 시 IP rate-limit/차단** 여부, 목록 페이지네이션이 GET/POST인지 미확인.
- **기업마당 crtfcKey 발급 절차**(IP/시스템URL 등록)와 일일 호출제한 수치 미확정.
- **각 데이터셋의 KOGL 유형** 개별 확인(상업/재배포/변경 가능 범위).

---

## 부록: 핵심 출처 (1차)

- 공공데이터포털 이용가이드: `data.go.kr/ugs/selectPublicDataUseGuideView.do`
- K-Startup 공고 API: `data.go.kr/data/15125364/openapi.do`
- 과기정통부 R&D 공고 API: `data.go.kr/data/15074634/openapi.do`
- 기업마당 API 안내: `bizinfo.go.kr/web/lay1/program/S1T175C174/apiList.do`
- 나라장터 개방표준: `data.go.kr/data/15058815/openapi.do`
- NTIS OpenAPI 포털(공고 API 부재 확인): `ntis.go.kr/rndopen/api/mng/apiMain.do`
- NTIS 통합공고 웹: `ntis.go.kr/rndgate/eg/un/ra/mng.do`
- IRIS 공고 상세 예시: `iris.go.kr/contents/retrieveBsnsAncmView.do?ancmId=010035`
- 공공데이터법: `law.go.kr/lsInfoP.do?lsiSeq=218743`
- 공공누리(KOGL): `kogl.or.kr/info/license.do`
- 잡코리아 v 사람인: `lawtimes.co.kr/news/121766`
- 야놀자 v 여기어때(대법 2021도1533): `law.go.kr/LSW/precInfoP.do?precSeq=226943`
- 재사용 후보: `github.com/boam79/gov_support_mcp` · `github.com/leokim90/gov-data-mcp`
