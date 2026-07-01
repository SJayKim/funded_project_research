# CLAUDE.md

## Repository Layout

- Runtime package: `funded_project_research/`
- Source adapters: `funded_project_research/adapters/`
- Documentation index: `docs/README.md`
- Tests and fixtures: `tests/`
- Sample API payloads: `samples/`
- Helper scripts: `scripts/`

Run project modules from the repository root:
- Collector: `python -m funded_project_research.collect`
- Static dashboard build/server: `python -m funded_project_research.serve`
- Extraction eval: `python -m funded_project_research.eval_extract`

## Behavioral Guidelines (Karpathy)

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Commands
이 프로젝트는 코드가 아니라 **자료 조사·정리 문서**가 중심이다.
- 빌드/테스트/린트/타입체크: 해당 없음 (소프트웨어 산출물이 아님)
- 자료 조사: `/deep-research <질문>` (다출처 fact-check 리서치)
- 문서 PDF 생성: `/make-pdf <markdown 파일>` (마크다운 → 출판 품질 PDF)

## Project-Specific Gotchas
<!-- 자동 reflection으로 누적됨. 초기에는 비워두기 -->
- 외부 소스 수집은 `collect_all`에서 어댑터별 try/except로 격리 — 한 소스 실패가 전체 실행을 죽이지 않게. (해외 GitHub Actions IP는 IRIS `www.iris.go.kr` 연결 차단됨 실측 2026-06-23. data.go.kr 4종은 정상.)
- 정부서버 `www.*.go.kr` 라이브 API는 해외 CI IP에서 지오차단(국내선 0.3s 정상, CI선 30s timeout) — bizinfo `bizinfoApi.do`도 동일(실측 2026-07-01, IRIS와 같은 클래스). 타임아웃 상향 무의미(행만 길어짐). `collect_all`은 `URLError`를 `[info] 지오차단 추정 격리 스킵`으로, 그 외만 `[warn] 수집 실패`로 로깅 — 매일 뜨는 지오차단을 실제 실패로 오인 금지. 신규 어댑터가 `www.*.go.kr` 라이브 host면 CI 수집 불가 전제(data.go.kr 미러가 있으면 그쪽이 CI 안전).
- 상세페이지 fetch host는 목록 API host와 다름 — enrich가 쓰는 상세 host(`www.k-startup.go.kr`·`www.bizinfo.go.kr` 등)도 `adapters/base._TLS_RELAXED_HOSTS`에 등록해야 AKI 누락 cert가 통과. http_get를 stub하는 단위테스트는 이 갭을 못 잡으니 신규 fetch 경로는 실 fetch 1회로 검증할 것. (실측 2026-06-26: 미등록 시 enrich 100% CERTIFICATE_VERIFY_FAILED.)
- `store.upsert`는 ON CONFLICT로 전 컬럼을 excluded로 덮음 — `collect_all`이 재수집하는 공고는 LLM/enrich로 채운 파생필드(`summary`·추출 6필드)가 ""로 유실된다. `run()`에서 `previous`로부터 carry-forward 필수. 신규 파생필드 추가 시 carry-forward 목록에도 등록할 것. (실측 2026-06-26: 미보존 시 origin/data ok 100→50, 재현 테스트 `test_extraction_preserved_on_recollect`.)

## Measurable Conventions
<!-- 측정 가능한 것만. "잘 써라" 같은 추상 표현 금지 -->
- 모든 조사 자료에는 출처(공고문 조항/URL/기관)를 명시 — 무출처 수치·인용 금지
- 공고 정보는 기관·사업명·접수기간·지원규모·신청자격을 구조화해 기록
- 산출 문서는 한국어로 작성 (해외 공고 대응 시 예외)

## Self-Reflection on Errors
When an error, exception, test failure, or unexpected behavior occurs
during this session, perform reflection AUTONOMOUSLY — do not wait for
the user to point it out:

1. STOP. Do not patch the symptom or suppress the error.
2. Analyze the root cause:
   - What was the actual failure mode (not just the error message)?
   - Why did this happen? Trace back to the originating decision or
     assumption that led here.
   - Was this caused by a silent assumption, missing context, or
     ignored convention?
   - Is this an instance of a pattern that could recur?
3. Fix the root cause, not the symptom.
4. After fixing, ask: "Would a rule in this CLAUDE.md have prevented
   this error?"
   - If YES → propose adding the rule (one line, specific, measurable)
     to the relevant section (Gotchas / Conventions). Show the proposed
     change and wait for user confirmation before writing.
   - If NO → log the lesson to Auto Memory instead, since it's a
     transient environmental issue rather than a project rule.

The goal is preventing the same CLASS of error from recurring. Every
error is a free lesson — capture it before it escapes.

## Project Context
<!-- 도메인·비즈니스 맥락만. 한국어 가능. 코드로 알 수 있는 정보 금지 -->
한국 **정부과제(정부 R&D 등) 관련 자료를 모두 조사해서 제공**하는 프로젝트다.
여러 출처(NTIS, 기업마당, 부처·기관 공고 등)의 공고·지원사업 정보를 조사·정리해
한 곳에서 출처와 함께 제공하는 것이 목표다. 산출물은 조사 문서다.
