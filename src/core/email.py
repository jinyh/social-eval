from __future__ import annotations

import asyncio
import html
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import aiosmtplib
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.field_encryption import decrypt_field, encrypt_field
from src.core.logging import logger
from src.core.time import utc_now
from src.models.editorial import EmailDelivery


EVENT_CONTENT: dict[str, tuple[str, str]] = {
    "invitation_created": (
        "账户邀请",
        "管理员已邀请你加入文科论文智能辅助评审系统。",
    ),
    "expert_review_assigned": (
        "专家复核任务",
        "你有一项新的专家复核任务，请登录系统查看匿名稿。",
    ),
    "editorial_review_ready": (
        "编辑预审材料已就绪",
        "一项稿件的智能辅助预审材料已经生成，请登录系统处理。",
    ),
    "editorial_review_failed": (
        "编辑预审处理失败",
        "一项稿件处理失败，已进入可恢复状态，请登录系统查看。",
    ),
    "expert_review_submitted": (
        "专家复核已提交",
        "已分配专家完成复核，请登录系统查看结果。",
    ),
    "responsible_editor_transferred": (
        "责任编辑任务已转移",
        "一项稿件已转交给你负责，请登录系统查看。",
    ),
    "password_reset_requested": (
        "重置账户密码",
        "我们收到了你的密码重置请求。如非本人操作，请忽略本邮件。",
    ),
    "password_changed": (
        "账户密码已更新",
        "你的账户密码已经更新。如非本人操作，请立即联系系统管理员。",
    ),
    "account_status_changed": (
        "账户状态已更新",
        "你的账户状态已由管理员更新，请联系管理员了解详情。",
    ),
}


def _safe_error(exc: Exception) -> str:
    """保留错误类型和短消息，不把 SMTP 凭据写入数据库。"""

    text = str(exc)
    if settings.smtp_password:
        text = text.replace(settings.smtp_password, "[已脱敏]")
    return f"{exc.__class__.__name__}: {text}"[:1000]


def _login_url(event_type: str, template_data: dict) -> str:
    base = settings.public_base_url.rstrip("/")
    encrypted_token = str(template_data.get("token_encrypted", ""))
    token = decrypt_field(encrypted_token) if encrypted_token else ""
    if event_type == "invitation_created":
        return f"{base}/activate#token={token}"
    if event_type == "password_reset_requested":
        return f"{base}/reset-password#token={token}"
    return base


def _render_message(delivery: EmailDelivery) -> EmailMessage:
    subject, body = EVENT_CONTENT.get(
        delivery.event_type,
        ("系统通知", "你有一项新的系统通知，请登录系统查看。"),
    )
    template_data = dict(delivery.template_data or {})
    system_id = str(template_data.get("system_id") or delivery.object_id)
    link = _login_url(delivery.event_type, template_data)
    lines = [body]
    if delivery.event_type != "invitation_created":
        lines.append(f"系统稿号：{system_id}")
    if template_data.get("expires_at"):
        lines.append(f"邀请有效期至：{template_data['expires_at']}")
    lines.extend([f"登录地址：{link}", "", "本邮件不包含稿件正文、评分或审稿意见。"])
    text_body = "\n".join(lines)

    message = EmailMessage()
    message["Subject"] = f"【文科论文智能辅助评审系统】{subject}"
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from))
    message["To"] = delivery.recipient_email
    domain = settings.smtp_from.rpartition("@")[2] or "socialeval.local"
    message_id = make_msgid(idstring=delivery.id, domain=domain)
    message["Message-ID"] = message_id
    message.set_content(text_body)
    message.add_alternative(
        "<html><body>"
        + "".join(f"<p>{html.escape(line)}</p>" for line in lines if line)
        + f'<p><a href="{html.escape(link)}">登录系统</a></p>'
        + "</body></html>",
        subtype="html",
    )
    return message


