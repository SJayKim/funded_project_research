# Spec: 정부과제 수집+알림 에이전트 (1차 웨지)

> 작성일: 2026-06-22 · 브랜치 `main` · repo `SJayKim/funded_project_research`
> 근거 문서: `user-main-design-20260622-081511.md`(APPROVED) · `data_source_research.md` · `government_project_research_categories.md`(§11) · `office_hours_session_context.md`
> 모드: Intrapreneurship(내부 실무 도구) · 산출물 분류: 실제 수집 파이프라인 구현

---

## Context (왜 만드는가)

한국 기업/대학 연구실의 과제 담당 실무자는 지금 IRIS·NTIS·기업마당·K-Startup·부처 홈페이지를 사람이 일일이 돌며 신규 공고를 모은다. 시간 소모가 크고, 새 공고를 놓치며, 누가 무엇을 봤는지 공유가 안 돼 마감을 놓치거나 중복 검토한다(office-hours Q1: 가장 아픈 곳 = ① 수집 자체의 고통 ② 정보 흩어짐·놓침). 병목은 **상류(수집·집계·놓침 방지)**이며 매칭·랭킹·요약은 그 다음 문제다(Q1에서 "선별·적합성 판단이 고통"은 선택되지 않음).

**1차 웨지 = 1차 코어 소스 범위 내에서 신규 공고를 빠짐없이 한 곳에 모아 중복 제거 + 마감 임박 추적 + 알림.** "빠짐없이"는 1차 코어 소스 한정(롱테일 지자체·TP, IRIS 미수록 KIAT·KEITI 등은 2차).

## 확정 결정 (이 스펙에서 잠금)

| 항목 | 결정 | 근거 |
|---|---|---|
| 아키텍처 | D) 하이브리드 — B의 모듈형 어댑터+SQLite+증분 diff+알림 디스패처 백본 + A의 단계출시 페이스 | design "Recommended Approach" |
| 상태 영속 | **repo 전용 `data` 브랜치**에 SQLite 파일 load/commit (main 이력 오염 방지) | 사용자 결정 2026-06-22. Actions 러너 stateless → 외부 영속소 필요 |
| 1차 알림 채널 | **이메일(SMTP)** | 사용자 결정 2026-06-22 |
| 실행 | GitHub Actions cron (1주차 주1회 → 안정 후 일1~2회) | design "Distribution Plan" |
| 통합 스키마 | `categories.md §11` 컬럼 그대로 사용(신규 설계 없음) | design Premise 5 |
| 원문 파싱(HWP/PDF) | 1차 제외 — 메타데이터로 "신규 감지→알림" 성립 | data_source_research §5 |
| 기업마당 1주차 처리 | **data.go.kr 미러 `3034791`로 1주차 포함** (crtfcKey 수동발급 대기 없음) | 사용자 결정 2026-06-22 |
| 구현 언어 | **Python** | 사용자 결정 2026-06-22. 재사용 OSS(boam79/leokim90) 정합 |

## 아키텍처 (목표)

```text
[공통 어댑터 인터페이스]  collect() -> [원시 공고]   (API 어댑터 / 스크래퍼 어댑터 동일 계약)
        │
[정규화 레이어]  통합 스키마(§11 컬럼)로 매핑 + 기관명/금액/날짜 정규화
                 (소스별 매핑 추가는 허용 — 신규 소스는 매핑만 늘림)
        │
[중복제거]  소스내 고유키 = {source}:{source_id}
            cross-source 중복 = 정규화 title+agency 정확매칭 → Jaccard≥0.75 (boam79 3단계 차용)
        │
[영속 DB(SQLite, repo `data` 브랜치)]  공고 레코드 + 변경이력
            매 수집 full snapshot을 직전 레코드와 비교, 감시 필드(접수마감·신청상태·첨부 링크)
            변화 시 "수정"으로 판정(필드별 diff)
        │
[알림 디스패처(이메일/SMTP)]  신규 + 마감 임박(D-7/D-3/D-1) + 마감일 연장 등 수정
```

**상태 영속 흐름(매 실행):** `data` 브랜치에서 SQLite 파일 checkout/load → 수집·정규화·중복제거·diff → 변경 레코드 알림 → SQLite를 `data` 브랜치에 commit/push. `data` 브랜치는 main과 분리해 코드 이력 오염을 막는다.

