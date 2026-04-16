from celery import Celery

from src.core.config import settings


celery_app = Celery(
    "socialeval",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.task_ignore_result = True
