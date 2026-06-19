"""
DATASET COMPARISON API

Comparison itself is source-type agnostic since both local and Roboflow
datasets are normalized into the same Dataset/DatasetVersion records on
import - so "Local vs Roboflow" and "Roboflow vs Roboflow" work through
the exact same code path as "Local vs Local".
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.dataset import Dataset, DatasetVersion
from app.schemas.dataset import CompareRequest
from app.core.rbac import get_current_user
from app.services import comparison_engine
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/compare", tags=["Comparison"])


def _latest_version(db: Session, dataset_id: str, version_id: str | None) -> DatasetVersion:
    q = db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset_id)
    if version_id:
        version = q.filter(DatasetVersion.id == version_id).first()
    else:
        version = q.order_by(DatasetVersion.version_number.desc()).first()
    if not version:
        raise HTTPException(status_code=404,
                             detail=f"No scanned version found for dataset {dataset_id} - run a scan first")
    return version


@router.post("")
def compare_datasets(payload: CompareRequest, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    dataset_a = db.query(Dataset).filter(Dataset.id == payload.dataset_a_id).first()
    dataset_b = db.query(Dataset).filter(Dataset.id == payload.dataset_b_id).first()
    if not dataset_a or not dataset_b:
        raise HTTPException(status_code=404, detail="One or both datasets not found")

    version_a = _latest_version(db, dataset_a.id, payload.version_a_id)
    version_b = _latest_version(db, dataset_b.id, payload.version_b_id)

    version_a_dict = {
        "health_score": version_a.health_score, "health_grade": version_a.health_grade,
        "integrity_score": version_a.integrity_score, "annotation_score": version_a.annotation_score,
        "balance_score": version_a.balance_score, "image_quality_score": version_a.image_quality_score,
        "diversity_score": version_a.diversity_score, "leakage_score": version_a.leakage_score,
        "full_report": version_a.full_report,
    }
    version_b_dict = {
        "health_score": version_b.health_score, "health_grade": version_b.health_grade,
        "integrity_score": version_b.integrity_score, "annotation_score": version_b.annotation_score,
        "balance_score": version_b.balance_score, "image_quality_score": version_b.image_quality_score,
        "diversity_score": version_b.diversity_score, "leakage_score": version_b.leakage_score,
        "full_report": version_b.full_report,
    }

    result = comparison_engine.compare_versions(
        version_a_dict, version_b_dict, dataset_a.class_names or [], dataset_b.class_names or [],
    )
    result["dataset_a"] = {"id": dataset_a.id, "name": dataset_a.name, "source_type": dataset_a.source_type.value}
    result["dataset_b"] = {"id": dataset_b.id, "name": dataset_b.name, "source_type": dataset_b.source_type.value}

    log_action(db, user.id, "datasets_compared", "dataset", dataset_a.id,
               details={"compared_with": dataset_b.id})
    return result
