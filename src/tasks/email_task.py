from __future__ import annotations

from datetime import timedelta

from src.core.database import SessionLocal
from src.core.email import deliver_email_sync
from src.core.time import utc_now
from src.models.editorial import EmailDelivery
from src.tasks.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="socialeval.send_email_delivery",
    max_retries=3,
)
def send_email_delivery(self, delivery_id: str) -> None:
    db = SessionLocal()
    try:
        deliver_email_sync(delivery_id, db)
    except Exception as exc:
        countdown = (60, 300, 1800)[min(self.request.retries, 2)]
        delivery = db.get(EmailDelivery, delivery_id)
        if delivery is not None:
            delivery.next_attempt_at = utc_now() + timedelta(seconds=countdown)
            db.commit()
        raise self.retry(exc=exc, countdown=countdown)
    finally:
        db.close()


def dispatch_email_delivery(delivery_id: str) -> None:
    send_email_delivery.delay(delivery_id)
