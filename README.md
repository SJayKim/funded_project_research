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
# 테스트 (외부 API·실제 메일·유료 LLM 호출 없음)
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

## 대시보드 화면과 배포

지원·사업 공고와 입찰을 구분하고 제목·기관·요약·검증된 발췌를 검색합니다.
분야·출처·마감 포함 필터, 표/카드 보기, 목록 안 상세 펼침을 제공하며 결과는
가까운 마감순으로 50건씩 표시합니다. 마감 정보가 없으면 `마감 미확인`으로
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
