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
# 테스트
python -m unittest

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
