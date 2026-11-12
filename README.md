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
6. 복구 DB를 다시 검사하고 테스트·정적 빌드를 확인한 뒤 수집 일정을 재개합니다. 이번 Phase 0은 스키마를 바꾸지 않으므로 코드만 되돌릴 때 DB 이행은 필요하지 않습니다.

현재 구현·검증과 다음 단계는 [현재 인계](docs/sessions/HANDOFF-CURRENT.md)를 참고하세요.

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
