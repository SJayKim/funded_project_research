"""실발송 1회 검증(블로커 6). 샘플 '신규 공고' 1건을 실제 SMTP로 발송한다.

자격증명은 환경변수로만 받는다(파일 저장 안 함):
  SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASS MAIL_FROM MAIL_TO
실행 후 MAIL_TO 수신함에 메일 1건이 도착하면 acceptance #2 통과.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import notify_email
from normalize import NoticeRecord

sample = NoticeRecord(
    source="kstartup",
    source_id="178198",
    title="2026년도 딥테크 특화 창업중심대학 창업기업 모집공고",
    url="https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=178198",
    agency="중소벤처기업부",
    deadline="2026-07-08",
)

msg = notify_email.build_message([sample], [], [])
if msg is None:
    print("메시지 없음")
    sys.exit(1)

subject, body = msg
notify_email.send(subject, body)
print(f"발송 완료 → {os.environ.get('MAIL_TO')}")
print(f"제목: {subject}")
print(body)
