# 세션 컨텍스트 — 2026-06-25

**브랜치**: main · **상태**: in-progress · **배포**: origin/main = 로컬 main = `47221be` · **코드 변경 없음**(설계 세션)

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
