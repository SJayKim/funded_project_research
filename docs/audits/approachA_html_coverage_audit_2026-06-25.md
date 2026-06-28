# Approach A — HTML 커버리지 손작업 감사 + CI fetch 실측 (P0)

> 다음작업 1번 산출물 (2026-06-25). 설계문서
> `~/.gstack/projects/SJayKim-funded_project_research/sjkim-main-design-approachA-20260625-100441.md`의
> "7. 다음 작업 1번"을 수행. 4 추출소스(kstartup·bizinfo·msit·iris)에서 기술공고를 source 층화로
> 열어 4필드(funding_amount·eligibility·required_docs·key_dates)가 **상세 HTML 본문에 실제로
> 있는지** 실측. nara는 추출 제외(입찰=파일다운로드 URL, HTML 본문 없음).
>
> 측정 방법: stdlib `urllib` + Linux Chrome UA + 쿠키 없음 (= CI 환경 모사). script/style 제거 후
> 본문 텍스트만 평가. 소스당 2건씩(n=2) 패턴 일관성 확인.

## 0. 한 줄 결론

**HTML-first는 4소스 중 3소스(kstartup·bizinfo·iris)에서 유효, msit은 본문이 HWP 첨부에만 있어
거의 무가치.** iris는 커버리지 최상이나 CI(해외 Actions IP) fetch 차단이 텐션 → CI 실측 필요.

## 1. 소스별 HTML 커버리지 (핵심 표)

| source | 본문 visible chars | 금액 | 자격 | 서류 | 일정 | HTML-first 판정 |
|--------|------:|:----:|:----:|:----:|:----:|------|
| **kstartup** | ~5,000–6,000 | △ | ○ | ○ | ○ | **양호** — 구조화 필드, 본문 풍부 |
| **bizinfo** | ~2,100 | ○ | ○(산문) | △ | ○ | **중상** — 금액·자격·일정 산문형, 상세 서류는 공고문.pdf |
| **iris** | ~2,700–3,700 | ○ | ○ | ○ | ○ | **최상** — 구조화 필드 + **공고문 전문 인라인** |
| **msit** | ~3,700(대부분 네비) | △ | ✕ | ✕ | ✕ | **불가** — 본문엔 도입부+서명만, 4필드 전체가 HWP/HWPX 첨부 안 |

○=본문에서 추출 가능, △=부분/산문에 섞임, ✕=HTML에 없음(첨부에만)

### 소스별 관찰 근거
- **kstartup** (172700, 172689): `접수기간`·`신청대상`·`제출서류`·`신청방법`·`예산/지원내용` 라벨이
  본문에 구조적으로 노출. HTML만으로 4필드 대부분 확보.
- **bizinfo** (101596, 101599): `신청기간`·`소관부처`·`사업수행기관`·`사업개요`는 구조화. 금액·자격은
  산문형("최대 50백만원 한도", "국내 로봇산업 중소·중견기업 단독 또는 컨소시엄"). 상세 제출서류는
  `공고문.pdf`/`첨부파일.zip`에. LLM이 산문에서 뽑아야 함(라벨 매칭 불가).
- **iris** (021938, 021934): `소관부처`·`전문기관`·`공고번호`·`접수기간` 구조화 + **"■ 공고문" 이하
  공고 전문이 HTML에 그대로 박혀 있음**. 4필드 커버리지 최상.
- **msit** (3179651, 3179653): 본문 visible 3,700자 중 대부분이 네비게이션 메뉴. 실제 공고 영역엔
  제목·소관부서·담당자·작성일 + 도입 문단 + "장관" 서명까지만. 그 다음 바로 첨부
  (`...공고문.hwpx`/`.hwp`/`.odt`, `공모안내서.zip`). **4필드 본문 = 0** (첨부확장자 10회 언급).

## 2. 설계 함의 (HTML-first 결정 재검증)

설계의 "이슈1: HTML 본문만, PDF/HWP 2단계" 결정은 **3/4 소스에서 성립**. 단:

1. **msit은 HTML-first 효용 ≈ 0.** v1에서 msit 추출은 제목/기관/일정(이미 base 컬럼에 있음) 외
   신규 4필드를 사실상 못 채움. → 옵션:
   - (a) msit을 v1 추출 대상에서 **잠정 제외**(nara처럼), 2단계 HWP 파싱 때 합류. **(권장)**
   - (b) msit만 첨부 HWP 파싱을 1순위로 당김(설계의 "HWP 함정 회피"와 충돌 → 비권장).
2. **bizinfo 금액·자격은 라벨이 아니라 산문에 있음.** extract 프롬프트는 라벨 매칭이 아니라
   "본문 전체에서 의미 추출 + 원문 substring 보존" 방식이어야 함(설계의 substring 검증과 정합).
3. **iris가 가장 추출 가치 높음** (공고문 전문 인라인) — 그런데 CI fetch가 막히면 가치 0. §3 참조.

## 3. CI fetch 실측 (미완 — 사용자 dispatch 필요)

- **로컬(한국 IP) 결과**: 4소스 전부 stdlib + Linux UA + 쿠키 없음으로 `status 200` fetch 성공.
- **그러나 IRIS는 로컬이 한국 IP라 성공한 것**. 메모리 실측 기록(2026-06-23): 해외 GitHub Actions
  IP는 `www.iris.go.kr` 연결 차단. **로컬 성공이 CI 성공을 보장하지 않음.**
