# 세션 컨텍스트 — 2026-06-26

**브랜치**: main · **상태**: in-progress · **배포**: origin/main = 로컬 main = `0e5d57d` (clean) · **데이터**: origin/data = `c55f5b5` (ok 121 / key_dates 120)

> Approach A enrich를 프로덕션에 실가동시키며 (a) key_dates 추출 결함, (b) 마감공고 추출 낭비, (c) upsert 클로버 데이터 유실 — 3건을 발견·수정·검증·배포한 세션. main 커밋 체인 `fef9c96 → a18ba99 → a0a39ba → 0e5d57d` 전부 푸시 완료.

---

## 1. key_dates 추출 튜닝 (남은작업1) — `fef9c96`

- **증상**: enrich 98건 중 key_dates 10건만 채워짐(funding 72·eligibility 73·required_docs 84 대비 현저히 낮음).
- **근본원인**: LLM이 접수기간·신청기간·행사일정 등 **여러 일정을 자체 구분자(' / ')로 병합** → `verify()`의 substring 검증(extract.py:77)에서 비-verbatim이라 100% 탈락. 다른 3필드는 단일 prose 블록이라 verbatim 복사돼 생존. EVAL golden은 verbatim이라 strict 검증 자체는 정상(이 문제 못 잡음).
- **수정**: `extract.py` key_dates 필드 설명을 "접수·신청 기간 **한 구절만 원문 그대로 복사**, 여러 일정 합치거나 형식·구분자 바꾸지 말 것"으로 한정(1줄, 다른 필드 불변).
- **검증(유료 재현→수정→재확인)**: 드롭됐던 corpus 10건에 raw extract 재현 = **2/10** verbatim 생존 → 수정 후 extract_verified 재확인 = **9/10**(1건은 모델 빈 응답 = recall miss, 비결정적). 회귀 61 OK.

## 2. 마감공고 enrich 제외 (사용자 지시) — `a18ba99`

- **지시**: "이미 마감된 공고에 대해서는 진행하지마."
- **실측**: backlog 1098건 중 **마감 1077 / 진행중 21 / 마감없음 0**. 98%가 마감 → 전건 드레인은 ~1100 Opus호출·3시간 낭비였음.
- **수정**: enrich 게이트에 미마감 필터 `deadline_date(r) is None or deadline_date(r) >= date.today()`(collect.py). daily 파이프라인도 매일 마감공고 재시도 안 함(영구).
- **검증**: 신 게이트 정확히 21건, 마감 0건 누수, 회귀 61 OK.

## 3. upsert 클로버 버그 발견·수정 — `a0a39ba` (이번 세션 최대 발견)

- **발견 경위**: 미마감 21건 enrich 후 origin/data ok가 100→**50으로 감소**. 21건 추가했는데 오히려 줄어듦.
- **근본원인**: `store.upsert`가 `ON CONFLICT DO UPDATE SET {전 컬럼}=excluded`로 덮음. `run()`이 collect_all 재수집 공고(추출필드 공란)를 upsert하면 기존 enrich 6필드가 ""로 유실. **summary는 이미 carry-forward로 보호돼 있었으나(collect.py:69-73) 추출 6필드는 누락.** 마감 필터(2번)가 closed 재추출을 막으면서 유실이 영구화·노출됨.
- **부수 효과 확인**: 클로버 탓에 **매 런 enrich가 ~50건을 재추출 = ~7분 낭비**(런 20분의 주범 중 하나). 수정 후 0으로 떨어짐.
- **수정**: `run()`에 추출 6필드 carry-forward 추가(summary와 동일 패턴). 재현 테스트 `test_extraction_preserved_on_recollect` 추가 — 수정 없으면 `'' != '2026-07-01 ~ ...'`로 FAIL, 수정 후 PASS 확인. 회귀 **62 OK**.

## 4. 마감 71건 추출값 복구 (사용자 승인) — data `4d47e81`

- 클로버로 유실된 71건을 직전 스냅샷 `32a3ed2`에서 머지(재추출 없이 무료). 현재 ok값 다운그레이드 방지(현재 공란 ∩ 구버전 비공란만 복구).
- worktree로 data 브랜치 직접 push: ok **50→121**, key_dates **120**.

## 5. CLAUDE.md Gotcha 추가 (사용자 승인) — `0e5d57d`

> `store.upsert`는 ON CONFLICT로 전 컬럼을 excluded로 덮음 — `collect_all` 재수집 공고는 LLM/enrich 파생필드(`summary`·추출 6필드)가 ""로 유실. `run()`에서 `previous`로부터 carry-forward 필수. 신규 파생필드 추가 시 carry-forward 목록에도 등록.

## 6. 프로덕션 배포·검증

- origin/data는 미enrich 구 스키마였음(직전 backfill 가정은 no-op). fef9c96로 시딩 런 → **이슈3(Actions IP에서 상세 fetch 작동 여부) 해결**: kstartup·bizinfo 상세 fetch 정상, 100건 enrich 성공.
- 진행 중이던 daily 자동 런이 **구 SHA(ebde9cc)로 checkout**된 것 발견 → 취소 후 fix로 재디스패치(메모리 [[actions-inflight-run-uses-old-sha]]).
- 클로버 fix 프로덕션 검증: 전체 collect 후에도 ok **121 유지**(50으로 안 떨어짐) = **FIX PASS**. 런 시간 **20분→11분**(enrich 낭비 제거 효과 실증).

## 아키텍처 확인 (사용자 문의)

- **대시보드는 정적**: serve.py `--build` → index.html 1장(DATA 16,110건 JSON 임베드) → GitHub Pages. **LLM/백엔드/fetch 호출 0** — 챗봇 아님. 검색창은 클라이언트 문자열 필터.
- **LLM은 배치 파이프라인에만**: `summarize.py`(요약) + `extract.py`(4필드). 키는 Actions Secrets에만.
- **매일 자동**: `cron: 0 0 * * *`(00:00 UTC = 09:00 KST), 워크플로 active. 06-24·25 자동 성공 실측. 발화는 ~30분 지연(정상). ⚠️ repo 60일 무커밋 시 GitHub가 스케줄 자동 비활성화.
- 육안 확인: https://sjaykim.github.io/funded_project_research/ — ok 공고마다 '지원금액/신청자격/제출서류/주요일정 발췌:' 렌더(419 블록). 표 뷰 기본, 카드 토글 있음.

## 이월 / 미착수

- **collect_all ~11분**(13,889건 전건 재수집)이 런 시간의 남은 병목. 최적화 여지: IRIS를 CI에서 skip(-30s, 어차피 차단 timeout), 또는 변경분만 수집(델타). 설계 변경이라 별도 작업.
- 이전 세션 이월분: 감사 §1·§4 iris 표 정정("중"으로), is_tech LLM화(TODOS), eval_extract.py 라이브 1회(프롬프트 회귀 베이스라인).
- key_dates recall 1/10 miss(모델 빈 응답, 비결정적) — 경미, 모니터링만.

## 비고 / 검증 커맨드

- 테스트: `PYTHONUTF8=1 python tests/test_pipeline.py` → 62 OK(유료 EVAL 1 skip).
- enrich 재현: `git show origin/data:gov_notices.db > gov_notices.db` → `.env` 키 로드(sed로 따옴표 제거) → `python -c "from store import Store; import collect; collect.enrich(Store(), cap=N)"`.
- 시딩 추가: `gh workflow run collect.yml -f no_notify=true --ref main`(런당 미마감 cap=100, 데이터 push 경합 방지 위해 순차).
- 설계 doc: `~/.gstack/.../sjkim-main-design-approachA-20260625-100441.md`.
