"""§6 기술분야 키워드 분류기(stdlib, 순수 함수). category + is_tech 결정.

dict 선언 순서대로 첫 매칭 승(결정적). 한 개도 매칭 안 되면 ("기타","0").
교착어라 한글은 부분문자열 in으로, 영문 토큰(AI/SaaS)은 .lower()로 매칭한다.
"""
from __future__ import annotations

from normalize import NoticeRecord

# §6 일반 기술 분야 10개 + 세부 키워드(전부 소문자).
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "AI/생성형AI": ("ai", "인공지능", "생성형", "llm", "agent", "에이전트", "rag", "딥러닝", "머신러닝"),
    "데이터": ("데이터", "빅데이터", "마이데이터", "합성데이터"),
    "클라우드/SaaS": ("saas", "클라우드", "cloud"),
    "보안": ("보안", "개인정보", "제로트러스트", "정보보호", "사이버"),
    "제조AI": ("스마트팩토리", "스마트공장", "예지보전", "품질검사", "공정혁신"),
    "헬스케어AI": ("의료영상", "디지털헬스", "헬스케어", "의료기기", "바이오", "임상"),
    "금융AI": ("이상거래", "리스크관리", "핀테크", "문서자동화"),
    "로봇/자율주행": ("로봇", "자율주행", "경로계획", "드론"),
    "콘텐츠/미디어": ("콘텐츠", "저작권", "버추얼휴먼", "메타버스"),
    "공공/안전": ("재난", "치안", "국방", "사회문제"),
}


def _haystack(rec: NoticeRecord) -> str:
    # agency 제외: 키워드를 품은 기관명(예: 인공지능산업진흥원)이 전건을
    # 기술로 오분류시키는 것을 막는다. 제목+신청대상만으로 판정.
    return f"{rec.title} {rec.target}".lower()


def classify(rec: NoticeRecord) -> tuple[str, str]:
    text = _haystack(rec)
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return category, "1"
    return "기타", "0"
