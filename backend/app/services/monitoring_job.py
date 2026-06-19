"""
The function the scheduler calls on each tick for a monitored dataset.
Kept in its own module to avoid circular imports between scheduler.py and
the rest of the app.
"""
import logging

from app.database import SessionLocal
from app.models.dataset import Dataset, DatasetVersion, DatasetHistory
from app.services import health_engine, recommendation_engine

logger = logging.getLogger("cis.monitoring_job")


def run_monitored_scan(dataset_id: str):
    db = SessionLocal()
    try:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset or not dataset.monitoring_enabled:
            return

        report = health_engine.run_health_scan(
            dataset_root=dataset.root_path,
            splits={"train": dataset.train_path, "val": dataset.val_path, "test": dataset.test_path},
            class_names=dataset.class_names or [],
            annotation_format=dataset.annotation_format,
            scan_mode="standard",
        )
        recs = recommendation_engine.generate_recommendations(report)

        next_version_number = (
            db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset.id).count() + 1
        )
        scores = report["scores"]
        version = DatasetVersion(
            dataset_id=dataset.id,
            version_number=next_version_number,
            scan_mode="standard",
            health_score=scores["health_score"],
            health_grade=scores["health_grade"],
            integrity_score=scores["integrity"],
            annotation_score=scores["annotation"],
            balance_score=scores["balance"],
            image_quality_score=scores["image_quality"],
            diversity_score=scores["diversity"],
            leakage_score=scores["leakage"],
            train_images=report["counts"]["train_images"],
            val_images=report["counts"]["val_images"],
            test_images=report["counts"]["test_images"],
            full_report=report,
            recommendations=recs,
        )
        db.add(version)

        import datetime as dt
        dataset.last_scanned_at = dt.datetime.utcnow()
        db.add(DatasetHistory(dataset_id=dataset.id, event_type="monitoring_scan",
                               message=f"Automated monitoring scan - health score {scores['health_score']}",
                               meta={"version_number": next_version_number}))
        db.commit()
        logger.info(f"Monitoring scan complete for dataset {dataset_id}: {scores['health_score']}")
    except Exception as e:
        logger.exception(f"Monitoring scan failed for dataset {dataset_id}: {e}")
        db.rollback()
    finally:
        db.close()
