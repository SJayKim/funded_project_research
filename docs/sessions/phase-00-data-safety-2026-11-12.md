# Phase 0 인계 — 로컬 구현·검증 완료

확인: 2026-11-12 KST · 운영 적용: 미적용 · GitHub CI: 푸시 권한 부족으로 미실행

## 기준과 결과

- 위치: `/Users/manager/Desktop/funded_project_research`.
- 브랜치: `improve/phase-00-data-safety`, 시작 코드 `86f63b343697c23b485946ec65be3c58c16ef804`.
- 검증한 제품 판: `d274240`. 이후 커밋은 이 인계의 상태 기록만 갱신한다.
- 범위: 계획서 Phase 0의 테스트 진입점, DB 보호, 수집 직렬화, 복구 안내.
- 제품 수집·알림·날짜·분류·요약·화면 로직과 DB 스키마는 변경하지 않았다.
- 수집 전 테스트 → 복원/검사 → 백업 artifact 보존 → 수집 → DB 재검사 → 저장/배포 순서다. 앞 단계 실패를 무시하는 분기를 제거했다.
- 원격 브랜치 부재와 통신 오류를 구분한다. 최초 생성은 수동 `initialize_db`와 원격 브랜치/로컬 DB 부재가 모두 필요하며 `--no-notify`를 자동 적용한다.
- 수동/예약 실행의 concurrency 그룹은 하나이고 `cancel-in-progress: false`다.
- 유료 평가에는 키 외에 `RUN_LIVE_EVAL=1`이 필요하다. 기본 검증은 실제 API·SMTP·LLM 없이 수행한다.

## 검증 근거

| 검증 | 결과 | 범위·한계 |
|---|---|---|
| 변경 전 Python 3.13.16 unittest | 71개 실행: 70 통과, 유료 평가 1 skip | 계획서 기준선과 일치 |
| 변경 후 `python -m unittest discover -s tests -v` | 86개 실행: 85 통과, 유료 평가 1 skip | 새 복원 테스트 15개 포함 |
| 복원 실패 주입 | 원격 오류, fetch 실패/오래된 ref, 누락 blob, 빈/손상 파일, 누락 테이블/컬럼/기본 키, 백업 실패에서 중단 | 기존 로컬 파일·원격 data 보존 |
| 정상/최초/구 스키마 | 파일 바이트·공고 키·수집 시각·알림 보존, 정상 빈 DB 허용, 구 스키마는 검사 중 미이행 | 실제 임시 Git 원격/SQLite 사용 |
| 실제 workflow 셸 리허설 | 이전 명령은 손상 DB에도 모의 수집/SMTP 각 1회, 수정 후 각 0회 및 원격 변경 0회 | Actions의 단계 성공 조건을 로컬 순차 실행으로 모사; 실제 SMTP 0회 |
| workflow 추가 리허설 | 최초 시딩은 `--no-notify`, 정상 갱신 성공, push 거절은 실패 종료·원격 미변경 | 임시 원격에만 push |
| actionlint 1.7.12 | collect/test YAML 오류 0 | shellcheck 자체는 미실행 |
| API 키만 있는 환경의 유료 평가 | 1개 skip | 실제 키 대신 합성 문자열 사용; 유료 호출 0회 |
| 운영 DB 사본 복원/검증 | 공고 75,221, 알림 135,770, 무결성 `ok`, 바이트 동일 | 원격 DB 읽기만 수행 |
| 복원 DB의 정적 빌드 | 성공 | 화면·사용성 검증을 대신하지 않음 |
| `git diff --check` | 통과 | 사용자 미추적 문서 원본 해시 보존 |
| GitHub Python 3.13 CI | 미실행 | workflow 수정 권한 부족으로 branch push 거절; Phase 0의 원격 완료 조건은 남아 있음 |

로컬 명령은 Python 3.13을 지정하기 위해 `uv run --no-project --python 3.13`을 앞에 붙였다.
로컬 상세 자료는 Git 제외 경로 `.gstack/phase-00/`에 있다:
`unittest.log`, `actionlint.txt`, `workflow-rehearsal.json`, `snapshot-preservation.json`, `dashboard.html`.
CI는 `.github/workflows/test.yml`에서 같은 unittest 명령을 실행한다.

