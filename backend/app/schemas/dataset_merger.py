from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime


class MergeConfig(BaseModel):
    remove_duplicates: bool = False
    remove_blurry: bool = False
    remove_corrupted: bool = False
    blurry_threshold: int = 100
    excluded_images: List[str] = []
    excluded_annotations: List[str] = []
    # class_mappings: {target_name: [source_class1, source_class2, ...]}
    class_mappings: Optional[Dict[str, List[str]]] = None


class DatasetMergeStart(BaseModel):
    merge_name: str
    source_datasets: List[str]


class ClassMappingUpdate(BaseModel):
    """Payload to save/update class mappings for an operation."""
    class_mappings: Dict[str, List[str]]


class MergeAnalysisResponse(BaseModel):
    id: str
    total_images: int
    total_annotations: int
    duplicate_count: int
    corrupted_files: int
    blurry_images: int
    analysis_data: Dict[str, Any]


class MergeOperationResponse(BaseModel):
    id: str
    merge_name: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime]
    merged_images_count: int
    zip_file_size: int
