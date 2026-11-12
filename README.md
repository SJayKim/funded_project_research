# funded_project_research

정부지원사업 및 정부 R&D 공고를 여러 공식 출처에서 수집해 정규화하고, 신규/변경/마감임박 공고를 알림으로 보내며, SQLite DB 기반의 간단한 대시보드를 제공하는 Python 프로젝트입니다.

## 링크

- 공개 대시보드: <https://sjaykim.github.io/funded_project_research/>
- GitHub 저장소: <https://github.com/SJayKim/funded_project_research>

## 주요 기능

- K-Startup, 기업마당, 과기정통부, 나라장터, IRIS 공고 수집
- 공고 정규화, 중복 제거, 신규/수정/마감임박 감지
- 기술 분야 공고 분류 및 요약
- SMTP 이메일 알림
- SQLite 저장소와 로컬/정적 HTML 대시보드
- GitHub Actions를 통한 매일 자동 수집 및 GitHub Pages 배포

## 구조

```text
funded_project_research/      # 런타임 패키지
funded_project_research/adapters/  # 출처별 수집 어댑터
tests/                        # 테스트와 fixture
samples/                      # 샘플 API 응답
scripts/                      # 보조 스크립트
docs/                         # 조사, 기획, 세션 문서
```

## 실행

Python 3.13 기준입니다. 외부 패키지 의존성 없이 표준 라이브러리 중심으로 동작합니다.

```powershell
# 기본 테스트: 외부 API·실제 SMTP·유료 LLM을 호출하지 않음
python -m unittest discover -s tests -v

# 공고 수집 및 저장
python -m funded_project_research.collect

# 첫 실행처럼 이메일 없이 DB만 채우기
python -m funded_project_research.collect --no-notify

# 로컬 대시보드 실행
python -m funded_project_research.serve

# 정적 대시보드 생성
python -m funded_project_research.serve --build site/index.html

# 추출 평가 실행
python -m funded_project_research.eval_extract
```

대시보드는 기본적으로 `gov_notices.db`를 읽고 `http://127.0.0.1:8000`에서 실행됩니다.

`python -m unittest`만 실행하면 이 저장소의 테스트를 발견하지 못합니다. 기본 검증은
위 `discover` 명령을 사용하세요. 실모델 테스트는 `RUN_LIVE_EVAL=1`과
`ANTHROPIC_API_KEY`가 모두 있을 때만 실행되며 비용이 발생합니다. 일반 CI는 이를 끕니다.
로컬에 Python 3.13이 없고 `uv`가 있다면 같은 명령을
`uv run --no-project --python 3.13 python -m unittest discover -s tests -v`로 실행할 수 있습니다.

## 자동 수집의 DB 보호

- `tests` workflow는 push/PR에서, `collect` workflow는 수집·배포 전에 Python 3.13 테스트를 실행합니다.
- 예약·수동 수집은 `collect-data-pages` concurrency 그룹을 공유하며 실행 중인 작업은 자동 취소하지 않습니다.
- 원격 조회 실패, DB 다운로드 실패, 손상 DB, 필수 테이블·컬럼·기본 키 누락은 수집 전에 실행을 중단합니다. 실패를 빈 DB로 바꿔 진행하지 않습니다.
- 복원한 스냅샷의 무결성·공고/알림 건수를 검사하고 DB 사본과 코드 SHA·data SHA·파일 해시를 `db-baseline-<run_id>-<run_attempt>` artifact에 30일 보관합니다. 백업 업로드가 실패해도 수집하지 않습니다.
- 수집 후에도 DB를 검사한 뒤 `data` 브랜치 저장과 Pages 배포를 진행합니다. 수집 전 테스트/복원 단계가 실패하면 수집·메일·DB 덮어쓰기·배포 단계는 실행되지 않습니다.

이미 `data` 브랜치가 있는 운영 저장소에서는 **`initialize_db`를 사용하지 않습니다**.
진짜 최초 설치에서만 수동 실행의 `initialize_db`를 켜세요. 원격에서 `data` 브랜치가
없다는 사실을 확인해야 초기화하며, 그 실행은 자동으로 `--no-notify`를 적용합니다.
원격 오류나 기존 로컬 DB가 있을 때는 초기화 입력으로도 우회할 수 없습니다.

DB 검사는 읽기 전용이며 파일이 없다고 새로 만들지 않습니다.

```sh
python -m scripts.ci_db validate --db gov_notices.db

# 복원 리허설: 비어 있는 별도 작업 위치에서 실행. 백업 폴더는 매번 새 경로 사용.
python -m scripts.ci_db restore --db gov_notices.db --backup-dir .gstack/db-baseline/run-001
```

