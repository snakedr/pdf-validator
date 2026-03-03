from celery import Celery
from celery.schedules import crontab
from datetime import datetime

from celery_app import celery_app

# Configure Celery Beat schedule
celery_app.conf.beat_schedule = {
    'fetch-emails-every-5-minutes': {
        'task': 'email_client.fetch_emails_task',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
        'options': {'queue': 'default'}
    },
    'cleanup-old-files-daily': {
        'task': 'maintenance.cleanup_old_files',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
        'options': {'queue': 'maintenance'}
    },
    'health-check-hourly': {
        'task': 'maintenance.health_check',
        'schedule': crontab(minute=0),  # Every hour
        'options': {'queue': 'maintenance'}
    },
}

celery_app.conf.timezone = 'UTC'