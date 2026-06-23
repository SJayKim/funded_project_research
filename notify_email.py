"""이메일(SMTP) 알림 디스패처: 신규 / 마감 임박 / 수정.

자격증명·수신자는 환경변수(Actions Secrets). 미설정 시 RuntimeError.
메시지 빌드(순수)와 발송(I/O)을 분리해 테스트 가능하게 한다.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from diff import Modified
from normalize import NoticeRecord


def _line(rec: NoticeRecord) -> str:
    # 형식: 제목 · 요약 · 마감 + 출처 URL(둘째 줄). 요약 없으면 제목으로 대체.
    summary = rec.summary or rec.title
    deadline = rec.deadline or "(마감일 없음)"
    return f"- {rec.title} · {summary} · 마감 {deadline}\n  {rec.url}"


def build_message(
    new: list[NoticeRecord],
    imminent: list[tuple[NoticeRecord, int]],
    modified: list[Modified],
) -> tuple[str, str] | None:
    """알림할 내용이 있으면 (subject, body), 없으면 None."""
    if not (new or imminent or modified):
        return None

    parts: list[str] = []
    if new:
        parts.append(f"[신규 공고 {len(new)}건]")
        parts += [_line(r) for r in new]
    if imminent:
        parts.append(f"\n[마감 임박 {len(imminent)}건]")
        parts += [f"- D-{d} {_line(r)[2:]}" for r, d in imminent]
    if modified:
        parts.append(f"\n[수정 감지 {len(modified)}건]")
        for m in modified:
            chg = ", ".join(f"{c.field}: {c.old or '∅'}→{c.new or '∅'}" for c in m.changes)
            parts.append(f"- {m.record.title} | {m.record.url}\n    {chg}")

    subject = f"[정부과제] 신규 {len(new)} · 임박 {len(imminent)} · 수정 {len(modified)}"
    return subject, "\n".join(parts)


def send(subject: str, body: str, transport=None) -> None:
    """transport는 테스트용 주입(EmailMessage를 받는 콜러블). 기본은 SMTP_SSL."""
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    mail_from = os.environ.get("MAIL_FROM", user or "")
    mail_to = os.environ.get("MAIL_TO", "")
    if not (host and user and password and mail_to):
        raise RuntimeError("SMTP 자격증명/수신자 미설정 (SMTP_HOST/SMTP_USER/SMTP_PASS/MAIL_TO)")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg.set_content(body)

    if transport is not None:
        transport(msg)
        return
    with smtplib.SMTP_SSL(host, port) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