def queue_email(
    db: Session,
    *,
    idempotency_key: str,
    event_type: str,
    recipient_email: str,
    object_type: str,
    object_id: str,
    template_data: dict | None = None,
) -> EmailDelivery:
    """幂等创建邮件投递；禁用邮件时仍保留可审计记录。"""

    existing = (
        db.query(EmailDelivery)
        .filter(EmailDelivery.idempotency_key == idempotency_key)
        .first()
    )
    if existing is not None:
        return existing
    safe_template_data = dict(template_data or {})
    raw_token = safe_template_data.pop("token", None)
    if raw_token:
        safe_template_data["token_encrypted"] = encrypt_field(str(raw_token))
    delivery = EmailDelivery(
        idempotency_key=idempotency_key,
        event_type=event_type,
        recipient_email=recipient_email,
        object_type=object_type,
        object_id=object_id,
        template_data=safe_template_data,
        status="queued" if settings.email_enabled else "disabled",
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    if settings.email_enabled:
        from src.tasks.email_task import dispatch_email_delivery

        dispatch_email_delivery(delivery.id)
    return delivery


async def deliver_email(delivery_id: str, db: Session) -> EmailDelivery:
    """向 SMTP 服务器提交一封已排队邮件。"""

    delivery = db.get(EmailDelivery, delivery_id)
    if delivery is None:
        raise ValueError("未找到邮件投递记录")
    if delivery.status == "accepted":
        return delivery
    if not settings.email_enabled:
        delivery.status = "disabled"
        db.commit()
        return delivery
    if not settings.smtp_host:
        raise RuntimeError("启用邮件后必须配置 SMTP_HOST")
    if settings.smtp_ssl and settings.smtp_starttls:
        raise RuntimeError("SMTP_SSL 与 SMTP_STARTTLS 不能同时启用")

    delivery.status = "sending"
    delivery.attempt_count += 1
    delivery.last_error = None
    db.commit()
    message = _render_message(delivery)
    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            use_tls=settings.smtp_ssl,
            start_tls=settings.smtp_starttls,
            timeout=settings.smtp_timeout,
        )
    except Exception as exc:
        delivery.status = "failed"
        delivery.last_error = _safe_error(exc)
        db.commit()
        raise
    delivery.status = "accepted"
    if delivery.template_data and "token_encrypted" in delivery.template_data:
        delivery.template_data = {
            key: value
            for key, value in delivery.template_data.items()
            if key != "token_encrypted"
        }
    delivery.provider_message_id = str(message["Message-ID"])
    delivery.accepted_at = utc_now()
    delivery.next_attempt_at = None
    db.commit()
    db.refresh(delivery)
    return delivery


def send_review_assignment_email(
    *,
    expert_email: str,
    task_id: str,
    paper_title: str,
    summary: str,
    db: Session | None = None,
) -> EmailDelivery | None:
    """兼容既有调用；邮件正文不使用标题或摘要。"""

    del paper_title, summary
    if db is None:
        logger.info("专家复核邮件未入队：缺少数据库会话")
        return None
    return queue_email(
        db,
        idempotency_key=f"expert-review-assigned:{task_id}:{expert_email.lower()}",
        event_type="expert_review_assigned",
        recipient_email=expert_email,
        object_type="evaluation_task",
        object_id=task_id,
        template_data={"system_id": task_id},
    )


def send_editorial_event_email(
    *,
    recipient_email: str,
    submission_id: str,
    event_type: str,
    db: Session | None = None,
) -> EmailDelivery | None:
    """发送不含标题、正文、评分或审稿意见的编辑事件通知。"""

    if db is None:
        logger.info("编辑事件邮件未入队：缺少数据库会话")
        return None
    return queue_email(
        db,
        idempotency_key=f"{event_type}:{submission_id}:{recipient_email.lower()}",
        event_type=event_type,
        recipient_email=recipient_email,
        object_type="editorial_submission",
        object_id=submission_id,
        template_data={"system_id": submission_id},
    )


def deliver_email_sync(delivery_id: str, db: Session) -> EmailDelivery:
    return asyncio.run(deliver_email(delivery_id, db))
