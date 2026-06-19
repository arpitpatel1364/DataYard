import datetime as dt
from typing import List
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models.user import User
from app.models.dataset_merger import DatasetMergeOperation, DatasetAnalysisResult, DatasetMergeLog
from app.schemas.dataset_merger import (
    DatasetMergeStart, MergeConfig, ClassMappingUpdate,
    MergeAnalysisResponse, MergeOperationResponse
)
from app.core.rbac import get_current_user
from app.services.dataset_merger import DatasetMerger
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/merger", tags=["Dataset Merger"])

MERGER_OUTPUT_DIR = settings.STORAGE_DIR / "merged_datasets"
MERGER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MERGER_TEMP_DIR = settings.STORAGE_DIR / "temp_merger"
MERGER_TEMP_DIR.mkdir(parents=True, exist_ok=True)


def analyze_datasets_task(operation_id: str, db: Session):
    operation = db.query(DatasetMergeOperation).filter(DatasetMergeOperation.id == operation_id).first()
    if not operation:
        return

    try:
        operation.status = "analyzing"
        db.commit()

        merger = DatasetMerger(output_dir=str(MERGER_OUTPUT_DIR), temp_dir=str(MERGER_TEMP_DIR))
        analysis_report = merger.analyze_datasets(operation.source_datasets)

        analysis_result = DatasetAnalysisResult(
            merge_operation_id=operation.id,
            total_images=analysis_report.get('total_images', 0),
            total_annotations=analysis_report.get('total_annotations', 0),
            duplicate_count=analysis_report.get('duplicates_found', 0),
            corrupted_files=analysis_report.get('corrupted_files', 0),
            blurry_images=analysis_report.get('blurry_images', 0),
            analysis_data=analysis_report
        )
        db.add(analysis_result)

        operation.status = "pending_merge"
        db.commit()

    except Exception as e:
        operation.status = "failed"
        operation.error_message = str(e)
        db.commit()


def merge_datasets_task(operation_id: str, config: dict, db: Session):
    operation = db.query(DatasetMergeOperation).filter(DatasetMergeOperation.id == operation_id).first()
    if not operation:
        return

    try:
        operation.status = "merging"
        db.commit()

        merger = DatasetMerger(output_dir=str(MERGER_OUTPUT_DIR), temp_dir=str(MERGER_TEMP_DIR))

        zip_path, metadata = merger.merge_datasets(
            dataset_paths=operation.source_datasets,
            merge_name=operation.merge_name,
            exclude_items={
                "images": config.get("excluded_images", []),
                "annotations": config.get("excluded_annotations", [])
            },
            remove_duplicates=config.get("remove_duplicates", False),
            remove_blurry=config.get("remove_blurry", False),
            remove_corrupted=config.get("remove_corrupted", False),
            class_mappings=config.get("class_mappings") or (operation.class_mappings or None),
        )

        operation.status = "completed"
        operation.completed_at = dt.datetime.utcnow()
        operation.zip_file_path = zip_path
        operation.merged_images_count = len(metadata.get('merged_images', []))
        operation.merged_annotations_count = len(metadata.get('merged_annotations', []))
        operation.zip_file_size = Path(zip_path).stat().st_size if Path(zip_path).exists() else 0
        operation.merge_metadata = metadata
        db.commit()

    except Exception as e:
        operation.status = "failed"
        operation.error_message = str(e)
        db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=MergeOperationResponse)