- 진짜 검증은 GitHub Actions 러너(해외 IP)에서 동일 fetch를 돌려보는 것뿐. gh CLI 미설치라 본
  세션에서 Actions 로그 관측 불가 → **probe 워크플로를 추가했으니 사용자가 dispatch 후 로그 확인**.

### probe 실행 방법
`.github/workflows/fetch_probe.yml` 추가됨 (workflow_dispatch 전용, 일일 런과 분리).
GitHub → Actions → "fetch-probe" → Run workflow. 로그에서 소스별 `status`/`bytes`/차단 여부 확인.

### probe 결과에 따른 분기
- iris도 CI에서 200 → 4소스(−msit) 정상 진행.
- **iris CI 차단 확인 시**: iris 추출은 (a) data.go.kr IRIS API에 본문 필드가 있나 재확인, 또는
  (b) iris를 추출 제외로 강등. 본 감사로는 결론 못 냄(IP 의존).

## 4. EVAL fixture (extract 프롬프트 회귀 평가셋)

source 층화, 소스당 2건. **golden = 사람이 본문에서 확인한 값**. msit은 "HTML에 없음"이 golden.

| # | source | id | golden funding_amount | golden eligibility | golden required_docs | golden key_dates | extraction_status(기대) |
|---|--------|----|----|----|----|----|----|
| 1 | kstartup | 172700 | (본문 지원내용 발췌) | 신청대상 발췌 | 제출서류 발췌 | 접수기간 발췌 | ok |
| 2 | kstartup | 172689 | (없으면 no_info) | 신청대상/중소기업 | 제출서류·신청서 | 접수기간 | ok |
| 3 | bizinfo | 101596 | 최대 50백만원 한도 | 국내 로봇 중소·중견 단독/컨소시엄 | (서류는 PDF→no_info) | 2024.09.20~2024.10.04 | ok |
| 4 | bizinfo | 101599 | (백만원 단위 발췌) | (산문) | 신청서 | 신청기간 | ok |
| 5 | iris | 021938 | (지원규모 발췌) | 지원대상 발췌 | 제출서류 발췌 | 2026-06-08~2026-06-25 | ok |
| 6 | iris | 021934 | 지원규모 발췌 | 중소기업 | 제출서류 | 접수기간 | ok |
| 7 | msit | 3179651 | "" | "" | "" | "" | **no_info** (전부 HWP) |
| 8 | msit | 3179653 | "" | "" | "" | "" | **no_info** (전부 HWP) |

> 구현 시 각 행의 golden 값을 실제 본문에서 정확히 채워 `tests/fixtures/extract/`에 저장.
> 평가 지표: 필드별 (a) substring이 원문에 실재하나, (b) 사람 golden과 의미 일치하나.
> #7,#8은 "환각 안 하고 no_info 반환"을 검증하는 **음성 케이스**(중요).

## 5. extract 프롬프트 초안 (tool_use)

```
시스템: 너는 한국 정부 지원사업/R&D 공고 본문에서 4개 항목을 추출한다.
규칙:
- 입력은 공고 상세페이지의 본문 텍스트다. 네비게이션·푸터·해시태그는 무시한다.
- 각 값은 반드시 본문에 그대로 등장하는 표현을 발췌(인용)한다. 추론·요약·환각 금지.
- 본문에 해당 정보가 없으면 그 필드는 빈 문자열 ""로 둔다. (대부분 첨부 PDF/HWP에만 있는 경우 흔함)
- 금액은 숫자+단위 그대로(예: "최대 50백만원 한도"), 일정은 기간 그대로(예: "2026-06-08 ~ 2026-06-25").

tool: extract_notice_fields
  funding_amount: string  # 지원금액/지원규모/예산. 없으면 ""
  eligibility:    string  # 신청자격/신청대상. 없으면 ""
  required_docs:  string  # 제출서류/신청방법. 없으면 ""
  key_dates:      string  # 접수/신청 기간·마감. 없으면 ""
```

- 구현 시 **Opus 4.8 body에 tools 허용 여부 재검증**(설계 이슈2 미해결). 안 되면 모델 폴백 또는
  JSON 강제 프롬프트.
- 4필드 전부 ""면 호출부에서 `extraction_status="no_info"`, 1+ 채워지면 `ok`, 예외면 `failed`.
- 추출 후 각 값 원문 substring 검증(설계 §5) 통과분만 저장.

## 6. 다음 단계로 넘기는 결정/TODO
- [x] **msit v1 추출 제외 확정** (제외, 2단계 HWP 합류). 설계 doc §1·§3·§6 + TODOS 반영 완료(2026-06-25).
- [ ] **iris CI fetch 실측** (probe dispatch) → 차단 시 iris 추출 경로 재설계.
- [ ] EVAL fixture golden 값 정밀 기입 (`tests/fixtures/extract/`).
- [ ] extract 프롬프트 tools-on-body 재검증.
- 이후 구현은 설계 §7-2 순서(공용 헬퍼 → extract.py → 스키마 6필드 → enrich 2단계 → serve.py 카드).
