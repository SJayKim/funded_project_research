# 신뢰성 개선 인계

2026-11-12 KST. 브랜치 `improve/dashboard-reliability`.
작업 위치: `/Users/manager/.cache/funded-project-worktrees/reliability-20261112`.

## 구현·검증

- 계획: [신뢰성 개선 실행안](../planning/reliability-release-2026-11-12.md).
- KST 날짜·시각·접수 전/마감/충돌/미확인, 48시간 경과, Python/JS 공통 18사례.
- 출처별 수집 결과 저장. 오류 JSON/XML·페이지 중단·반복/상한·총건수 불일치를 실패/부분으로 처리.
- 파생 정보 입력 해시 검증. 오래된 요약/발췌는 DB에 보존하되 현재 정보로 표시하지 않음.
- 상세 추출이 last_seen/source_checked_at을 갱신하지 않음. TLS 체인·호스트 검증 유지.
- 공식 상세의 신청기간만 읽는 제한 재확인. dry-run 기본, 명시적 apply, 근거/정정 이력 저장.
- 운영 사본 75,221건/알림 135,770건의 ID·first_seen·last_seen·알림 전수 비교 일치.
- 실제 공식 원문 20건 확인. HFSP 2029-04-09→2025-04-09, 캠프 2026-11-15→2026-11-06 23:59 정정 확인.
- PR #2의 검색 중심 UI를 통합했다. 전체 unittest 109개 중 108 통과·유료 1 skip. 기존 검색/페이지 이동/상세/표·카드 회귀 검사 통과.
- Chromium: 두 사례 마감 표시, 오래된 발췌 숨김, 확인된 마감임박 17건, 한국 자정·마감시각·접수 시작·확인 만료 자동 전환. 320~1440px 가로 넘침과 콘솔 오류 없음.
- 근거: 작업 폴더 `.gstack/reliability/`의 dry-run/apply 보고서·DB 사본·테스트 로그·스크린샷. DB와 원문 전문은 Git에 넣지 않음.

## 운영 적용

[PR #3](https://github.com/SJayKim/funded_project_research/pull/3)은 CI 통과 후 main `608b9a1`에 병합했다. [운영 점검](https://github.com/SJayKim/funded_project_research/actions/runs/43191282901)은 `health_only=true`로 실행했다. 메일·LLM·공고 신규 적재·알림 이력을 건드리지 않고 실제 수집 응답과 공식 신청기간을 확인했다.

2026-11-12 18:29 KST에 원문 20건 모두 확인하고 data `673a400` 및 Pages에 반영했다. 알려진 날짜 오류 2건과 오래된 발췌 숨김을 공개 화면에서 확인했다. 공고 75,221건·알림 135,770건을 유지했다. 기존 21개 보존 컬럼과 알림 전수를 양방향 비교해 예상 밖 변경은 0건이다. DB 무결성은 `ok`, 검증 이력은 20건이다.

| 출처 | 실제 응답 | 범위와 미확인 원인 |
|---|---|---|
| 기업마당 | 정상, 1,385건·15페이지 | 이번 요청 범위의 응답 완료 |
| K-Startup | 실패, 0건 | JSON 해석 실패. 인증·서버 응답 등 원인은 미확정 |
| 나라장터 | 실패, 0건 | 기대한 응답 구조 또는 공고 ID 조건 불일치. 응답 형태 진단 필요 |
| 과기정통부 | 부분, 300건·30페이지 | 뒤 페이지에서 네트워크 실패 |
| IRIS | 부분, 27건·3페이지 | 목록 응답 후 상세 조회 실패. 목록 전체 차단으로 단정하지 않음 |

위 숫자는 조회 응답 건수이며 새로 적재된 공고 수가 아니다. 이 점검에서는 공고의 `last_seen`·`source_checked_at`도 갱신하지 않았다. 원문 재확인 단계의 `verified_at`과 정정 근거만 갱신했다. 4개 출처가 부분/실패이므로 운영 점검 Actions는 마지막 보고 단계에서 실패했다. DB 저장·정적 빌드·Pages 배포 단계는 모두 성공했고, 이어진 [dashboard 배포](https://github.com/SJayKim/funded_project_research/actions/runs/43191280443)도 성공했다.

운영 백업 artifact `db-baseline-43191282901-1`의 코드·data SHA와 DB 해시를 대조했다. 백업 SHA256은 `35518156fac0357b1bdc6a83ca32bcb17607a5a9462c632c7a0859c575ebdc94`, 반영 후 SHA256은 `f57a81b0489c19886e11775b246ca0135e718972176ee4f5c35e4e7e83c164a4`다. 로컬 검증 근거는 `.gstack/reliability/production-verification.json`, `production-recheck/`, `verified-release.json`과 화면 캡처다. Git에는 DB나 비밀값을 넣지 않는다.

## 남은 작업과 한계

- 기존 17단계 전체 완료가 아니다. 분류/중복 제거, 나라장터 정정 차수, 알림 대기열·누락 보충은 후속이다. UI 재설계는 별도 PR #2에서 반영했다.
- K-Startup의 비JSON 응답, 나라장터 구조 불일치, 과기정통부 뒤 페이지 네트워크 실패, IRIS 상세 조회 실패를 각각 진단한다. 원문 20건 확인은 전체 API 정상화 증거가 아니다.
- PDF/HWP 첨부와 전체 75,221건의 의미 정확성을 검증하지 않았다. 재확인된 기간도 지원 자격·선정 보장이 아니다.
- 정기 실행 3회 관찰과 실제 수신 확인은 아직 수행하지 않았다. 유료 LLM·실제 메일 시험은 실행하지 않는다.
- 기존 unittest의 일부 DB 연결 종료 경고가 전체 실행에서 나타난다. 새 신뢰성 테스트는 별도 확인한다.
