"""
MONITORING SCHEDULER

Replaces Celery + Redis with an in-process APScheduler background scheduler,
since the brief calls for SQLite-only, no external services. Each monitored
dataset gets its own interval job that re-runs a health scan and records a
new DatasetVersion + DatasetHistory entry, so health trends/timeline keep
growing automatically every `scan_every_minutes`.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger("cis.scheduler")
scheduler = BackgroundScheduler()


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("CIS monitoring scheduler started")


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)


def _job_id(dataset_id: str) -> str:
    return f"monitor_dataset_{dataset_id}"


def schedule_dataset_monitoring(dataset_id: str, minutes: int):
    from app.services.monitoring_job import run_monitored_scan  # local import avoids circular import

    job_id = _job_id(dataset_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    scheduler.add_job(run_monitored_scan, "interval", minutes=max(1, minutes),
                       args=[dataset_id], id=job_id, replace_existing=True)
    logger.info(f"Scheduled monitoring for dataset {dataset_id} every {minutes} min")


def unschedule_dataset_monitoring(dataset_id: str):
    job_id = _job_id(dataset_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"Unscheduled monitoring for dataset {dataset_id}")


def restore_all_monitoring_jobs():
    """Called on app startup to re-register monitoring jobs for datasets
    that had monitoring_enabled=True before the last restart."""
    from app.database import SessionLocal
    from app.models.dataset import Dataset

    db = SessionLocal()
    try:
        datasets = db.query(Dataset).filter(Dataset.monitoring_enabled == True).all()  # noqa: E712
        for ds in datasets:
            schedule_dataset_monitoring(ds.id, ds.scan_every_minutes or 30)
    finally:
        db.close()