## Current State (검증된 현재 상태, 출처 포함)

소스 접근성·합법성은 `data_source_research.md`에서 6클러스터 병렬 리서치 + 적대적 재검증으로 확정(조사일 2026-06-21). 핵심:

| 소스 | 데이터셋/경로 | 판정 | 1차 마감일 필드 |
|---|---|---|---|
| K-Startup 사업공고 | data.go.kr `15125364`, 엔드포인트 `nidapi.k-startup.go.kr/api/kisedKstartupService/v1/getAnnouncementInformation`, 자동승인, 10,000회/일 | API | ✅ `pbanc_rcpt_end_dt` YYYYMMDD (실호출 confirmed 2026-06-22) |
| 과기정통부 R&D | data.go.kr `15074634`, 엔드포인트 `apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList` (브라우저 UA 헤더 필수, XML 고정) | API | ❌ **마감일 필드 없음** — `pressDt` 게시일만 (실호출 confirmed). 신규 알림만 가능 |
| 중소벤처24 공고 | data.go.kr `15113191` — **LINK 타입**, 제공기관 `smes.go.kr/main/dbCnrs` 연계, 표준 REST 아님(연계 API 가이드 PDF 필요) | API(LINK) | ⚠️ endpoint 미확보 → 실측 불가 |
| 나라장터 용역 | data.go.kr `15129394`(`/getBidPblancListInfoServc`)/`15058815`(`/getDataSetOpnStdBidPblancInfo`), Base `apis.data.go.kr/1230000/...`, UA 헤더 필요 | API | ✅ `bidClseDt` `YYYY-MM-DD HH:MM:SS` / 개방표준 `bidClseDate`+`bidClseTm` (실호출 confirmed) |
| 기업마당 미러 | data.go.kr `3034791`, End Point `api.odcloud.kr/api/3034791/v1/uddi:fa09d13d-bce8-474e-b214-8008e79ec08f`, 자동승인 | API(파일/odcloud) | ✅ `신청종료일자` `YYYY-MM-DD` (실호출 confirmed 2026-06-22) / ⚠️ 연간 스냅샷 |
| IRIS 범부처 R&D 공고 | `iris.go.kr/contents/retrieveBsnsAncmListView.do` 정적 HTML, robots `/contents/` 허용 | 스크래핑 | 접수기간 노출(2주차) |
| NTIS 사업공고 | **공고 API 없음, robots `Disallow:/` 전면차단** | 절대 스크래핑 금지 · API only(과제·성과 메타만) | — |

**합법성 원칙(data_source_research §3):** ① 가능한 건 전부 공식 API ② 스크래핑은 robots 허용 + 무인증 공개 + 적정 호출간격 + 출처표시 ③ NTIS는 절대 스크래핑 금지. 내부 도구이므로 재배포 아님(KOGL 재배포 제약 완화).

## Proposed Change — 단계출시

### 1주차 (data.go.kr serviceKey 자동승인 소스 only)

대상: K-Startup(15125364) · 과기정통부 R&D(15074634) · 나라장터 용역(15129394/15058815) · **기업마당 미러(`3034791`)**. 기업마당 자체 API(crtfcKey 수동발급)는 1주차 블로커이므로 미러로 1주차에 포함하고, crtfcKey 발급은 2차로 미룬다.

- **기업마당 미러 `3034791`**(사용자 결정 B, 2026-06-22): 파일데이터+OpenAPI(odcloud), **업데이트 주기 연간** 스냅샷이라 신선도 한계가 있으나 1주차에 그대로 포함해 수집·표시한다. 실시간성은 2차 crtfcKey API로 보강. **실측 confirmed**: End Point `api.odcloud.kr/api/3034791/v1/uddi:fa09d13d-bce8-474e-b214-8008e79ec08f`, 자동승인 후 동일 serviceKey 200, `신청종료일자` `YYYY-MM-DD`(한글 키). K-Startup(YYYYMMDD·영문 키)과 포맷·키 언어가 달라 정규화 레이어가 양쪽을 처리해야 함.
- **중소벤처24 `15113191`**: LINK 타입(표준 REST 아님, smes.go.kr 연계). endpoint 미확보로 1주차 실측 보류 → 연계 API 가이드 PDF 확인 후 편입 판단.

