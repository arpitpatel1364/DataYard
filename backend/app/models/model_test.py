"""
Model Testing Lab models: model_tests, benchmark_runs.
"""
import uuid
import datetime as dt

from sqlalchemy import String, DateTime, ForeignKey, Text, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class ModelTest(Base):
    """An uploaded model registered for testing."""
    __tablename__ = "model_tests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    framework: Mapped[str] = mapped_column(String(50), nullable=False)  # pytorch/onnx/tensorrt/openvino
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_mb: Mapped[float] = mapped_column(Float, default=0.0)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    runs: Mapped[list["BenchmarkRun"]] = relationship(back_populates="model_test",
                                                        cascade="all, delete-orphan")


class BenchmarkRun(Base):
    """A single benchmark/analysis execution against a model."""
    __tablename__ = "benchmark_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    model_test_id: Mapped[str] = mapped_column(String(36), ForeignKey("model_tests.id"), nullable=False)
    run_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # accuracy / performance / efficiency / output_quality / robustness / deployment

    status: Mapped[str] = mapped_column(String(20), default="completed")  # queued/running/completed/error
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    finished_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=True)

    model_test: Mapped["ModelTest"] = relationship(back_populates="runs")