기존 DB는 검증과 백업이 모두 성공한 뒤에만 교체됩니다. 기존 스냅샷의 마이그레이션은
복원 검사에서 실행하지 않으며, 기존 `Store`가 수집 시작 시 처리합니다.

### 복원 실패와 복구

1. 실패한 실행의 테스트/복원/백업 단계와 `data` 브랜치 상태를 확인합니다. 인증·네트워크 오류라면 원인을 고친 뒤 기존 DB로 다시 실행합니다. `initialize_db`로 우회하지 않습니다.
2. DB 수동 복구가 필요하면 우선 `collect` workflow를 비활성화하고 실행 중 작업의 종료를 확인합니다. 발송 중인 실행을 취소하거나 병행해 DB를 바꾸지 않습니다.
3. 실패 실행 또는 마지막 검증 실행의 `db-baseline-*` artifact를 별도 폴더에 내려받습니다. `manifest.json`의 코드/data SHA·건수·해시를 확인하고 `python -m scripts.ci_db validate --db <백업>/gov_notices.db` 결과와 대조합니다. artifact 보존 기간이 지났으면 `data` 브랜치 Git 이력의 DB를 별도 파일로 추출해 검사합니다.
4. 해당 백업 이후 수집·메일 발송·알림 이력 변경이 없고 최신 `data` SHA와의 관계를 확인한 경우에만, `data`의 최신 커밋에서 복구 커밋을 만들어 일반 push합니다. 강제 push와 이력 초기화를 하지 않습니다. 건수뿐 아니라 공고 키·`first_seen`·`last_seen`·`alerts`를 대조합니다.
5. 백업 이후 발송이 있었거나 결과가 불명확하면 **과거 DB로 바로 덮지 않습니다**. 최신 알림 이력을 보존·대조한 뒤 복구해야 중복 메일을 막을 수 있습니다. SMTP와 DB 저장 사이의 중단 문제는 이후 Phase 11~12에서 다룹니다.
6. 복구 DB를 다시 검사하고 테스트·정적 빌드를 확인한 뒤 수집 일정을 재개합니다. 코드 되돌림과 데이터 복원은 별개입니다. 신뢰성 배포에서 추가한 컬럼·검증 이력·알림 이력을 코드 되돌림 때문에 삭제하지 않습니다.

현재 구현·검증과 다음 단계는 [현재 인계](docs/sessions/HANDOFF-CURRENT.md)를 참고하세요.

## 정보 신뢰성과 원문 재확인

접수 상태와 D-day는 한국 현재 시각으로 계산합니다. 개별 공고를 확인한 기록이 없거나
48시간이 지나면 `확인 필요`로 표시하며, 마감임박/확인된 마감 전 집계에서 제외합니다.
기존 `last_seen`은 검증 시각으로 소급 사용하지 않습니다. 출처별 수집 응답 완료·정상 0건·
부분 수집·실패는 별도로 저장합니다. 수집 오류가 있으면 기존 데이터와 오류 상태를
배포한 뒤 Actions를 실패로 표시합니다.

기업마당·K-Startup의 구조화된 신청기간은 다음 명령으로 재확인합니다. 기본값은 읽기
전용 dry-run입니다. 운영 적용 전 DB 백업과 변경 결과를 확인하세요. `--apply`는 기간·
검증 근거만 갱신하며 공고 ID·최초수집일·기존 알림 이력을 보존하고 메일을 보내지 않습니다.

```sh
python -m funded_project_research.recheck --db gov_notices.db --limit 20 --report recheck.json
python -m funded_project_research.recheck --db gov_notices.db --limit 20 --apply --report applied.json
```

정기 수집은 순환 대상의 원문 최대 100건을 함께 재확인합니다. 수동 workflow의 `recheck_only=true`는 수집과
발송을 생략하고 재확인·DB 저장·대시보드 배포만 실행합니다. 단위 테스트에는 Node.js가
필요합니다(Python/화면 날짜 규칙의 공통 fixture 실행). [실행안](docs/planning/reliability-release-2026-11-12.md)과
[검증 인계](docs/sessions/reliability-2026-11-12.md)에 범위·미완료 항목을 기록합니다.

