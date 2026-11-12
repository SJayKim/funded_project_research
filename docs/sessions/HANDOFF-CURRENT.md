# 현재 작업 인계

갱신: 2026-11-12 KST · 현재 상태: 주기적 신뢰성 점검 활성화·운영 검증 완료

## 목표와 위치

사용자 요청 “신뢰성 제고위해 plan 세워서 진행”에 따라 날짜·수집 상태·파생 정보·원문 정정을 한 배포 단위로 구현했다. 구현 브랜치는 `improve/dashboard-reliability`, 운영 기록 브랜치는 `docs/reliability-rollout-20261112`, 위치는 `/Users/manager/.cache/funded-project-worktrees/reliability-20261112`이다. Phase 0(`a8676fe`)을 포함하고 별도 UI PR #2(`23b8d487`)와 통합했다.

실행 범위는 [신뢰성 개선 실행안](../planning/reliability-release-2026-11-12.md), 검증과 운영 결과는 [현재 상세 인계](reliability-2026-11-12.md)에 기록한다. 원 작업 폴더의 미추적 전체 로드맵과 감사 문서는 수정하지 않는다.

최신 요청은 “매번 신뢰성있게 주기적으로 체크하게 만들어줘”다. 구현 브랜치는 `improve/continuous-reliability`, 운영 기록 브랜치는 `docs/periodic-reliability-rollout`이며, [주기적 점검 구현·검증](../impl-notes/2026-11-12-periodic-reliability.md)에 주기·순환·누락 감시 계약을 기록한다.

## 현재 상태

| 작업 | 상태 | 근거 |
|---|---|---|
| 주기적 점검 | main `f61c259` 반영. 하루 4회+수집 후 검사·매시간 누락 감시 활성화, 첫 운영 실행·공개 대조·감시 확인 완료 | [주기적 점검 인계](../impl-notes/2026-11-12-periodic-reliability.md) |
| Phase 0 데이터 보호 | 신뢰성 PR에 포함 | [Phase 0 인계](phase-00-ci-2026-11-12.md) |
| 검색 중심 UI | 별도 PR #2로 main 반영, 신뢰성 규칙 통합 | [UI 구현노트](../impl-notes/2026-11-12-dashboard-design.md) |
| 정보 신뢰성 | main `608b9a1` 반영, 109개 중 108 통과·유료 1 skip, 원문 20건·DB 보존·공개 브라우저 통과 | [PR #3](https://github.com/SJayKim/funded_project_research/pull/3) |
| 운영 반영 | data `1e4fd49`·Pages 반영. 최신 점검 원문 82/100 확인·18 미확인, 공고/알림 이력 보존 | [상세 인계](reliability-2026-11-12.md) |

## 이어갈 순서와 경계

주기적 점검은 활성 상태이며 다시 설정하지 않는다. 최신 결과는 [공개 점검 기록](https://sjaykim.github.io/funded_project_research/reliability.json)과 Actions에서 확인한다. 이전 수동 점검의 숫자를 현재 상태로 재사용하지 않는다.

1. 상세 인계에 기록한 운영 결과를 기준으로 K-Startup 비JSON·나라장터 구조 불일치부터 진단한다. 이번 `health_only`는 공고 75,221건·알림 135,770건을 보존했고 메일·LLM을 호출하지 않았다.
2. 과기정통부 뒤 페이지와 IRIS 상세 조회 실패를 재현하고 정상/부분 상태 전환을 확인한다. 네트워크 오류를 근거 없이 지오차단으로 단정하지 않는다.
3. 분류·중복 제거, 나라장터 정정 차수, 알림 대기열·누락 보충과 정기 실행 관찰은 남은 작업이다. 전체 17단계 완료로 처리하지 않는다.

사용자의 계획 실행 요청을 승인 근거로 유지한다. `CLAUDE.md`의 오래된 테스트 없음·네트워크 오류 정상 취급 관례보다 실제 코드·테스트와 확인된 감사 결함을 따른다. 데이터 복구는 이후 알림 이력을 보존하며 README의 복구 절차를 따른다. 판단 이력은 [신뢰성 구현노트](../impl-notes/2026-11-12-reliability.md)에 남긴다.
