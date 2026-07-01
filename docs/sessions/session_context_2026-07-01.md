# 세션 컨텍스트 — 2026-07-01

**브랜치**: main · **상태**: in-progress · **배포**: origin/main = 로컬 main = `0914161` (clean, `dashboard-excerpt-view.jpeg` 미추적/임시) · **데이터**: origin/data `gov_notices.db` 18,006건 (nara 7389 · kstartup 5103 · bizinfo 5000 · msit 514)

> bizinfo 라이브 전환(6-30 `1d16a2e`, 7-01 `bfbd212`)의 **프로덕션 회귀를 발견·진단·처리**한 세션. 라이브 `bizinfoApi.do`가 해외 CI IP에서 지오차단됨을 실측 확정하고, 사용자 승인(라이브 유지+경고 정리)에 따라 `URLError`를 `[info]` 격리로 강등. `0914161` 커밋·푸시 완료.

---

## 1. 진행상황 파악 (세션 시작)

- 최근 3세션 흐름 재구성: 06-26(key_dates·마감필터·upsert 클로버 3건 수정), 06-30(bizinfo 정적→라이브 전환), 07-01 최신 커밋 `bfbd212`(라이브 fixture 실캡처 교체·게이트 2·3 검증).
- 로컬 테스트 67 OK(유료 EVAL 1 skip) 확인. 오프라인이라 원격 상태 초기 확인 불가 → 이후 온라인 복구.

## 2. bizinfo 지오차단 회귀 발견·진단 (이번 세션 핵심)

- **발견**: `BIZINFO_CRTFC_KEY` Secret 등록 확인(2026-06-30) + 오늘 daily 런(28485171215) success. 그러나 런 로그에 `[warn] BizinfoAdapter 수집 실패, 건너뜀: <urlopen error timed out>`.
- **데이터 실측**: origin/data에서 bizinfo `last_seen`가 **6-30에 멈춤**(다른 3소스는 7-01) → 7-01 런이 bizinfo 0건 수집 = 회귀 확정. bizinfo 5000건 전부 first_seen 2026-06-23/06-27(구 정적 스냅샷 유래, 미갱신).
- **2번째 CI 데이터포인트**: 수동 런(28499526093, no_notify) 디스패치 → 동일하게 `timed out` 재현 = 일시적 아님, 지속.
- **결정적 판별**: 로컬(국내 IP) 실호출 = **100건 0.3초 성공** vs CI(해외 IP) = **30초 행→타임아웃 2회**. 즉 단순 느림이 아니라 **지오/IP 차단**(WAF geo-filter). 호스트 `www.bizinfo.go.kr` 자체는 정적 시절 상세 fetch가 CI 200이었으므로(06-26) 엔드포인트(`bizinfoApi.do`) 특정 지오차단. **IRIS `www.iris.go.kr`과 동일 클래스**. 타임아웃 상향은 무의미(행만 길어짐).

## 3. 방향 결정 (사용자 승인) — "라이브 유지 + 경고 정리"

- AskUserQuestion 3안 제시: (A) 라이브 유지+경고정리, (B) 정적 odcloud 복귀, (C) Korea-IP 수집 투자. **사용자 A 선택.**
- 근거: 어느 쪽이든 오늘 대시보드 bizinfo 가시 결과는 사실상 동일(≈0, 정적은 16개월 stale이라 (b)필터가 전부 숨김). 라이브 어댑터는 정확하고 국내 실행 시 신선하므로 유지가 우월.

## 4. 처리 — `0914161`

- **collect.py**: `collect_all`이 `URLError`(도달 실패)를 `[info] CI 미도달(지오차단 추정), 격리 스킵`으로, 그 외만 `[warn] 수집 실패`로 로깅. 소스명 하드코딩 없이 예외 타입으로 구분. `from urllib.error import URLError` 추가.
- **재현 테스트**: `test_geoblock_urlerror_is_info_not_warn`(URLError 어댑터 → raws 빈 + stderr에 `[info]` 있고 `[warn]` 없음). 기존 `test_one_adapter_failure_isolated`(RuntimeError)와 호환. **68 OK**.
- **CLAUDE.md Gotcha**: `www.*.go.kr` 라이브 API의 CI 지오차단 전제 명문화(국내 0.3s/CI 30s, 타임아웃 상향 무의미, URLError→info 로깅, 신규 어댑터가 www.*.go.kr 라이브면 CI 수집 불가 전제·data.go.kr 미러 우선).
- 커밋·푸시: 최초 push는 자동 모드가 main 직접 push 차단("알아서 진행"이 미명시) → 사용자 명시 승인 후 push 완료(`bfbd212..0914161`).

## 이월 / 미착수

- **다음 daily 런부터** bizinfo 지오차단이 `[warn]`이 아닌 `[info]`로 표시(검증 런은 미실행 — 로깅 분기는 단위테스트로 잠김·결정적이라 11분 런 생략).
- **신선 bizinfo를 실제로 얻으려면** Korea-IP 수집(self-hosted 러너/로컬 수집→data push)이 유일 경로 — 미착수(선택지 C, 별도 세션).
- 이전 세션 이월 유지: collect_all ~11분 병목(IRIS·bizinfo CI skip 최적화 여지), is_tech LLM화(TODOS), 마감/첨부 파싱 2단계(TODOS), msit/nara v1 추출 제외(TODOS).

## 비고 / 검증 커맨드

- 테스트: `PYTHONUTF8=1 python tests/test_pipeline.py` → 68 OK(유료 EVAL 1 skip).
- 로컬 bizinfo 라이브 실호출: `.env`에서 `BIZINFO_CRTFC_KEY` 로드(따옴표 제거) → `BizinfoAdapter(max_pages=1).collect()` (국내 IP 0.3s 성공).
- data 신선도 점검: `git show origin/data:gov_notices.db > gnd_check.db` → sqlite `select source, max(last_seen) from notices group by source`.
- 수동 런: `gh workflow run collect.yml -f no_notify=true --ref main`.