출처의 운영 접근 상태만 확인하려면 `python -m funded_project_research.collect --health-only`를
사용합니다. 출처 상태만 저장하고 공고·알림 이력을 유지하며 메일·LLM을 호출하지 않습니다.
수동 workflow의 `health_only=true`는 이 점검 후 원문 재확인과 배포까지 진행합니다.
`recheck_only`와 함께 선택하면 원문 재확인만 실행합니다.

## 자동 신뢰성 점검

매일 09:00 KST 수집 후 검사에 더해, 00:17·06:17·12:17·18:17 KST에 출처와 원문을 점검합니다.
추가 점검은 공고 신규 적재·알림 이력 변경·메일·LLM 호출을 하지 않습니다. 원문 기간과
검증 이력은 근거가 확인될 때 갱신합니다. 원문은 기업마당·K-Startup의 최대 100건을
순환 점검하며, 전체 DB의 날짜·확인 시각·식별자·원문 링크 형식도 검사합니다.

`reliability-watch`는 매시간 43분에 공개 점검 기록을 읽고, 8시간 넘게 갱신되지 않으면
실패로 표시합니다. 대시보드에도 마지막 검사 시각·미확인 건수·점검 지연이 표시됩니다.
매 배포 뒤에는 공개 점검 JSON과 HTML 바이트가 빌드 결과와 일치하는지 검사합니다.
판정과 근거는 DB의 `reliability_checks`, Actions 요약, 30일 보관 artifact에서 확인합니다.
Actions의 개인 알림 수신 설정은 변경하지 않습니다.

```sh
# 같은 점검을 메일 없이 수동 실행 (data 초기화 금지)
gh workflow run collect.yml -f health_only=true -f no_notify=true
# 점검 누락 감시만 실행
gh workflow run reliability-watch.yml
```

점검 빈도·순환 규칙·실패 처리와 한계는 [주기적 점검 인계](docs/impl-notes/2026-11-12-periodic-reliability.md)에 기록합니다.

## 대시보드 화면과 배포

지원·사업 공고와 입찰을 구분하고 제목·기관·요약·검증된 발췌를 검색합니다.
분야·출처·마감 포함 필터, 표/카드 보기, 목록 안 상세 펼침을 제공하며 결과는
가까운 마감순으로 50건씩 표시합니다. 마감 정보가 없으면 `마감 확인 필요`로
남기고 접수중을 추정하지 않습니다. D-day는 브라우저의 한국 현재 시각 기준입니다.

정적 빌드는 `site/index.html`과 `site/assets/`를 함께 생성합니다. Pretendard
v1.3.9는 로컬 폰트 파일로 제공하며 배포 라이선스는
`funded_project_research/assets/pretendard/LICENSE.txt`에 포함합니다.

`dashboard` workflow는 화면 변경을 main에 반영하거나 수동 실행할 때 기존
data 브랜치의 DB를 읽어 Pages만 갱신합니다. 수집·메일 발송·DB 저장은 실행하지
않습니다. 예약 수집 workflow와 같은 실행 그룹을 사용해 배포가 겹치지 않게 합니다.

브라우저 날짜·필터·링크 규칙 테스트는 Node가 있으면 기본 unittest에서 함께
실행하며 CI에는 Node를 설치합니다. Playwright가 설치된 환경에서는 로컬 정적
서버를 띄운 뒤 `node tests/dashboard_browser.cjs http://127.0.0.1:48272/`로
실제 화면·검색·키보드·작은 화면·안전한 텍스트 렌더링도 검사할 수 있습니다.
기록과 스크린샷은 `.gstack/dashboard-verification/`에 저장됩니다.

HTML에는 아직 전체 공고 데이터가 포함됩니다. 50건씩 표시하는 것은 DOM 크기를
제한하는 조치이며 초기 다운로드 용량 분할은 별도 후속 작업입니다.

## 환경변수

필수 또는 선택 환경변수는 다음과 같습니다.

- `SERVICE_KEY`: 공공데이터 API 호출용 서비스 키
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `MAIL_TO`: 이메일 알림 설정
- `MAIL_FROM`: 발신자 주소, 미설정 시 `SMTP_USER` 사용
- `ANTHROPIC_API_KEY`: 요약/상세 추출용 API 키, 없으면 요약은 fallback으로 처리되고 상세 추출은 생략
- `SUMMARIZE_MODEL`, `EXTRACT_MODEL`: 모델 오버라이드
- `GOV_DB`: 대시보드에서 읽을 DB 경로, 기본값 `gov_notices.db`
- `PORT`: 로컬 대시보드 포트, 기본값 `8000`

## 문서

자세한 문서 목록은 [docs/README.md](docs/README.md)를 참고하세요.
