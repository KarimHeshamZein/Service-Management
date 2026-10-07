"""Create in-app notifications and optionally deliver them through configured SMTP."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .account_recovery import MailDeliveryError, send_email
from .config import settings
from .models import NotificationEmailStatus, User, UserNotification, utcnow


def create_notification(
    db: Session,
    *,
    user: User,
    kind: str,
    title: str,
    message: str,
    target_url: str | None = None,
    department_id: int | None = None,
    task_id: int | None = None,
) -> UserNotification:
    should_email = bool(user.email and user.email_notifications and settings.email_delivery_configured)
    notification = UserNotification(
        user_id=user.id,
        department_id=department_id,
        task_id=task_id,
        kind=kind,
        title=title,
        message=message,
        target_url=target_url,
        email_status=(
            NotificationEmailStatus.PENDING
            if should_email
            else NotificationEmailStatus.NOT_REQUESTED
        ),
    )
    db.add(notification)
    db.flush()
    return notification


def deliver_notification_email(db: Session, notification: UserNotification, user: User) -> None:
    if notification.email_status != NotificationEmailStatus.PENDING or not user.email:
        return
    notification.email_attempted_at = utcnow()
    link = f"{settings.public_base_url}{notification.target_url}" if notification.target_url else settings.public_base_url
    try:
        send_email(
            user.email,
            f"{settings.app_name}: {notification.title}",
            f"{notification.message}\n\nOpen in {settings.app_name}:\n{link}",
        )
    except MailDeliveryError as exc:
        notification.email_status = NotificationEmailStatus.FAILED
        notification.email_error = str(exc)
    else:
        notification.email_status = NotificationEmailStatus.SENT
        notification.email_sent_at = utcnow()
        notification.email_error = None
    db.commit()
