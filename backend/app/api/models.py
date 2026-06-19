"""
MODEL TESTING LAB / MODEL ANALYTICS API
"""
import shutil
import datetime as dt
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models.user import User
from app.models.dataset import Dataset
from app.models.model_test import ModelTest, BenchmarkRun
from app.core.rbac import get_current_user
from app.services import model_benchmark
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/models", tags=["Model Testing Lab"])

FRAMEWORK_BY_EXT = {".pt": "pytorch", ".pth": "pytorch", ".onnx": "onnx",
                     ".engine": "tensorrt", ".xml": "openvino"}


@router.get("/capabilities")
def get_runtime_capabilities(user: User = Depends(get_current_user)):
    """Tells the frontend which inference runtimes are actually installed,
    so the UI can grey out unavailable benchmark types instead of silently failing."""
    return model_benchmark.runtime_capabilities()


@router.post("/upload")
async def upload_model(file: UploadFile = File(...), dataset_id: str | None = Form(None),
                        db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ext = Path(file.filename).suffix.lower()
    framework = FRAMEWORK_BY_EXT.get(ext)
    if not framework:
        raise HTTPException(status_code=400,
                             detail=f"Unsupported model file type '{ext}'. Supported: "
                                     f"{list(FRAMEWORK_BY_EXT.keys())}")

    dest = settings.MODEL_DIR / f"{Path(file.filename).stem}_{int(dt.datetime.utcnow().timestamp())}{ext}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    model_test = ModelTest(
        name=file.filename, owner_id=user.id, framework=framework, file_path=str(dest),
        file_size_mb=round(dest.stat().st_size / (1024 * 1024), 3), dataset_id=dataset_id,
    )
    db.add(model_test)
    db.commit()
    db.refresh(model_test)
    log_action(db, user.id, "model_uploaded", "model_test", model_test.id, details={"framework": framework})
    return {"id": model_test.id, "name": model_test.name, "framework": model_test.framework,
            "file_size_mb": model_test.file_size_mb}


@router.get("")
def list_models(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(ModelTest).order_by(ModelTest.created_at.desc()).all()
    return [{"id": m.id, "name": m.name, "framework": m.framework, "file_size_mb": m.file_size_mb,
             "dataset_id": m.dataset_id, "created_at": m.created_at} for m in rows]


def _record_run(db: Session, model_test_id: str, run_type: str, results: dict) -> BenchmarkRun:
    run = BenchmarkRun(model_test_id=model_test_id, run_type=run_type, status="completed",
                        results=results, finished_at=dt.datetime.utcnow())
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.post("/{model_id}/benchmark/performance")
def run_performance_benchmark(model_id: str, input_size: int = 640, num_runs: int = 30,
                               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    model_test = db.query(ModelTest).filter(ModelTest.id == model_id).first()
    if not model_test:
        raise HTTPException(status_code=404, detail="Model not found")

    results = model_benchmark.performance_metrics(Path(model_test.file_path), model_test.framework,
                                                    input_size, num_runs)
    run = _record_run(db, model_id, "performance", results)
    log_action(db, user.id, "model_benchmark_performance", "model_test", model_id)
    return {"run_id": run.id, "results": results}


@router.post("/{model_id}/benchmark/efficiency")
def run_efficiency_benchmark(model_id: str, db: Session = Depends(get_db),
                              user: User = Depends(get_current_user)):
    model_test = db.query(ModelTest).filter(ModelTest.id == model_id).first()
    if not model_test:
        raise HTTPException(status_code=404, detail="Model not found")

    results = model_benchmark.efficiency_metrics(Path(model_test.file_path), model_test.framework)
    run = _record_run(db, model_id, "efficiency", results)
    return {"run_id": run.id, "results": results}


@router.post("/{model_id}/benchmark/accuracy")
def run_accuracy_benchmark(model_id: str, data_yaml_path: str | None = None,
                            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    model_test = db.query(ModelTest).filter(ModelTest.id == model_id).first()
    if not model_test:
        raise HTTPException(status_code=404, detail="Model not found")

    yaml_path = data_yaml_path
    if not yaml_path and model_test.dataset_id:
        dataset = db.query(Dataset).filter(Dataset.id == model_test.dataset_id).first()
        yaml_path = dataset.data_yaml_path if dataset else None

    results = model_benchmark.accuracy_metrics(Path(model_test.file_path), model_test.framework, yaml_path)
    run = _record_run(db, model_id, "accuracy", results)
    log_action(db, user.id, "model_benchmark_accuracy", "model_test", model_id)
    return {"run_id": run.id, "results": results}


@router.post("/{model_id}/benchmark/output-quality")
def run_output_quality_benchmark(model_id: str, db: Session = Depends(get_db),
                                  user: User = Depends(get_current_user)):
    model_test = db.query(ModelTest).filter(ModelTest.id == model_id).first()
    if not model_test:
        raise HTTPException(status_code=404, detail="Model not found")

    sample_images = []
    if model_test.dataset_id:
        dataset = db.query(Dataset).filter(Dataset.id == model_test.dataset_id).first()
        if dataset and dataset.val_path:
            val_dir = Path(dataset.val_path)
            images_dir = val_dir / "images" if (val_dir / "images").exists() else val_dir
            if images_dir.exists():
                sample_images = [str(p) for p in list(images_dir.rglob("*.jpg"))[:25]]

    results = model_benchmark.output_quality_metrics(Path(model_test.file_path), model_test.framework,
                                                       sample_images)
    run = _record_run(db, model_id, "output_quality", results)
    return {"run_id": run.id, "results": results}


@router.post("/{model_id}/benchmark/robustness")
def run_robustness_benchmark(model_id: str, db: Session = Depends(get_db),
                              user: User = Depends(get_current_user)):
    model_test = db.query(ModelTest).filter(ModelTest.id == model_id).first()
    if not model_test:
        raise HTTPException(status_code=404, detail="Model not found")

    sample_images = []
    if model_test.dataset_id:
        dataset = db.query(Dataset).filter(Dataset.id == model_test.dataset_id).first()
        if dataset and dataset.val_path:
            val_dir = Path(dataset.val_path)
            images_dir = val_dir / "images" if (val_dir / "images").exists() else val_dir
            if images_dir.exists():
                sample_images = [str(p) for p in list(images_dir.rglob("*.jpg"))[:5]]

    results = model_benchmark.robustness_metrics(Path(model_test.file_path), model_test.framework, sample_images)
    run = _record_run(db, model_id, "robustness", results)
    return {"run_id": run.id, "results": results}


@router.get("/{model_id}/runs")
def list_runs(model_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (db.query(BenchmarkRun).filter(BenchmarkRun.model_test_id == model_id)
            .order_by(BenchmarkRun.started_at.desc()).all())
    return [{"id": r.id, "run_type": r.run_type, "status": r.status, "results": r.results,
             "started_at": r.started_at, "finished_at": r.finished_at} for r in rows]
