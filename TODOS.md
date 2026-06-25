# TODOS

Approach A(공고 본문 파싱) /plan-eng-review에서 명시 연기된 항목. 컨텍스트 포함.

## nara 입찰 전용 추출 스키마 (사용자 승인 2026-06-25)
- **What:** v1 추출 게이트에서 nara(나라장터 입찰/조달) 제외. 입찰 전용 추출 스키마(예산·벤더자격)를 별도 설계.
- **Why:** 조달 입찰은 grant/지원공고와 다른 제품면. 동일 funding_amount·eligibility 프롬프트를 입찰에 쓰면
  '계약예산/벤더자격'을 '지원금/신청자격'으로 오표시해 대시보드 이용자가 혼동(Codex 검토 #18).
- **Pros:** 추출 의미 정합성. grant 카드 신뢰도 유지.
- **Cons:** nara 공고는 v1에서 금액·자격 칸 비어 보임(수집·알림은 유지).
- **Context:** v1 추출 = grant 3소스(kstartup·bizinfo·iris)만 (msit은 감사 1번에서 제외 확정). 다음작업 1번 10건 감사 때 nara 포함 가치 재평가.
- **Depends on:** 없음. 단 입찰 스키마는 grant 추출 안정화 후.

## msit v1 추출 제외 (감사 1번 확정 2026-06-25)
- **What:** v1 추출 게이트에서 msit 제외. 2단계 첨부(HWP) 파싱 구현 시 합류.
- **Why:** 다음작업 1번 HTML 커버리지 실측 — msit 상세 본문엔 공고 도입부+장관 서명만, 4필드
  (funding_amount·eligibility·required_docs·key_dates) 전체가 HWP/HWPX 첨부에만 있음(첨부확장자 10회).
  HTML-first 효용 ≈ 0이라 추출해도 신규 4필드를 못 채움.
- **Pros:** 빈 추출 호출 낭비 방지. grant 카드 신뢰도 유지(빈칸 환각 방지).
- **Cons:** msit 공고는 v1에서 금액·자격 칸 비어 보임(수집·분류·알림은 유지).
- **Context:** v1 추출 = grant 3소스(kstartup·bizinfo·iris)만. 단 iris는 CI 해외IP fetch 차단 시 재설계 필요(probe 실측 대기).
- **Depends on:** 첨부(PDF/HWP) 파싱 2단계 — 아래 항목과 합류.

## is_tech 게이트 강화 (상세HTML 기반 재분류)
- **What:** classify가 제목+대상만 보는 현재(classify.py:28)를, 상세HTML 본문 확보 후 본문 기반으로 재평가.
- **Why:** 기술 신호가 본문/첨부에만 있는 공고를 추출이 건너뜀 = 보강해야 할 공고를 놓침(Codex #4).
- **Pros:** 추출 커버리지 정확도. **Cons:** 분류가 enrich 단계에 의존하게 됨(순환 주의).
- **Context:** enrich가 상세HTML을 이미 fetch하므로 그 텍스트로 classify 재실행 가능. v1은 기존 게이트 유지.
- **Depends on:** Approach A enrich 단계 구현.

## 첨부(PDF/HWP) 파싱 — 2단계
- **What:** 상세HTML로 커버 안 되는 공고의 첨부(PDF/HWP)를 다운로드·파싱해 추출.
- **Why:** 일부 소스는 핵심 정보가 HWP 첨부에만 있음. **Cons:** 제3자 의존성(pypdf/pyhwp)·CI install·
  HWP 변종 함정·DB/저장 비대화(Codex #5,#6,#19).
- **Context:** 다음작업 1번이 'HTML로 몇 %나 커버되나'를 실측 → 부족분이 크면 착수. 가치 증명 전엔 보류.
- **Depends on:** HTML 추출 커버리지 실측 결과.

## RAG 기반 챗봇 (로드맵 C단계)
- **What:** 보존한 상세HTML 코퍼스를 임베딩·인덱싱해 자연어 질의 챗봇.
- **Why:** "내가 되는 마감임박 AI 과제" 같은 대화형 질의 = RAG 스윗스팟. v1이 코퍼스를 적립해둠.
- **Context:** v1에서 추출 원문을 commit DB 밖에 보존(이슈8) → C단계에서 재크롤 없이 인덱싱. v1엔 RAG 인프라 미도입(YAGNI).
- **Depends on:** v1 코퍼스 적립 + 사용자 검증.
