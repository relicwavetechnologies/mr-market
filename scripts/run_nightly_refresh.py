#!/usr/bin/env python3
"""Manually trigger the nightly refresh pipeline via Celery.

Usage:
    python scripts/run_nightly_refresh.py
    python scripts/run_nightly_refresh.py --task nightly_refresh_all
    python scripts/run_nightly_refresh.py --task fetch_fii_dii_data
    python scripts/run_nightly_refresh.py --task fetch_bulk_deals

By default, triggers all nightly tasks. Use --task to run a specific one.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

AVAILABLE_TASKS = {
    "nightly_refresh_all": "app.tasks.nightly_refresh.nightly_refresh_all",
    "fetch_fii_dii_data": "app.tasks.nightly_refresh.fetch_fii_dii_data",
    "fetch_bulk_deals": "app.tasks.nightly_refresh.fetch_bulk_deals",
    "fetch_latest_news": "app.tasks.news_fetch.fetch_latest_news",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manually trigger Mr. Market nightly refresh tasks"
    )
    parser.add_argument(
        "--task",
        choices=list(AVAILABLE_TASKS.keys()),
        default=None,
        help="Specific task to trigger (default: all nightly tasks)",
    )
    parser.add_argument(
        "--queue",
        default="nightly",
        help="Celery queue to send the task to (default: nightly)",
    )
    args = parser.parse_args()

    from workers.app.celery_app import celery

    tasks_to_run = (
        {args.task: AVAILABLE_TASKS[args.task]}
        if args.task
        else {k: v for k, v in AVAILABLE_TASKS.items() if k != "fetch_latest_news"}
    )

    print("Triggering nightly refresh tasks...\n")

    for name, task_path in tasks_to_run.items():
        print(f"  Sending: {task_path} -> queue={args.queue}")
        result = celery.send_task(
            task_path,
            queue=args.queue,
        )
        print(f"  Task ID: {result.id}")

    print(f"\n{len(tasks_to_run)} task(s) enqueued.")
    print("Monitor with: celery -A app.celery_app:celery flower")


if __name__ == "__main__":
    main()
