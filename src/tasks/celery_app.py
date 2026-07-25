from celery import Celery

from src.core.config import settings


celery_app = Celery(
    "socialeval",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "src.tasks.evaluation_task",
        "src.tasks.editorial_task",
        "src.tasks.email_task",
    ],
)

celery_app.conf.task_ignore_result = True
