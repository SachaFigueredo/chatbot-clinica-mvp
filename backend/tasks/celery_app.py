from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings

# ---------------------------------------------------------------------------
# Celery application — recordatorios automáticos y tareas background
# ---------------------------------------------------------------------------

celery_app = Celery(
    "chatbot_clinica",
    broker=settings.celery_broker_url,
    backend=settings.celery_broker_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Argentina/Buenos_Aires",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# ---------------------------------------------------------------------------
# Auto-discover tasks from the ``tasks`` package
# ---------------------------------------------------------------------------

celery_app.autodiscover_tasks(["tasks"], force=True)

# ---------------------------------------------------------------------------
# Beat schedule — runs every 30 minutes
# ---------------------------------------------------------------------------
# Each task uses a 1-hour lookup window, so every appointment is caught by
# at least one beat execution.  The flag columns (reminder_1_sent,
# reminder_2_sent) prevent duplicate sends.
# ---------------------------------------------------------------------------

celery_app.conf.beat_schedule = {
    "send-reminder-1": {
        "task": "tasks.reminders.send_reminder_1",
        "schedule": crontab(minute="*/30"),
    },
    "send-reminder-2": {
        "task": "tasks.reminders.send_reminder_2",
        "schedule": crontab(minute="*/30"),
    },
}
