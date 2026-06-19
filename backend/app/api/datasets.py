"""
DATASETS API

Covers: data.yaml auto-detection (Option A/B/C), local + Roboflow import,
dataset registry (list/get), class selection workflow, scan execution
(quick/standard/deep -> health engine + class intelligence + recommendations),
versioning/timeline, and monitoring configuration.
"""
import shutil
import datetime as dt
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models.user import User
from app.models.dataset import Dataset, DatasetVersion, DatasetHistory, DatasetSourceType, DatasetStatus
from app.schemas.dataset import (ScanPathRequest, RoboflowImportRequest, ClassSelectionRequest,
                                  MonitoringConfigRequest, DatasetOut, DatasetVersionOut)
from app.core.rbac import get_current_user
from app.services import yaml_parser, health_engine, class_intelligence, recommendation_engine
from app.services import roboflow_client, scheduler as scheduler_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/datasets", tags=["Datasets"])


# ---------------------------------------------------------------------------
# DATA.YAML AUTO-DETECTION + IMPORT
# ---------------------------------------------------------------------------

@router.post("/detect")
def detect_dataset_structure(payload: ScanPathRequest, user: User = Depends(get_current_user)):
    """
    Options A/B/C: accepts a path to a data.yaml file OR a dataset folder
    (server-side path, since this is a self-hosted internal tool). Returns
    the auto-detected summary WITHOUT registering anything yet, so the
    frontend can show the class-selection checkboxes before committing.
    """
    try:
        result = yaml_parser.detect_dataset(payload.path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result.to_summary()


@router.post("/upload-yaml")
async def upload_data_yaml(file: UploadFile = File(...), dataset_root: str = Form(...),
                            user: User = Depends(get_current_user)):
    """
    Option B: user drags a data.yaml file directly. We store it alongside
    the dataset_root path they confirm (since the dataset images/labels
    themselves are assumed to already exist on the server's filesystem -
    this is a desktop-style internal tool, not a public file host).
    """
    dest = Path(dataset_root) / "data.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        result = yaml_parser.detect_dataset(str(dest))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result.to_summary()


@router.post("/register", response_model=DatasetOut)
def register_dataset(payload: ScanPathRequest, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """Registers a detected local dataset into the Dataset Registry."""
    result = yaml_parser.detect_dataset(payload.path)

    dataset = Dataset(
        name=payload.name or Path(result.dataset_root).name,
        owner_id=user.id,
        source_type=DatasetSourceType.LOCAL,
        root_path=result.dataset_root,
        data_yaml_path=result.data_yaml_path,
        train_path=result.splits.get("train").path if result.splits.get("train") else None,
        val_path=result.splits.get("val").path if result.splits.get("val") else None,
        test_path=result.splits.get("test").path if result.splits.get("test") else None,
        num_classes=result.num_classes,
        class_names=result.classes,
        annotation_format="yolo",
        status=DatasetStatus.REGISTERED,
        scan_every_minutes=settings.DEFAULT_SCAN_EVERY_MINUTES,
    )
    db.add(dataset)
    db.flush()
    db.add(DatasetHistory(dataset_id=dataset.id, event_type="import",
                           message="Dataset registered from local path", meta={"path": payload.path}))
    db.commit()
    db.refresh(dataset)
    log_action(db, user.id, "dataset_registered", "dataset", dataset.id)
    return dataset


@router.post("/import-roboflow", response_model=DatasetOut)
def import_roboflow_dataset(payload: RoboflowImportRequest, db: Session = Depends(get_db),
                             user: User = Depends(get_current_user)):
    dest_dir = settings.DATASET_DIR / f"roboflow_{payload.workspace}_{payload.project}_{payload.version}"
    try:
        roboflow_client.download_dataset(payload.api_key, payload.workspace, payload.project,
                                          payload.version, dest_dir)
    except roboflow_client.RoboflowError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = yaml_parser.detect_dataset(str(dest_dir))

    dataset = Dataset(
        name=payload.name or f"{payload.workspace}/{payload.project} v{payload.version}",
        owner_id=user.id,
        source_type=DatasetSourceType.ROBOFLOW,
        root_path=result.dataset_root,
        data_yaml_path=result.data_yaml_path,
        train_path=result.splits.get("train").path if result.splits.get("train") else None,
        val_path=result.splits.get("val").path if result.splits.get("val") else None,
        test_path=result.splits.get("test").path if result.splits.get("test") else None,
        num_classes=result.num_classes,
        class_names=result.classes,
        annotation_format="yolo",
        status=DatasetStatus.REGISTERED,
        roboflow_workspace=payload.workspace,
        roboflow_project=payload.project,
        roboflow_version=payload.version,
        scan_every_minutes=settings.DEFAULT_SCAN_EVERY_MINUTES,
    )
    db.add(dataset)
    db.flush()
    db.add(DatasetHistory(dataset_id=dataset.id, event_type="import",
                           message="Dataset imported from Roboflow",
                           meta={"workspace": payload.workspace, "project": payload.project}))
    db.commit()
    db.refresh(dataset)
    log_action(db, user.id, "dataset_imported_roboflow", "dataset", dataset.id)
    return dataset


# ---------------------------------------------------------------------------
# REGISTRY (list / get)
# ---------------------------------------------------------------------------

@router.get("", response_model=list[DatasetOut])
def list_datasets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Dataset).order_by(Dataset.created_at.desc()).all()


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    scheduler_service.unschedule_dataset_monitoring(dataset_id)
    db.delete(dataset)
    db.commit()
    log_action(db, user.id, "dataset_deleted", "dataset", dataset_id)
    return


# ---------------------------------------------------------------------------
# CLASS SELECTION WORKFLOW
# ---------------------------------------------------------------------------

@router.get("/{dataset_id}/classes")
def get_dataset_classes(dataset_id: str, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"classes": dataset.class_names, "num_classes": dataset.num_classes}


# ---------------------------------------------------------------------------
# SCAN EXECUTION (health engine + class intelligence + recommendations)
# ---------------------------------------------------------------------------

@router.post("/scan", response_model=DatasetVersionOut)
def run_scan(payload: ClassSelectionRequest, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    dataset = db.query(Dataset).filter(Dataset.id == payload.dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    dataset.status = DatasetStatus.SCANNING
    db.commit()

    try:
        report = health_engine.run_health_scan(
            dataset_root=dataset.root_path,
            splits={"train": dataset.train_path, "val": dataset.val_path, "test": dataset.test_path},
            class_names=dataset.class_names or [],
            annotation_format=dataset.annotation_format,
            scan_mode=payload.scan_mode,
        )

        per_class_instances = report.get("annotations", {}).get("per_class_instances", {})
        per_class_images = report.get("annotations", {}).get("per_class_image_count", {})
        ci_result = class_intelligence.run_class_intelligence(
            per_class_instances, per_class_images,
            report.get("annotations", {}).get("invalid_annotations_sample", []),
            payload.selected_classes or dataset.class_names or [],
            report.get("counts", {}).get("total_images", 0),
        )
        report["class_intelligence"] = ci_result

        recs = recommendation_engine.generate_recommendations(report)
        recs.extend(ci_result.get("recommendations", []))

        next_version_number = (
            db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset.id).count() + 1
        )
        scores = report["scores"]
        version = DatasetVersion(
            dataset_id=dataset.id,
            version_number=next_version_number,
            scan_mode=payload.scan_mode,
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
        dataset.status = DatasetStatus.SCANNED
        dataset.last_scanned_at = dt.datetime.utcnow()
        db.add(DatasetHistory(dataset_id=dataset.id, event_type="scan",
                               message=f"{payload.scan_mode} scan completed - health {scores['health_score']}",
                               meta={"version_number": next_version_number}))
        db.commit()
        db.refresh(version)
        log_action(db, user.id, "dataset_scanned", "dataset", dataset.id,
                   details={"scan_mode": payload.scan_mode, "health_score": scores["health_score"]})
        return version
    except Exception as e:
        dataset.status = DatasetStatus.ERROR
        db.commit()
        raise HTTPException(status_code=500, detail=f"Scan failed: {e}")


@router.get("/{dataset_id}/versions", response_model=list[DatasetVersionOut])
def list_versions(dataset_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version_number).all())


@router.get("/versions/{version_id}/full-report")
def get_full_report(version_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    version = db.query(DatasetVersion).filter(DatasetVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return {
        "version_number": version.version_number,
        "scan_mode": version.scan_mode,
        "full_report": version.full_report,
        "recommendations": version.recommendations,
    }


@router.get("/{dataset_id}/history")
def get_history(dataset_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (db.query(DatasetHistory).filter(DatasetHistory.dataset_id == dataset_id)
            .order_by(DatasetHistory.created_at.desc()).all())
    return [{"event_type": r.event_type, "message": r.message, "meta": r.meta,
             "created_at": r.created_at} for r in rows]


# ---------------------------------------------------------------------------
# MONITORING CONFIG
# ---------------------------------------------------------------------------

@router.post("/monitoring/configure")
def configure_monitoring(payload: MonitoringConfigRequest, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    dataset = db.query(Dataset).filter(Dataset.id == payload.dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    dataset.monitoring_enabled = payload.enabled
    dataset.scan_every_minutes = payload.scan_every_minutes
    db.commit()

    if payload.enabled:
        scheduler_service.schedule_dataset_monitoring(dataset.id, payload.scan_every_minutes)
    else:
        scheduler_service.unschedule_dataset_monitoring(dataset.id)

    log_action(db, user.id, "monitoring_configured", "dataset", dataset.id,
               details={"enabled": payload.enabled, "interval": payload.scan_every_minutes})
    return {"message": "Monitoring configuration updated", "enabled": payload.enabled}


@router.get("/monitoring/live")
def live_monitoring_feed(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Dashboard feed: every monitored dataset + its latest health trend."""
    datasets = db.query(Dataset).filter(Dataset.monitoring_enabled == True).all()  # noqa: E712
    out = []
    for ds in datasets:
        versions = (db.query(DatasetVersion).filter(DatasetVersion.dataset_id == ds.id)
                    .order_by(DatasetVersion.version_number).all())
        out.append({
            "dataset_id": ds.id,
            "name": ds.name,
            "scan_every_minutes": ds.scan_every_minutes,
            "last_scanned_at": ds.last_scanned_at,
            "health_timeline": [{"version": v.version_number, "score": v.health_score} for v in versions],
        })
    return out