산출: 공통 어댑터 계약 + 정규화 레이어 + 소스내 중복제거 + SQLite(`data` 브랜치) + 증분 diff + 이메일 알림 1채널 가동 → 곧장 "안 놓침" 체감.

### 2주차 (R&D 백본)

IRIS 스크래퍼(`/contents/retrieveBsnsAncmListView.do`)를 **같은 어댑터 계약**으로 추가. **착수 전 IRIS 목록 1페이지 실측(페이지네이션 GET/POST·rate-limit) 선행.** NTIS 과제·성과 API(LINK형)는 메타 보강용 후속.

성공 기준: IRIS 공고가 동일 파이프라인으로 적재되며 **어댑터 코드 + IRIS 필드 매핑만 추가, diff·알림 로직은 무변경**. cross-source 중복이 정규화 매칭으로 제거됨.

### 통합 스키마 (categories.md §11 — 1차 적재 대상 컬럼)

1차 수집에서 메타로 채워지는 컬럼: 공고명 · 출처 URL · 소관부처 · 전문기관 · 신청 대상 · 접수 마감 · (가능 시)지원금 규모. 나머지 §11 컬럼(우리 회사 역할·제출 난이도·선정 가능성·사업 적합도·우선순위 A/B/C·다음 액션 등)은 2단계(매칭/태깅)에서 채운다. 모든 레코드에 **출처 URL·기관·접수기간 보존 필수(무출처 0건)**.

소스내 고유키: `{source}:{source_id}`. 감시 필드(diff 대상): 접수마감 · 신청상태 · 첨부 링크.

## Acceptance Criteria (pass/fail)

1. 1주차: data.go.kr API 코어에서 신규 공고가 SQLite(`data` 브랜치)에 적재된다.
2. 신규 공고 1건 발생 시 이메일 알림 1건이 실제 수신함에 도착한다(공고명·소관부처·접수마감·출처 URL 포함).
3. 같은 공고를 같은 소스에서 재수집 시 소스내 중복 0건(`{source}:{source_id}` 키 기준).
4. 마감 D-7/D-3/D-1 임박 공고가 정확히 1회씩 알림된다(중복 발송 없음).
5. 직전 수집 대비 감시 필드(접수마감·신청상태·첨부)가 바뀐 공고는 "수정"으로 감지되어 알림된다.
6. 모든 적재 레코드에 출처 URL·기관·접수기간이 보존된다(무출처 0건).
7. 2주차: IRIS 공고가 동일 파이프라인으로 적재되며 diff·알림 로직 코드 무변경(어댑터+필드 매핑만 추가). cross-source 중복(K-Startup vs IRIS 동일 공고)이 정규화 title+agency 매칭으로 제거된다.
8. NTIS 사업공고 경로는 스크래핑하지 않는다(코드·테스트로 보장).
9. 테스트 작성·통과, 기존 기능 무회귀.

## Testing Plan

| Layer | What | Count |
|---|---|---|
| Unit | 정규화(기관명/금액/날짜) · `{source}:{source_id}` 키 생성 · Jaccard≥0.75 중복판정 · 마감 D-7/D-3/D-1 계산 · 필드별 diff 판정 | +8~10 |
| Integration | 어댑터 collect() → 정규화 → 중복제거 → SQLite 적재 → diff → 알림 디스패처 (각 소스 응답 fixture 사용, 네트워크 모킹) | +5 |
| E2E | 신규 공고 적재 → 이메일 발송 1건 / 재수집 → 중복 0건 / 마감 임박 → 알림 / 수정 감지 → 알림 (각 1) | +4 |

엣지케이스: 마감일 필드 없는 소스(알림 스킵 + 로그) · 빈 응답 · 페이지네이션 끝 · 같은 실행 내 중복 · `data` 브랜치 첫 실행(빈 DB) · 알림 발송 실패 재시도.

## Files Reference (예상 — 구현 시 확정)

