"""
Dataset domain models: datasets, dataset_versions, dataset_history,
roboflow_connections, reports.
"""
import enum
import uuid
import datetime as dt

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Enum, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class DatasetSourceType(str, enum.Enum):
    LOCAL = "local"
    ROBOFLOW = "roboflow"


class DatasetStatus(str, enum.Enum):
    REGISTERED = "registered"
    SCANNING = "scanning"
    SCANNED = "scanned"
    ERROR = "error"
    ARCHIVED = "archived"


class Dataset(Base):
    """The Dataset Registry entry. One row per logical dataset."""
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)

    source_type: Mapped[DatasetSourceType] = mapped_column(Enum(DatasetSourceType),
                                                             default=DatasetSourceType.LOCAL)
    root_path: Mapped[str] = mapped_column(Text, nullable=True)  # resolved local path
    data_yaml_path: Mapped[str] = mapped_column(Text, nullable=True)

    train_path: Mapped[str] = mapped_column(Text, nullable=True)
    val_path: Mapped[str] = mapped_column(Text, nullable=True)
    test_path: Mapped[str] = mapped_column(Text, nullable=True)

    num_classes: Mapped[int] = mapped_column(Integer, default=0)
    class_names: Mapped[dict] = mapped_column(JSON, default=list)  # list[str] stored as JSON

    annotation_format: Mapped[str] = mapped_column(String(50), default="yolo")

    status: Mapped[DatasetStatus] = mapped_column(Enum(DatasetStatus), default=DatasetStatus.REGISTERED)

    # Monitoring
    monitoring_enabled: Mapped[bool] = mapped_column(Integer, default=0)
    scan_every_minutes: Mapped[int] = mapped_column(Integer, default=30)
    last_scanned_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=True)

    # Roboflow linkage (optional)
    roboflow_workspace: Mapped[str] = mapped_column(String(255), nullable=True)
    roboflow_project: Mapped[str] = mapped_column(String(255), nullable=True)
    roboflow_version: Mapped[str] = mapped_column(String(50), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow,
                                                      onupdate=dt.datetime.utcnow)

    versions: Mapped[list["DatasetVersion"]] = relationship(back_populates="dataset",
                                                              cascade="all, delete-orphan",
                                                              order_by="DatasetVersion.version_number")
    history: Mapped[list["DatasetHistory"]] = relationship(back_populates="dataset",
                                                             cascade="all, delete-orphan")


class DatasetVersion(Base):
    """A snapshot of a dataset's scan results at a point in time (versioning + timeline)."""
    __tablename__ = "dataset_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    scan_mode: Mapped[str] = mapped_column(String(20), default="standard")  # quick/standard/deep

    health_score: Mapped[float] = mapped_column(Float, default=0.0)
    health_grade: Mapped[str] = mapped_column(String(5), default="F")

    integrity_score: Mapped[float] = mapped_column(Float, default=0.0)
    annotation_score: Mapped[float] = mapped_column(Float, default=0.0)
    balance_score: Mapped[float] = mapped_column(Float, default=0.0)
    image_quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    diversity_score: Mapped[float] = mapped_column(Float, default=0.0)
    leakage_score: Mapped[float] = mapped_column(Float, default=0.0)

    train_images: Mapped[int] = mapped_column(Integer, default=0)
    val_images: Mapped[int] = mapped_column(Integer, default=0)
    test_images: Mapped[int] = mapped_column(Integer, default=0)

    full_report: Mapped[dict] = mapped_column(JSON, default=dict)  # complete scan payload
    recommendations: Mapped[dict] = mapped_column(JSON, default=list)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    dataset: Mapped["Dataset"] = relationship(back_populates="versions")


class DatasetHistory(Base):
    """Lightweight audit trail of changes/events for a dataset (growth, scans, imports)."""
    __tablename__ = "dataset_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # import/scan/compare/edit
    message: Mapped[str] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    dataset: Mapped["Dataset"] = relationship(back_populates="history")


class RoboflowConnection(Base):
    """Stores a user's Roboflow API key (lightly obfuscated) for repeated imports."""
    __tablename__ = "roboflow_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(100), default="My Roboflow")
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    workspace: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class Report(Base):
    """Generated report files (PDF/CSV/JSON/XLSX) tied to a dataset version or comparison."""
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=True)
    dataset_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("dataset_versions.id"),
                                                      nullable=True)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)  # health/comparison/class/model
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf/csv/json/xlsx
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
