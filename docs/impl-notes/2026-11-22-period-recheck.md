# 2026-11-22 기업마당 신청기간 재확인

[11월 15일 운영 실행](https://github.com/SJayKim/funded_project_research/actions/runs/43676448137)의 원문 재확인 결과 중 `period_missing` 59건을 대상으로 삼았다. 당시 보고서와 수집 전 DB 스냅샷의 공고 키를 대조해 원문 URL을 확인하고, 11월 22일 각 상세 페이지의 구조화된 신청기간 필드를 다시 읽었다. 아래 확인 시각은 한국 표준시다.

원문을 59건 모두 읽었다. 고정 날짜 없이 조건을 명시한 공고는 56건이다. 원문 표현별로 `예산 소진시까지` 32건, `상시 접수` 17건, `모집 완료시까지` 4건, `모집 완료시` 3건이다. 확인 범위는 원문 표현이며, 예산 잔액과 실제 접수 여부는 해당 기관에서 확인해야 한다.

나머지 3건은 세부사업별, 차수별, 접수방법별로 기간이 달라 사람이 대상 사업과 조건을 골라 원문을 확인해야 한다. 구조화된 필드에서 단일 고정 날짜, 첨부파일 전용 기간, 상충, 필드 부재 또는 접근 실패로 분류된 사례는 없었다.

## 운영 판정 제안

- 실패에는 실제 수집 중단·누락, 원문 접근 실패, 데이터 손상, 배포 실패를 포함한다.
- 주의에는 기간 상충, 첨부파일 확인 필요, 사업·차수·접수방법별 상이를 포함하고 원문 링크로 수동 확인을 유도한다.
- 안내에는 원문에서 구조적으로 확인된 조건부 마감을 포함하고 원문 문구와 확인 시각을 표시한다.

2026-11-23 프로젝트 책임자가 운영 기준을 승인했다. 원문에서 확인한 조건부 마감은 안내, 사업별 기간 차이·상충·첨부 확인 필요는 주의로 분류한다. 실제 수집 누락·접근 실패·데이터 손상·배포 실패는 CI 실패를 유지한다. 적용 조건과 검증은 [후속 기록](2026-11-23-reliability-resolution.md)에 남겼다.

## 공고별 근거

| 기업마당 원문 | 원문의 신청기간 | 분류 | 확인 시각 (KST) |
| --- | --- | --- | --- |
| [PBLN_000000000117676](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117676) | 세부사업별 상이 | 수동 확인 필요 | 21:30:54 |
| [PBLN_000000000117839](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117839) | 차수별 상이 | 수동 확인 필요 | 21:30:57 |
| [PBLN_000000000126928](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000126928) | 접수방법별 상이 | 수동 확인 필요 | 21:30:51 |
| [PBLN_000000000109049](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000109049) | 상시 접수 | 조건부 마감 | 21:30:53 |
| [PBLN_000000000117371](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117371) | 예산 소진시까지 | 조건부 마감 | 21:30:53 |
| [PBLN_000000000117481](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117481) | 상시 접수 | 조건부 마감 | 21:30:53 |
| [PBLN_000000000117664](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117664) | 예산 소진시까지 | 조건부 마감 | 21:30:54 |
| [PBLN_000000000117666](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117666) | 예산 소진시까지 | 조건부 마감 | 21:30:54 |
| [PBLN_000000000117668](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117668) | 상시 접수 | 조건부 마감 | 21:30:54 |
| [PBLN_000000000117671](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117671) | 예산 소진시까지 | 조건부 마감 | 21:30:54 |
| [PBLN_000000000117673](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117673) | 예산 소진시까지 | 조건부 마감 | 21:30:54 |
| [PBLN_000000000117679](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117679) | 예산 소진시까지 | 조건부 마감 | 21:30:55 |
| [PBLN_000000000117688](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117688) | 예산 소진시까지 | 조건부 마감 | 21:30:55 |
| [PBLN_000000000117702](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117702) | 예산 소진시까지 | 조건부 마감 | 21:30:55 |
| [PBLN_000000000117708](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117708) | 예산 소진시까지 | 조건부 마감 | 21:30:55 |
| [PBLN_000000000117711](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117711) | 예산 소진시까지 | 조건부 마감 | 21:30:55 |
| [PBLN_000000000117722](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117722) | 예산 소진시까지 | 조건부 마감 | 21:30:55 |
| [PBLN_000000000117727](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117727) | 예산 소진시까지 | 조건부 마감 | 21:30:55 |
| [PBLN_000000000117728](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117728) | 예산 소진시까지 | 조건부 마감 | 21:30:55 |
| [PBLN_000000000117736](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117736) | 예산 소진시까지 | 조건부 마감 | 21:30:56 |
| [PBLN_000000000117751](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117751) | 예산 소진시까지 | 조건부 마감 | 21:30:56 |
| [PBLN_000000000117768](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117768) | 예산 소진시까지 | 조건부 마감 | 21:30:56 |
| [PBLN_000000000117770](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117770) | 예산 소진시까지 | 조건부 마감 | 21:30:56 |
| [PBLN_000000000117781](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117781) | 예산 소진시까지 | 조건부 마감 | 21:30:53 |
| [PBLN_000000000117782](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117782) | 상시 접수 | 조건부 마감 | 21:30:56 |
| [PBLN_000000000117791](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117791) | 예산 소진시까지 | 조건부 마감 | 21:30:56 |
| [PBLN_000000000117794](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117794) | 상시 접수 | 조건부 마감 | 21:30:56 |
| [PBLN_000000000117800](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117800) | 상시 접수 | 조건부 마감 | 21:30:56 |
| [PBLN_000000000117805](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117805) | 예산 소진시까지 | 조건부 마감 | 21:30:56 |
| [PBLN_000000000117879](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000117879) | 예산 소진시까지 | 조건부 마감 | 21:30:57 |
| [PBLN_000000000118006](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000118006) | 예산 소진시까지 | 조건부 마감 | 21:30:53 |
| [PBLN_000000000118617](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000118617) | 상시 접수 | 조건부 마감 | 21:30:53 |
| [PBLN_000000000119124](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000119124) | 예산 소진시까지 | 조건부 마감 | 21:30:54 |
| [PBLN_000000000119154](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000119154) | 상시 접수 | 조건부 마감 | 21:30:54 |
| [PBLN_000000000126213](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000126213) | 예산 소진시까지 | 조건부 마감 | 21:30:50 |
| [PBLN_000000000126412](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000126412) | 상시 접수 | 조건부 마감 | 21:30:50 |
| [PBLN_000000000126504](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000126504) | 예산 소진시까지 | 조건부 마감 | 21:30:50 |
| [PBLN_000000000126552](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000126552) | 상시 접수 | 조건부 마감 | 21:30:50 |
| [PBLN_000000000126667](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000126667) | 상시 접수 | 조건부 마감 | 21:30:51 |
| [PBLN_000000000126739](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000126739) | 모집 완료시 | 조건부 마감 | 21:30:51 |
| [PBLN_000000000126754](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000126754) | 예산 소진시까지 | 조건부 마감 | 21:30:51 |
| [PBLN_000000000126776](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000126776) | 상시 접수 | 조건부 마감 | 21:30:51 |
| [PBLN_000000000126825](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000126825) | 예산 소진시까지 | 조건부 마감 | 21:30:51 |
| [PBLN_000000000126877](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000126877) | 상시 접수 | 조건부 마감 | 21:30:51 |
| [PBLN_000000000126878](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000126878) | 상시 접수 | 조건부 마감 | 21:30:51 |
| [PBLN_000000000126911](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000126911) | 모집 완료시 | 조건부 마감 | 21:30:51 |
| [PBLN_000000000126963](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000126963) | 예산 소진시까지 | 조건부 마감 | 21:30:51 |
| [PBLN_000000000127204](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000127204) | 모집 완료시까지 | 조건부 마감 | 21:30:52 |
| [PBLN_000000000127227](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000127227) | 예산 소진시까지 | 조건부 마감 | 21:30:52 |
| [PBLN_000000000127276](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000127276) | 예산 소진시까지 | 조건부 마감 | 21:30:52 |
| [PBLN_000000000127314](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000127314) | 상시 접수 | 조건부 마감 | 21:30:52 |
| [PBLN_000000000127373](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000127373) | 상시 접수 | 조건부 마감 | 21:30:52 |
| [PBLN_000000000127380](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000127380) | 모집 완료시까지 | 조건부 마감 | 21:30:52 |
| [PBLN_000000000127466](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000127466) | 상시 접수 | 조건부 마감 | 21:30:52 |
| [PBLN_000000000127513](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000127513) | 모집 완료시까지 | 조건부 마감 | 21:30:52 |
| [PBLN_000000000127517](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000127517) | 모집 완료시까지 | 조건부 마감 | 21:30:53 |
| [PBLN_000000000127551](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000127551) | 예산 소진시까지 | 조건부 마감 | 21:30:53 |
| [PBLN_000000000127846](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000127846) | 모집 완료시 | 조건부 마감 | 21:30:53 |
| [PBLN_000000000127847](https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000127847) | 예산 소진시까지 | 조건부 마감 | 21:30:53 |
