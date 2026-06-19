import uuid
import datetime as dt

from sqlalchemy import String, Integer, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

def gen_uuid() -> str:
    return str(uuid.uuid4())

class DatasetMergeOperation(Base):
    __tablename__ = "dataset_merge_operations"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    merge_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    
    source_datasets: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    completed_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=True)
    
    remove_duplicates: Mapped[bool] = mapped_column(Boolean, default=False)
    remove_blurry: Mapped[bool] = mapped_column(Boolean, default=False)
    remove_corrupted: Mapped[bool] = mapped_column(Boolean, default=False)
    blurry_threshold: Mapped[int] = mapped_column(Integer, default=100)
    
    excluded_images: Mapped[list] = mapped_column(JSON, default=list)
    excluded_annotations: Mapped[list] = mapped_column(JSON, default=list)
    
    merged_images_count: Mapped[int] = mapped_column(Integer, default=0)
    merged_annotations_count: Mapped[int] = mapped_column(Integer, default=0)
    zip_file_path: Mapped[str] = mapped_column(String, nullable=True)
    zip_file_size: Mapped[int] = mapped_column(Integer, default=0)
    
    duplicates_removed: Mapped[int] = mapped_column(Integer, default=0)
    blurry_removed: Mapped[int] = mapped_column(Integer, default=0)
    corrupted_removed: Mapped[int] = mapped_column(Integer, default=0)
    
    error_message: Mapped[str] = mapped_column(String, nullable=True)
    merge_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    class_mappings: Mapped[dict] = mapped_column(JSON, default=dict)  # {target_name: [src_names]}
    
    analysis = relationship("DatasetAnalysisResult", back_populates="merge_operation", uselist=False, cascade="all, delete-orphan")
    logs = relationship("DatasetMergeLog", back_populates="merge_operation", cascade="all, delete-orphan")


class DatasetAnalysisResult(Base):
    __tablename__ = "dataset_analysis_results"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    merge_operation_id: Mapped[str] = mapped_column(String(36), ForeignKey("dataset_merge_operations.id"))
    
    total_images: Mapped[int] = mapped_column(Integer, default=0)
    total_annotations: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    corrupted_files: Mapped[int] = mapped_column(Integer, default=0)
    blurry_images: Mapped[int] = mapped_column(Integer, default=0)
    analysis_data: Mapped[dict] = mapped_column(JSON, default=dict)
    
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    
    merge_operation = relationship("DatasetMergeOperation", back_populates="analysis")


class DatasetMergeLog(Base):
    __tablename__ = "dataset_merge_logs"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    merge_operation_id: Mapped[str] = mapped_column(String(36), ForeignKey("dataset_merge_operations.id"))
    
    level: Mapped[str] = mapped_column(String(20), default="info")
    message: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    
    merge_operation = relationship("DatasetMergeOperation", back_populates="logs")
