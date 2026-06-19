"""
REPORTING API

Generates downloadable PDF/CSV/JSON/Excel reports for a given dataset
version and persists a Report row pointing at the generated file.
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models.user import User
from app.models.dataset import Dataset, DatasetVersion, Report
from app.core.rbac import get_current_user
from app.services import report_generator
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/reports", tags=["Reports"])

GENERATORS = {
    "pdf": report_generator.generate_pdf_report,
    "csv": report_generator.generate_csv_report,
    "json": report_generator.generate_json_report,
    "xlsx": report_generator.generate_excel_report,
}


@router.post("/generate/{version_id}")
def generate_report(version_id: str, file_format: str = "pdf", db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    if file_format not in GENERATORS:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {file_format}")

    version = db.query(DatasetVersion).filter(DatasetVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found")
    dataset = db.query(Dataset).filter(Dataset.id == version.dataset_id).first()

    version_dict = {
        "version_number": version.version_number, "scan_mode": version.scan_mode,
        "health_score": version.health_score, "health_grade": version.health_grade,
        "integrity_score": version.integrity_score, "annotation_score": version.annotation_score,
        "balance_score": version.balance_score, "image_quality_score": version.image_quality_score,
        "diversity_score": version.diversity_score, "leakage_score": version.leakage_score,
    }

    filename = f"{dataset.name}_v{version.version_number}_{uuid.uuid4().hex[:8]}.{file_format}"
    output_path = settings.REPORT_DIR / filename

    fn = GENERATORS[file_format]
    if file_format == "csv":
        fn(version_dict, output_path)
    else:
        fn(dataset.name, version_dict, version.recommendations or [], output_path)

    report = Report(dataset_id=dataset.id, dataset_version_id=version.id, report_type="health",
                     file_format=file_format, file_path=str(output_path), created_by=user.id)
    db.add(report)
    db.commit()
    db.refresh(report)

    log_action(db, user.id, "report_generated", "report", report.id, details={"format": file_format})
    return {"report_id": report.id, "download_url": f"/api/reports/download/{report.id}"}


@router.get("/download/{report_id}")
def download_report(report_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report or not Path(report.file_path).exists():
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(report.file_path, filename=Path(report.file_path).name)


@router.get("")
def list_reports(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Report).order_by(Report.created_at.desc()).all()
    return [{
        "id": r.id, "dataset_id": r.dataset_id, "dataset_version_id": r.dataset_version_id,
        "report_type": r.report_type, "file_format": r.file_format, "created_at": r.created_at,
    } for r in rows]