## 데이터 기준선과 복구

- 기준 data SHA: `679ff058bcd22ebf43491d540ce86d5a8cf59027`.
- DB 파일: 45,625,344 bytes.
- SHA-256: `35518156fac0357b1bdc6a83ca32bcb17607a5a9462c632c7a0859c575ebdc94`.
- 기존 감사 사본: `.gstack/qa-reports/2026-11-12/gov_notices.db`.
- 복원 사본: `.gstack/phase-00/restored-gov.db`.
- 백업/메타데이터: `.gstack/phase-00/production-baseline/{gov_notices.db,manifest.json}`.
- manifest의 코드 SHA는 원본 기준선 `86f63b3`이다. 그 판에서 작업한 diff를 검증한 후 제품 판 `d274240`으로 커밋했다. 후속 문서 커밋과 제품 판을 구분한다.
- 복구 절차는 [README](../../README.md#복원-실패와-복구)에 있다. 백업 이후의 알림 이력을 지우는 롤백은 하지 않는다.

## 중단·보존 사항

- 운영 `main`/`data`/Pages, 실제 수집 일정과 SMTP·LLM 설정은 변경하지 않았다. 코드의 운영 적용은 Phase 15 범위로 남긴다.
- GitHub의 실제 예약/수동 동시 실행은 운영 수집·발송을 동반하므로 실행하지 않았다. 그룹 설정·취소 정책과 로컬 복원/저장 흐름을 검증했다.
- SMTP 접수 후 DB 저장 중단, 알림 이력 의미, 수집 결과의 성공/실패 판정은 기존 한계다. Phase 3·11~12의 목표를 이번 완료로 간주하지 않는다.
- `CLAUDE.md`의 “빌드/테스트 없음” 안내와 실제 코드가 충돌한다. 실제 코드·테스트를 따르고 README의 표준 명령을 정정했다. 출처별 접근 실패 원인 등의 오래된 지침은 해당 phase에서 검증한다.
- 사용자 미추적 `AUDIT-2026-11-12.md`, `docs/planning/dashboard-improvement-plan-2026-11-12.md`는 원본을 보존했고 이 커밋에 넣지 않는다.

## 원격 게시 막힘

- `git push -u origin improve/phase-00-data-safety`가 GitHub에서 거절됐다: OAuth 인증에 `.github/workflows/collect.yml` 수정에 필요한 `workflow` scope가 없다.
- 기존 gh 인증의 scope는 `gist, read:org, repo`다. 키·토큰을 출력하거나 변경하지 않았다.
- 기존 SSH agent 인증도 `Permission denied (publickey)`로 실패했다. HTTPS로 받은 GitHub 호스트 공개 키는 로컬 검증용 임시 known_hosts에만 사용했고 인증 설정은 바꾸지 않았다.
- 원격 branch/PR은 생성하지 못했다. **push pending: `improve/phase-00-data-safety`**.
- 사람 확인이 필요한 것은 GitHub 인증의 `workflow` 권한 부여다. 계정 소유자가 `gh auth refresh -h github.com -s workflow`로 갱신한 뒤 기존 작업 브랜치를 push하고 `tests` workflow를 확인하면 된다. 계획 범위에 대한 재승인은 필요하지 않다.

## 다음 세션

1. [현재 인계](HANDOFF-CURRENT.md), 로컬 계획서 Phase 1, 현재 branch/status를 확인한다.
2. GitHub 인증 갱신 뒤 같은 Phase 0 브랜치를 push하고 Python 3.13 CI를 확인한다. 통과한 판에서 `improve/phase-01-date-status`를 분기한다. 운영 main에는 아직 Phase 0이 없다.
3. 날짜·접수 상태 공통 fixture와 최소 보존 필드부터 시작한다. 한국 자정/마감 시각/종료 상태/충돌/잘못된 달력/중복 이행이 Phase 1 완료 기준이다.

구현 판단 이력: [구현노트](../impl-notes/2026-11-12-phase-00-data-safety.md).
