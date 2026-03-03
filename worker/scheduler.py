from celery.schedules import crontab
from celery_app import celery_app

# Schedule periodic tasks
beat_schedule = {
    'fetch-emails-every-1-minute': {
        'task': 'email_client.fetch_emails_task',
        'schedule': 60.0,  # 1 minute for testing
    },
    'cleanup-old-files-daily': {
        'task': 'maintenance.cleanup_old_files',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    'health-check-hourly': {
        'task': 'maintenance.health_check',
        'schedule': crontab(minute=0),  # Every hour
    },
}

# Apply schedule to celery app
celery_app.conf.beat_schedule = beat_schedule