| File | Change |
|---|---|
| `adapters/base.py` | 공통 어댑터 계약 `collect() -> list[RawNotice]` |
| `adapters/datagokr_*.py` | data.go.kr 4종 어댑터(1주차) |
| `adapters/iris.py` | IRIS 스크래퍼 어댑터(2주차) |
| `normalize.py` | §11 스키마 매핑 + 기관명/금액/날짜 정규화 |
| `dedupe.py` | 소스내 키 + cross-source Jaccard (boam79 차용) |
| `store.py` | SQLite load/save (`data` 브랜치 checkout/commit) |
| `diff.py` | full snapshot 비교 + 감시 필드 diff |
| `notify_email.py` | SMTP 디스패처(신규/임박/수정) |
| `.github/workflows/collect.yml` | cron 스케줄러 + `data` 브랜치 push |

## 재사용 OSS (바퀴 재발명 방지)

- `github.com/boam79/gov_support_mcp`(ISC, 37★) — 기업마당+K-Startup+중소벤처24 통합 + **중복제거 3단계 차용**. 발송 채널은 없음.
- `github.com/leokim90/gov-data-mcp`(MIT) — 5종 커넥터(소스 커버리지 참고).
- 직접 제작 필요: ① IRIS R&D 공고 수집기 ② 실제 발송 채널(SMTP) ③ R&D 매칭/태깅(2단계).

## Out of Scope (1차 제외 — 2단계)

- 매칭·랭킹·요약(회사 프로필→A/B/C 리스트), §11의 점수/우선순위 컬럼 채우기, §9 점수모델·§10 A/B/C
- HWP/PDF 원문 파싱(지원금액·자격 상세 추출)
- 롱테일 지자체·TP, IRIS 미수록 기관(KIAT·KEITI·NIPA·KHIDI 등) 개별 스크래퍼, KAIA RSS
- 슬랙/카톡 등 추가 알림 채널, 노션/시트 읽기용 미러(뷰 레이어)
- NTIS 사업공고 수집(공고 API 부재 + robots 전면차단으로 영구 제외)

## 운영 전 확정 사항 (착수 블로커 — 실측 필요)

design "Open Questions" + data_source_research §7. 추측 금지, 실호출로 확정:

1. ~~**★ 소스별 접수마감일 필드 존부**~~ — **실측 완료(2026-06-22)**. K-Startup `pbanc_rcpt_end_dt`(YYYYMMDD)·기업마당 미러 `신청종료일자`(YYYY-MM-DD)·나라장터 입찰 `bidClseDt`(YYYY-MM-DD HH:MM:SS)·개방표준 `bidClseDate`+`bidClseTm` 모두 confirmed. **과기정통부는 마감일 필드 없음**(`pressDt` 게시일만) → 신규 알림만. **중소벤처24는 LINK 타입이라 endpoint 미확보 → 실측 보류**(연계 API 가이드 PDF 필요). 정규화 레이어는 마감일 4개 포맷 + 한글/영문 키를 모두 처리해야 함.
2. **API 응답 스키마 실호출 검증**: 영문 필드명·페이징. 5개 공고 API 모두 지원금액을 정형 숫자 필드로 노출하지 않음 → 금액은 2단계.
3. **cross-source 중복 판정**: 동일 공고가 K-Startup API와 IRIS에 다른 ID로 뜰 때 title+agency 정규화 매칭이 충분한지 실데이터 검증.
4. ~~기업마당 crtfcKey 발급 절차~~ — **1주차는 미러 `3034791` 채택으로 해소**. crtfcKey 발급(IP/시스템URL 등록·일일 호출제한)은 2차로 이월.
5. **IRIS 목록 페이지네이션(GET/POST)·IP rate-limit/차단** 여부(2주차 착수 전).
6. **SMTP 자격증명·발신 주소·수신자 목록** 확정(Actions Secrets).

## The Assignment (다음 실행 1개)

**data.go.kr에서 K-Startup 공고 API(15125364) serviceKey를 발급받아 1회 호출해 응답 JSON을 저장하라.** 목적: 위 블로커 1·2순위(마감일 필드 존부·응답 스키마·페이징)를 실측으로 확정. 이 한 번의 실호출이 어댑터 인터페이스의 첫 계약(필드 매핑)을 확정한다. 결과 샘플은 `data_source_research.md`의 "운영 전 확정 사항"에 출처와 함께 기록.

## 다음 단계

- 구현 착수 전: 블로커 1~2번 실측(The Assignment) → 어댑터 계약 확정.
- 어댑터 계약·테스트 엣지케이스 락인이 필요하면 `/plan-eng-review` 재개(이번 세션에서 시작했다 spec 우선으로 전환).
