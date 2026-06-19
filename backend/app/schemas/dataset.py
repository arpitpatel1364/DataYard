from pydantic import BaseModel
from typing import Optional, Any
import datetime as dt


class ScanPathRequest(BaseModel):
    """Used for Option A/B/C: user supplies a local data.yaml path OR a folder path."""
    path: str
    name: Optional[str] = None


class RoboflowImportRequest(BaseModel):
    api_key: str
    workspace: str
    project: str
    version: str
    name: Optional[str] = None


class ClassSelectionRequest(BaseModel):
    dataset_id: str
    selected_classes: list[str]
    scan_mode: str = "standard"  # quick/standard/deep


class CompareRequest(BaseModel):
    dataset_a_id: str
    dataset_b_id: str
    version_a_id: Optional[str] = None
    version_b_id: Optional[str] = None


class MonitoringConfigRequest(BaseModel):
    dataset_id: str
    enabled: bool
    scan_every_minutes: int = 30


class DatasetOut(BaseModel):
    id: str
    name: str
    source_type: str
    root_path: Optional[str]
    num_classes: int
    class_names: Any
    status: str
    monitoring_enabled: bool
    scan_every_minutes: int
    last_scanned_at: Optional[dt.datetime]
    created_at: dt.datetime

    class Config:
        from_attributes = True


class DatasetVersionOut(BaseModel):
    id: str
    dataset_id: str
    version_number: int
    scan_mode: str
    health_score: float
    health_grade: str
    integrity_score: float
    annotation_score: float
    balance_score: float
    image_quality_score: float
    diversity_score: float
    leakage_score: float
    train_images: int
    val_images: int
    test_images: int
    recommendations: Any
    created_at: dt.datetime

    class Config:
        from_attributes = True
