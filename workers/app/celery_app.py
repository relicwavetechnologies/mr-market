"""Celery application configuration for Mr. Market workers.

Broker and result backend both use Redis. The beat schedule drives all
periodic tasks: nightly data refresh, intraday news fetch, and post-market
institutional data collection.
"""

import os

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(
    "mr_market_workers",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery.conf.update(
    # Serialisation
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone — all cron expressions are in IST
    timezone="Asia/Kolkata",
    enable_utc=True,
    # Task routing
    task_default_queue="default",
    task_routes={
        "app.tasks.nightly_refresh.*": {"queue": "nightly"},
        "app.tasks.news_fetch.*": {"queue": "news"},
        "app.tasks.price_streaming.*": {"queue": "prices"},
    },
    # Result expiry (24 hours)
    result_expires=86400,
    # Worker prefetch — keep low for long-running scraping tasks
    worker_prefetch_multiplier=1,
    # Task time limits
    task_soft_time_limit=1800,  # 30 min soft
    task_time_limit=3600,  # 60 min hard
    # Beat schedule — all times IST
    beat_schedule={
        "nightly_refresh": {
            "task": "app.tasks.nightly_refresh.nightly_refresh_all",
            "schedule": crontab(hour=4, minute=0),  # 04:00 IST daily
            "options": {"queue": "nightly"},
        },
        "news_fetch": {
            "task": "app.tasks.news_fetch.fetch_latest_news",
            # Every 15 min, Mon-Fri, 9:15 AM - 3:30 PM IST
            "schedule": crontab(
                minute="*/15",
                hour="9-15",
                day_of_week="1-5",
            ),
            "options": {"queue": "news"},
        },
        "fii_dii_fetch": {
            "task": "app.tasks.nightly_refresh.fetch_fii_dii_data",
            "schedule": crontab(hour=18, minute=0),  # 18:00 IST daily
            "options": {"queue": "nightly"},
        },
        "bulk_deals_fetch": {
            "task": "app.tasks.nightly_refresh.fetch_bulk_deals",
            "schedule": crontab(hour=18, minute=30),  # 18:30 IST daily
            "options": {"queue": "nightly"},
        },
    },
)

# Auto-discover tasks from the tasks package
celery.autodiscover_tasks(["app.tasks"])
