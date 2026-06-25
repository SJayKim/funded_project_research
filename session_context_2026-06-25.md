# 세션 컨텍스트 — 2026-06-25

**브랜치**: main · **상태**: in-progress · **배포**: origin/main = 로컬 main = `0c3dc6c`

> ## 갱신 — 2026-06-25 (저녁, 구현 세션)
>
> 아침은 설계 세션(아래). 저녁에 "다음 작업 1번 후속" 3건을 차례로 구현.
>
> **1. iris CI fetch probe — 미완(사용자 액션 대기).** 이 PC는 한국 IP라 해외 IP 차단 재현 불가, `gh`도 미설치 → dispatch·로그 관측 불가. 사용자가 GitHub→Actions→`fetch-probe` Run workflow 하거나 `gh` 설치 필요. 결과가 `iris FAIL`이면 감사 §3 분기대로 iris 추출 경로 재설계.
>
> **2. EVAL 양성 fixture 6건 — 완료·커밋(`0c3dc6c`).** kstartup·bizinfo·iris 상세 실측 fetch 후 golden 4필드를 본문 verbatim 발췌로 확정. `tests/fixtures/extract/`에 6건 작성, ""(첨부에만)은 substring 자동검증으로 환각 골든 차단. score() 8/8 PASS, 전체 61 테스트 통과.
>   - **실측 정정(중요): 감사 §1·§4가 iris를 "공고문 전문 인라인·커버리지 최상"으로 본 건 과대평가.** 두 iris 페이지 모두 인라인 ■공고문은 표지(공고하오니…장관)뿐 — 금액은 RFP(붙임1), 제출서류는 '제출서류 목록.pdf' 첨부에만. iris HTML-first 실커버리지 = `접수기간✓ / 자격△(일반문구) / 금액·서류✗` 로 **"중"**(msit보다 약간 나음). → 감사 문서 본문 §1·§4 표 미정정(다음 작업).
>
> **3. extract tools-on-body 재확인 — 완료(정적).** `extract.py:3-4`에 실측 기록 존재(Opus 4.8 body에 tools+tool_choice 허용, stop_reason=tool_use). 단위테스트가 body 계약 커버(test_pipeline.py:442-460). 라이브 재검증은 `ANTHROPIC_API_KEY` 필요 → `ANTHROPIC_API_KEY=... PYTHONUTF8=1 python eval_extract.py` (새 fixture 6건 엔드투엔드 동시 검증).
>
> **저녁 세션 다음 작업**: (a) iris CI probe dispatch 후 분기, (b) 감사 §1·§4 iris 표 정정, (c) 키 확보 시 eval_extract.py 라이브 1회 — 프롬프트 회귀 베이스라인 확보.

---

## 작업 내용: 서비스 AI 활용 기능 설계 (/office-hours) — 첫 AI 웨지 "첨부 파싱" 확정

"현재 서비스에서 LLM·agentic loop를 어떻게 써야 반드시 수요가 있을까"를 office-hours(intrapreneurship 모드)로 진단했다. **첫 AI 웨지 = 공고 첨부 파싱 에이전트(Approach A)** 로 확정, 설계 문서 APPROVED(적대적 리뷰 8/10). 이번 세션 산출물은 설계 문서뿐이고 코드 변경은 없다.

## 핵심 결정

| 항목 | 결정 | 근거 |
|---|---|---|
| 첫 웨지 | **A: 첨부 파싱 에이전트** | 모든 사용자가 첫 줄에서 "얼마 주나/내가 되나"를 물음 = 가장 확실한 단일 수요 |
| 매칭은? | **첫 웨지에서 제외**, 최종 목표로 | 사용자 0명 → 매칭할 프로필·정확도 판정자 없음 = 닭-달걀 함정 |
| 현실 진단 | 다중 사용자 지향 + 실사용자 0명 + "만들고 찾을 계획" | build-it-and-they-will-come 단계임을 사용자 스스로 인정 |
| 로드맵 | **A → B(자격 자가진단·매칭-라이트) → C(자연어 검색·일일 브리핑)** | A의 추출 자격이 B 입력 → A 선행 필수. C는 유입용 보너스 |

## Approach A 구현 골격 (기존 코드 위에 surgical)

1. `NoticeRecord`에 4필드 + 근거필드 추가: `funding_amount`·`eligibility`·`required_docs`·`key_dates`·`extracted_from`. `store.py`의 `NEW_COLUMNS` 멱등 ALTER 패턴 재사용. **이 4필드는 `WATCH_FIELDS` 제외**(재추출 드리프트로 인한 오탐·재호출 방지).
2. `extract.py` 신설: `summarize.py`(urllib+anthropic, 키 없으면 fallback) 패턴 복제. 단 평문이 아니라 **구조화 JSON** 반환 → 파싱·검증, 실패 필드만 "미추출"로. 호출 gate = `신규∩기술∩not extracted_from`(캐시), collect.py `run()`에 배선.
3. 텍스트 소스 단계: (a) 상세 본문 HTML 제공 소스 → (b) PDF → (c) HWP. **주의: 현재 어떤 어댑터도 상세 본문 HTML을 안 가져옴**(normalize.py는 목록 필드 + attachments만). (a)는 신규 detail-fetch urllib 경로를 새로 깔아야 함 → Effort M→M~L.
4. `serve.py` PAGE 카드 첫 줄에 금액·자격 노출(1·2순위 UI 위에 필드 추가).
5. 신뢰 장치: 추출값마다 `extracted_from` 근거 + 원문 링크. "자격 됨" 단정 금지, "공고 기준 ○○ 대상" 사실 인용만(잘못된 자격 안내 책임 회피, CLAUDE.md 무출처 금지 규칙 준수).

## 다음 작업 (우선순위)

1. **(코드 전 손작업) Assignment**: 다음 일일 런 신규 공고 10건을 직접 열어 금액·자격·서류·일정 4필드를 표로 정리. ① 어느 소스가 본문 HTML을 깨끗이 주고 어디가 HWP뿐인가 ② 금액 표기 비정형 비율 ③ 자격 판단 애매 비율. → extract.py 프롬프트와 Open Questions 4개를 데이터로 확정.
2. **/plan-eng-review** — 구현 착수 전 아키텍처·테스트·엣지케이스 잠그기(설계 문서 자동 참조).
3. **사용자 인터뷰** — 가장 큰 리스크는 파싱 기술이 아니라 사용자 0명. 정부과제 담당자 3명 인터뷰로 첨부 파싱이 진짜 원하는 건지 검증.

## 이월 / 미확인

- **자동 스케줄 런 모니터링 미완**: 06-24 09:00 KST 첫 자동 런 결과를 이 머신에서 확인 못 함 — `gh` CLI 미설치(`gh: command not found`). gh 설치하거나 GitHub 웹 Actions 탭에서 `collect.yml` success 여부·델타 규모·`[warn] IrisAdapter` 경고 1줄·메일 수신·`origin/data` 새 snapshot 커밋 확인 필요.
- IRIS는 해외 GH Actions IP 차단 지속(CLAUDE.md gotcha) — 첫 출시 추출 소스 집합에서 제외, 커버리지는 CI 도달 가능 소스로만 측정.

## 비고

- 설계 문서(상세): `~/.gstack/projects/SJayKim-funded_project_research/호두주인-main-design-20260624-202406.md` (APPROVED).
- 기존 AI 사용처: `summarize.py`(신규∩기술 공고 1~2문장 Claude Opus 4.8 요약), `classify.py`(기술분야 분류).
- 검증: `PYTHONUTF8=1 python tests/test_pipeline.py`. 대시보드: `serve.py` → http://localhost:8765.
