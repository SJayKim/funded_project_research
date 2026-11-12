# 현재 작업 인계

갱신: 2026-11-12 KST · 확인 범위: Phase 0 코드·로컬 검증·DB 복원

## 목표와 위치

- 목표: 정부과제 대시보드 개선 계획을 한 세션에 한 phase씩 구현·검증한다.
- 작업 위치: `/Users/manager/Desktop/funded_project_research`.
- 현재 브랜치: `improve/phase-00-data-safety`, 시작 코드 `86f63b3`.
- 계획 정본: 로컬 `docs/planning/dashboard-improvement-plan-2026-11-12.md`.

## 현재 상태

| 작업 | 상태·검증 | 다음 행동·상세 인계 |
|---|---|---|
| Phase 0 | 로컬 구현 완료, 86개 테스트 중 85 통과·유료 1 skip | GitHub Python 3.13 CI 확인, [단계 인계](phase-00-data-safety-2026-11-12.md) |
| Phase 1 | 미착수 | 한국 시각·날짜·접수 상태 규칙 통일 |
| Phase 2~16 | 미착수 | 계획의 선행 조건을 따라 순서대로 실행 |

- 운영 main/data/Pages에는 미적용. 제품 스키마·수집·발송 로직 변경 없음.
- 실제 DB 사본: 공고 75,221·알림 135,770, 원본/복원/백업 해시 동일.
- 보호할 작업: 사용자 미추적 감사 보고서와 계획서. 원본 수정·커밋하지 않았다.
- 진행 중: Phase 0 마무리/원격 CI 확인. 실제 수집·발송 프로세스는 실행하지 않음.

## 이어갈 순서

1. `git status --short --branch`와 최신 Phase 0 검증 판을 확인한다.
2. 단계 인계와 계획서 Phase 1을 읽는다. 과거 전체 세션을 기본 입력으로 읽지 않는다.
3. Phase 0의 최신 판에서 `improve/phase-01-date-status`를 분기하고 Phase 1만 진행한다.

## 결정과 경계

- 사용자 계획 실행 요청을 승인 근거로 유지한다. phase 진행 때문에 같은 승인을 다시 묻지 않는다.
- 수집/발송 로직과 운영 적용은 후속 phase에서 다룬다. 실제 시험 수신자·첫 방문자 결과는 아직 정해지지 않았다.
- `CLAUDE.md`의 오래된 테스트 없음 안내보다 실제 코드·테스트를 따른다.
- 데이터 백업을 되돌릴 때 이후 알림 이력을 지우지 않는다. 복구 절차는 README를 따른다.

상세 검증/한계: [Phase 0 인계](phase-00-data-safety-2026-11-12.md) · 판단 이력: [구현노트](../impl-notes/2026-11-12-phase-00-data-safety.md).
