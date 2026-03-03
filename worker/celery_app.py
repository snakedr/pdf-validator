from celery import Celery
from celery.schedules import crontab
import os
from dotenv import load_dotenv

load_dotenv()

# Celery configuration
celery_app = Celery(
    "worker",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    include=[
        "email_client",
        "attachment_processor", 
        "pdf_validator",
        "email_sender",
        "maintenance",
    ]
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    beat_schedule={
        "cleanup-every-morning": {
            "task": "maintenance.cleanup_old_files_task",
            "schedule": crontab(minute=0, hour=3),  # каждый день в 03:00
        },
        "check-emails-scheduled": {
            "task": "email_client.fetch_emails_task",
            "schedule": crontab(minute='*/2'),  # every hour from 9:00 to 23:00 Moscow (UTC 6-20)
        },
    },
    beat_schedule_filename="/tmp/celerybeat-schedule",
)

# Database settings (same as backend)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/email_processor")

# Email settings
IMAP_SERVER = os.getenv("IMAP_SERVER")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# AI/ML Provider Configuration (OpenAI-compatible API)
AI_API_KEY = os.getenv("AI_API_KEY")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")

# Backward compatibility
OPENAI_API_KEY = AI_API_KEY

# Storage
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
MAX_PDF_SIZE_MB = int(os.getenv("MAX_PDF_SIZE_MB", "50"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "json")