def start_analysis(
    req: DatasetMergeStart,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    operation = DatasetMergeOperation(
        user_id=current_user.id,
        merge_name=req.merge_name,
        source_datasets=req.source_datasets,
        status="queued_analysis"
    )
    db.add(operation)
    db.commit()
    db.refresh(operation)

    log_action(db, current_user.id, "MERGER_START_ANALYSIS", "MergeOperation", operation.id,
               {"merge_name": req.merge_name})

    background_tasks.add_task(analyze_datasets_task, operation.id, db)
    return operation


@router.get("/analyze/{operation_id}")
def get_analysis_result(
    operation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    operation = db.query(DatasetMergeOperation).filter(
        DatasetMergeOperation.id == operation_id,
        DatasetMergeOperation.user_id == current_user.id
    ).first()
    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")

    if operation.status in ["queued_analysis", "analyzing"]:
        return {"status": operation.status}

    if operation.status == "failed":
        return {"status": "failed", "error": operation.error_message}

    analysis = operation.analysis
    if not analysis:
        return {"status": "pending_merge"}

    # Expose full class info from analysis_data so the UI can build mapping UI
    raw = analysis.analysis_data or {}
    return {
        "status": operation.status,
        "class_mappings": operation.class_mappings or {},
        "analysis": {
            "total_images": analysis.total_images,
            "total_annotations": analysis.total_annotations,
            "duplicate_count": analysis.duplicate_count,
            "corrupted_files": analysis.corrupted_files,
            "blurry_images": analysis.blurry_images,
            "all_classes": raw.get("all_classes", []),
            "dataset_label_map": raw.get("dataset_label_map", {}),
            "analysis_data": raw,
        }
    }


@router.put("/{operation_id}/class-mappings")
def save_class_mappings(
    operation_id: str,
    payload: ClassMappingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Save / update the class mapping for an operation before merge."""
    operation = db.query(DatasetMergeOperation).filter(
        DatasetMergeOperation.id == operation_id,
        DatasetMergeOperation.user_id == current_user.id
    ).first()
    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")
    if operation.status not in ["pending_merge"]:
        raise HTTPException(status_code=400,
                            detail="Class mappings can only be set when status is pending_merge")

    operation.class_mappings = payload.class_mappings
    db.commit()
    return {"status": "ok", "class_mappings": operation.class_mappings}


@router.post("/merge/{operation_id}")
def start_merge(
    operation_id: str,
    config: MergeConfig,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    operation = db.query(DatasetMergeOperation).filter(
        DatasetMergeOperation.id == operation_id,
        DatasetMergeOperation.user_id == current_user.id
    ).first()
    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")

    operation.remove_duplicates = config.remove_duplicates
    operation.remove_blurry = config.remove_blurry
    operation.remove_corrupted = config.remove_corrupted
    operation.blurry_threshold = config.blurry_threshold
    operation.excluded_images = config.excluded_images
    operation.excluded_annotations = config.excluded_annotations
    if config.class_mappings is not None:
        operation.class_mappings = config.class_mappings
    db.commit()

    log_action(db, current_user.id, "MERGER_START_MERGE", "MergeOperation", operation.id)
    background_tasks.add_task(merge_datasets_task, operation.id, config.model_dump(), db)

    return {"status": "merging", "operation_id": operation.id}


@router.get("/{operation_id}")
def get_operation(
    operation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    operation = db.query(DatasetMergeOperation).filter(
        DatasetMergeOperation.id == operation_id,
        DatasetMergeOperation.user_id == current_user.id
    ).first()
    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")

    return {
        "id": operation.id,
        "merge_name": operation.merge_name,
        "status": operation.status,
        "created_at": operation.created_at,
        "completed_at": operation.completed_at,
        "merged_images_count": operation.merged_images_count,
        "zip_file_size": operation.zip_file_size,
        "error_message": operation.error_message
    }


@router.get("/user/list", response_model=List[MergeOperationResponse])
def list_operations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(DatasetMergeOperation).filter(
        DatasetMergeOperation.user_id == current_user.id
    ).order_by(DatasetMergeOperation.created_at.desc()).all()


@router.get("/download/{operation_id}")
def download_merged_dataset(
    operation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    operation = db.query(DatasetMergeOperation).filter(
        DatasetMergeOperation.id == operation_id,
        DatasetMergeOperation.user_id == current_user.id
    ).first()
    
    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")
        
    if operation.status != "completed":
        raise HTTPException(status_code=400, detail="Merge operation is not completed")
        
    if not operation.zip_file_path or not Path(operation.zip_file_path).exists():
        raise HTTPException(status_code=404, detail="Merged ZIP file not found on server")
        
    return FileResponse(
        path=operation.zip_file_path,
        media_type='application/zip',
        filename=f"{operation.merge_name}.zip"
    )
