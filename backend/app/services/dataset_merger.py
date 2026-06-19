"""
Dataset Merger Module
=====================
Professional backend module for merging multiple datasets with quality control,
duplicate detection, corrupted file handling, and ZIP archive generation.

Features:
- Multiple dataset import and validation
- Duplicate image detection (hash-based)
- Blurry image detection (Laplacian variance)
- Corrupted file identification
- Broken annotation detection
- Selective dataset component removal
- ZIP archive generation with cleanup
- Database tracking of merge operations
"""

import os
import json
import hashlib
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Set
import logging

import cv2
import numpy as np
from PIL import Image
import magic  # python-magic for file type validation

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatasetValidator:
    """Validates dataset structure and content integrity."""
    
    VALID_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.gif'}
    VALID_ANNOTATION_EXTENSIONS = {'.xml', '.json', '.txt', '.yaml', '.yml'}
    MIN_IMAGE_SIZE = 10  # pixels
    MAX_IMAGE_SIZE = 100000  # pixels
    BLURRY_THRESHOLD = 100  # Laplacian variance threshold
    
    def __init__(self):
        self.validation_errors = []
        self.warnings = []
    
    def validate_dataset_structure(self, dataset_path: str) -> Dict:
        """
        Validate dataset directory structure.

        Supports two layouts:
          Flat:       dataset/images/   + dataset/annotations/  (or labels/)
          YOLO-split: dataset/train/images/ + dataset/train/labels/
                      dataset/valid/images/ + dataset/valid/labels/
                      dataset/test/images/  + dataset/test/labels/

        Returns a result dict with:
          valid            bool
          image_dirs       list[str]   — all directories containing images
          annotation_dirs  list[str]   — all directories containing labels
          image_count      int
          annotation_count int
          errors           list[str]
          warnings         list[str]

        Legacy keys (images_path, annotations_path) are kept pointing to the
        first found directory so existing callers don't break.
        """
        result = {
            'valid': True,
            'images_path': None,       # legacy: first image dir
            'annotations_path': None,  # legacy: first annotation dir
            'image_dirs': [],
            'annotation_dirs': [],
            'image_count': 0,
            'annotation_count': 0,
            'errors': [],
            'warnings': []
        }

        dataset_path = Path(dataset_path)

        if not dataset_path.exists():
            result['valid'] = False
            result['errors'].append(f"Dataset path does not exist: {dataset_path}")
            return result

        # --- Try YOLO-split layout first (train/valid/test) ---
        SPLIT_NAMES = ['train', 'valid', 'val', 'test']
        found_splits = []
        for split in SPLIT_NAMES:
            split_dir = dataset_path / split
            if split_dir.is_dir():
                img_dir = split_dir / 'images'
                lbl_dir = split_dir / 'labels'
                if img_dir.is_dir():
                    found_splits.append((img_dir, lbl_dir if lbl_dir.is_dir() else None))

        if found_splits:
            for img_dir, lbl_dir in found_splits:
                result['image_dirs'].append(str(img_dir))
                imgs = list(img_dir.glob('*'))
                result['image_count'] += len(imgs)
                if lbl_dir:
                    result['annotation_dirs'].append(str(lbl_dir))
                    result['annotation_count'] += len(list(lbl_dir.glob('*')))
            # Set legacy keys
            result['images_path'] = result['image_dirs'][0]
            result['annotations_path'] = result['annotation_dirs'][0] if result['annotation_dirs'] else None
            return result

        # --- Fallback: flat layout (images/ + annotations/ or labels/) ---
        images_path = dataset_path / 'images'
        ann_path = (dataset_path / 'annotations' if (dataset_path / 'annotations').is_dir()
                    else dataset_path / 'labels')

        if not images_path.exists():
            result['valid'] = False
            result['errors'].append(f"Images directory not found: {images_path}")
            return result

        result['image_dirs'].append(str(images_path))
        result['images_path'] = str(images_path)
        result['image_count'] = len(list(images_path.glob('*')))

        if ann_path.exists():
            result['annotation_dirs'].append(str(ann_path))
            result['annotations_path'] = str(ann_path)
            result['annotation_count'] = len(list(ann_path.glob('*')))
        else:
            result['warnings'].append("No annotations/labels directory found")

        return result
    
    def check_image_quality(self, image_path: str) -> Dict:
        """
        Check image quality metrics.
        
        Returns:
            dict: Quality metrics including corruption, blurriness, size
        """
        quality_info = {
            'path': image_path,
            'valid': True,
            'corrupted': False,
            'blurry': False,
            'too_small': False,
            'too_large': False,
            'size': None,
            'blurry_score': None,
            'error': None
        }
        
        try:
            # Validate file exists
            if not os.path.exists(image_path):
                quality_info['valid'] = False
                quality_info['error'] = "File not found"
                return quality_info
            
            # Check file size (basic corruption indicator)
            file_size = os.path.getsize(image_path)
            if file_size < 100:  # Less than 100 bytes
                quality_info['corrupted'] = True
                quality_info['error'] = "File too small (likely corrupted)"
                quality_info['valid'] = False
                return quality_info
            
            # Try to open image with OpenCV
            image = cv2.imread(image_path)
            if image is None:
                quality_info['corrupted'] = True
                quality_info['valid'] = False
                quality_info['error'] = "Failed to read image (corrupted or invalid format)"
                return quality_info
            
            # Check dimensions
            height, width = image.shape[:2]
            quality_info['size'] = {'width': width, 'height': height}
            
            if width < self.MIN_IMAGE_SIZE or height < self.MIN_IMAGE_SIZE:
                quality_info['too_small'] = True
                quality_info['valid'] = False
            
            if width > self.MAX_IMAGE_SIZE or height > self.MAX_IMAGE_SIZE:
                quality_info['too_large'] = True
                quality_info['valid'] = False
            
            # Check blurriness using Laplacian variance
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            quality_info['blurry_score'] = round(laplacian_var, 2)
            
            if laplacian_var < self.BLURRY_THRESHOLD:
                quality_info['blurry'] = True
            
        except Exception as e:
            quality_info['valid'] = False
            quality_info['corrupted'] = True
            quality_info['error'] = f"Error processing image: {str(e)}"
        
        return quality_info
    
    def check_annotation_integrity(self, annotation_path: str, 
                                   image_name: str = None) -> Dict:
        """
        Check annotation file integrity.
        
        Returns:
            dict: Annotation validation details
        """
        annotation_info = {
            'path': annotation_path,
            'valid': True,
            'corrupted': False,
            'empty': False,
            'format': None,
            'error': None
        }
        
        try:
            if not os.path.exists(annotation_path):
                annotation_info['valid'] = False
                annotation_info['error'] = "Annotation file not found"
                return annotation_info
            
            file_size = os.path.getsize(annotation_path)
            if file_size == 0:
                annotation_info['empty'] = True
                annotation_info['valid'] = False
                return annotation_info
            
            # Determine format and validate
            ext = Path(annotation_path).suffix.lower()
            annotation_info['format'] = ext
            
            if ext in {'.json', '.yaml', '.yml'}:
                with open(annotation_path, 'r', encoding='utf-8') as f:
                    if ext == '.json':
                        json.load(f)
                    # YAML validation can be added if pyyaml is available
            
            elif ext == '.xml':
                import xml.etree.ElementTree as ET
                ET.parse(annotation_path)
            
        except json.JSONDecodeError as e:
            annotation_info['corrupted'] = True
            annotation_info['valid'] = False
            annotation_info['error'] = f"Invalid JSON: {str(e)}"
        except Exception as e:
            annotation_info['corrupted'] = True
            annotation_info['valid'] = False
            annotation_info['error'] = f"Error validating annotation: {str(e)}"
        
        return annotation_info


class DuplicateDetector:
    """Detects duplicate images using perceptual hashing."""
    
    def __init__(self):
        self.hash_map = {}
        self.duplicates = []
    
    def get_image_hash(self, image_path: str) -> Optional[str]:
        """
        Calculate MD5 hash of image file (fast detection).
        
        Returns:
            str: Hex digest of MD5 hash
        """
        try:
            hasher = hashlib.md5()
            with open(image_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"Error hashing image {image_path}: {e}")
            return None
    
    def get_perceptual_hash(self, image_path: str) -> Optional[str]:
        """
        Calculate perceptual hash (detect similar images).
        Uses average hash algorithm.
        
        Returns:
            str: Hex hash of resized image
        """
        try:
            image = cv2.imread(image_path)
            if image is None:
                return None
            
            # Resize to 8x8 and convert to grayscale
            resized = cv2.resize(image, (8, 8))
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            
            # Calculate average pixel value
            avg = gray.mean()
            
            # Hash based on comparison to average
            hash_bits = (gray > avg).flatten()
            return ''.join(hash_bits.astype(int).astype(str))
        except Exception as e:
            logger.error(f"Error calculating perceptual hash: {e}")
            return None
    
    def find_duplicates(self, image_paths: List[str]) -> Dict:
        """
        Find duplicate images in a list.
        
        Returns:
            dict: Mapping of hash to list of duplicate file paths
        """
        hash_map = {}
        duplicates = {}
        
        for path in image_paths:
            file_hash = self.get_image_hash(path)
            
            if file_hash is None:
                continue
            
            if file_hash not in hash_map:
                hash_map[file_hash] = []
            
            hash_map[file_hash].append(path)
        
        # Filter to only duplicates
        for hash_val, paths in hash_map.items():
            if len(paths) > 1:
                duplicates[hash_val] = paths
        
        return duplicates


class DatasetMerger:
    """
    Main dataset merger engine.
    Orchestrates validation, duplicate detection, and ZIP creation.
    """
    
    def __init__(self, output_dir: str, temp_dir: str = None):
        """
        Initialize merger.
        
        Args:
            output_dir: Directory for final ZIP files
            temp_dir: Temporary directory for merge operations
        """
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir or '/tmp/dataset_merge')
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        self.validator = DatasetValidator()
        self.duplicate_detector = DuplicateDetector()
        self.merge_metadata = {}
    
    # ─────────────────────────────────────────────────────────────────────────
    # CLASS EXTRACTION
    # ─────────────────────────────────────────────────────────────────────────

    def extract_classes_from_dataset(self, dataset_path: str) -> Dict:
        """
        Extract class names from a dataset.

        Strategy (in order of preference):
          1. Read 'names' list from data.yaml
          2. Collect unique integer class IDs from YOLO .txt labels and
             return them as strings ("class_0", "class_1", …)

        Returns:
            {
              "class_names": ["mask", "no-mask"],   # ordered list
              "source": "yaml" | "labels"
            }
        """
        dp = Path(dataset_path)

        # 1. Try data.yaml
        for yaml_name in ('data.yaml', 'dataset.yaml', 'data.yml'):
            yaml_path = dp / yaml_name
            if yaml_path.exists():
                try:
                    import yaml
                    with open(yaml_path, 'r') as f:
                        data = yaml.safe_load(f)
                    names = data.get('names', [])
                    if names:
                        return {'class_names': list(names), 'source': 'yaml'}
                except Exception as e:
                    logger.warning(f"Could not parse {yaml_path}: {e}")

        # 2. Scan YOLO .txt labels for unique class IDs
        struct = self.validator.validate_dataset_structure(dataset_path)
        label_dirs = struct.get('annotation_dirs', [])
        seen_ids: set = set()
        for lbl_dir in label_dirs:
            lbl_path = Path(lbl_dir)
            if not lbl_path.is_dir():
                continue
            for f in lbl_path.iterdir():
                if f.suffix == '.txt':
                    try:
                        for line in f.read_text().splitlines():
                            parts = line.strip().split()
                            if parts:
                                seen_ids.add(int(parts[0]))
                    except Exception:
                        pass

        if seen_ids:
            class_names = [f"class_{i}" for i in sorted(seen_ids)]
            return {'class_names': class_names, 'source': 'labels'}

        return {'class_names': [], 'source': 'unknown'}

    # ─────────────────────────────────────────────────────────────────────────
    # ANALYSIS
    # ─────────────────────────────────────────────────────────────────────────

    def analyze_datasets(self, dataset_paths: List[str]) -> Dict:
        """
        Analyze multiple datasets for quality issues AND extract class info.

        Returns:
            dict: Complete analysis report including per-dataset class names
                  and a 'dataset_label_map' for the class mapping UI.
        """
        analysis = {
            'datasets': {},
            'total_images': 0,
            'total_annotations': 0,
            'duplicates_found': 0,
            'corrupted_files': 0,
            'blurry_images': 0,
            # Class info for the mapping UI
            'all_classes': [],          # deduplicated union of all class names
            'dataset_label_map': {},    # {dataset_path: {"class_names": [...], "source": ...}}
            'timestamp': datetime.now().isoformat()
        }

        all_image_paths = []
        all_classes_set: set = set()

        for idx, dataset_path in enumerate(dataset_paths):
            logger.info(f"Analyzing dataset {idx + 1}/{len(dataset_paths)}: {dataset_path}")

            # Extract class names first
            class_info = self.extract_classes_from_dataset(dataset_path)
            analysis['dataset_label_map'][dataset_path] = class_info
            for cls in class_info['class_names']:
                all_classes_set.add(cls)

            # Validate structure
            struct_validation = self.validator.validate_dataset_structure(dataset_path)

            if not struct_validation['valid']:
                analysis['datasets'][dataset_path] = {
                    'valid': False,
                    'errors': struct_validation['errors'],
                    'class_names': class_info['class_names'],
                }
                continue

            dataset_info = {
                'valid': True,
                'class_names': class_info['class_names'],
                'images': [],
                'annotations': [],
                'quality_issues': {
                    'corrupted': [],
                    'blurry': [],
                    'too_small': [],
                    'too_large': []
                }
            }

            # Analyze images — iterate over ALL image dirs (handles YOLO-split)
            for img_dir_str in struct_validation.get('image_dirs', []) or (
                    [struct_validation['images_path']] if struct_validation['images_path'] else []):
                images_dir = Path(img_dir_str)
                if not images_dir.is_dir():
                    continue
                for image_file in images_dir.iterdir():
                    if image_file.suffix.lower() in self.validator.VALID_IMAGE_EXTENSIONS:
                        quality = self.validator.check_image_quality(str(image_file))

                        dataset_info['images'].append({
                            'name': image_file.name,
                            'path': str(image_file),
                            'quality': quality
                        })
                        all_image_paths.append(str(image_file))

                        if quality['corrupted']:
                            dataset_info['quality_issues']['corrupted'].append(image_file.name)
                        if quality['blurry']:
                            dataset_info['quality_issues']['blurry'].append(image_file.name)
                        if quality['too_small']:
                            dataset_info['quality_issues']['too_small'].append(image_file.name)
                        if quality['too_large']:
                            dataset_info['quality_issues']['too_large'].append(image_file.name)

            # Analyze annotations — iterate over ALL annotation dirs
            for ann_dir_str in struct_validation.get('annotation_dirs', []) or (
                    [struct_validation['annotations_path']] if struct_validation['annotations_path'] else []):
                annotations_dir = Path(ann_dir_str)
                if not annotations_dir.is_dir():
                    continue
                for ann_file in annotations_dir.iterdir():
                    if ann_file.suffix.lower() in self.validator.VALID_ANNOTATION_EXTENSIONS:
                        ann_info = self.validator.check_annotation_integrity(str(ann_file))
                        dataset_info['annotations'].append({
                            'name': ann_file.name,
                            'path': str(ann_file),
                            'valid': ann_info['valid'],
                            'issues': ann_info
                        })

            analysis['datasets'][dataset_path] = dataset_info
            analysis['total_images'] += len(dataset_info['images'])
            analysis['total_annotations'] += len(dataset_info['annotations'])
            analysis['corrupted_files'] += len(dataset_info['quality_issues']['corrupted'])
            analysis['blurry_images'] += len(dataset_info['quality_issues']['blurry'])

        # Deduplicated class union (sorted for stable ordering)
        analysis['all_classes'] = sorted(all_classes_set)

        # Detect duplicates across all datasets
        if all_image_paths:
            duplicates = self.duplicate_detector.find_duplicates(all_image_paths)
            analysis['duplicates_found'] = len(duplicates)
            analysis['duplicate_details'] = duplicates

        return analysis

    
    def merge_datasets(self, dataset_paths: List[str],
                       merge_name: str,
                       exclude_items: Dict = None,
                       remove_duplicates: bool = True,
                       remove_blurry: bool = False,
                       remove_corrupted: bool = True,
                       class_mappings: Optional[Dict[str, List[str]]] = None) -> Tuple[str, Dict]:
        """
        Merge multiple datasets with quality control and optional class remapping.

        Args:
            dataset_paths:   List of dataset directory paths
            merge_name:      Name for merged dataset (no spaces/special chars)
            exclude_items:   Dict {'images': [...], 'annotations': [...]}
            remove_duplicates/blurry/corrupted: quality filters
            class_mappings:  Optional dict mapping target class name → list of
                             source class names to merge into it.
                             e.g. {"with_mask": ["mask", "person_with_mask"],
                                   "no_mask":   ["no-mask", "person_without_mask"]}
                             Classes not mentioned are kept as-is.

        Returns:
            tuple: (path_to_zip_file, merge_metadata_dict)
        """
        if not merge_name:
            raise ValueError("Merge name is required")

        # Sanitize merge name
        merge_name = "".join(c for c in merge_name if c.isalnum() or c in '_-')

        merge_dir = self.temp_dir / merge_name
        merge_dir.mkdir(parents=True, exist_ok=True)

        for split in ['train', 'valid', 'test']:
            (merge_dir / split / 'images').mkdir(parents=True, exist_ok=True)
            (merge_dir / split / 'labels').mkdir(parents=True, exist_ok=True)

        exclude_items = exclude_items or {'images': [], 'annotations': []}

        def get_split(path: Path) -> str:
            parts = [p.lower() for p in path.parts]
            if 'test' in parts: return 'test'
            if 'valid' in parts or 'val' in parts: return 'valid'
            return 'train'

        # ── Build class-remapping tables ──────────────────────────────────────
        # class_mappings = {"target_name": ["src_cls1", "src_cls2"], ...}
        # We build per-dataset lookup: {dataset_path: {src_int_id -> target_int_id}}
        # Final class list = sorted target names from mappings + unmapped pass-throughs

        final_class_list: List[str] = []   # final ordered list for data.yaml
        # source_name -> target_int_id  (global lookup built below)
        source_name_to_target_id: Dict[str, int] = {}

        if class_mappings:
            # Build ordered final class list from mapping keys
            final_class_list = list(class_mappings.keys())
            for target_idx, (target_name, source_names) in enumerate(class_mappings.items()):
                for src_name in source_names:
                    source_name_to_target_id[src_name] = target_idx

        # Per-dataset int->int remap: dataset_path → {old_int: new_int}
        dataset_remap: Dict[str, Dict[int, int]] = {}
        for dataset_path in dataset_paths:
            class_info = self.extract_classes_from_dataset(dataset_path)
            src_names = class_info['class_names']     # index = original class ID
            remap: Dict[int, int] = {}

            if class_mappings:
                for src_idx, src_name in enumerate(src_names):
                    if src_name in source_name_to_target_id:
                        remap[src_idx] = source_name_to_target_id[src_name]
                    # else: annotation with this class ID will be dropped
            else:
                # No mappings — keep classes as-is, build a union mapping
                for src_idx, src_name in enumerate(src_names):
                    if src_name not in final_class_list:
                        final_class_list.append(src_name)
                    remap[src_idx] = final_class_list.index(src_name)

            dataset_remap[dataset_path] = remap

        metadata = {
            'merge_name': merge_name,
            'timestamp': datetime.now().isoformat(),
            'source_datasets': dataset_paths,
            'final_class_list': final_class_list,
            'class_mappings': class_mappings or {},
            'merged_images': [],
            'merged_annotations': [],
            'excluded_items': exclude_items,
            'quality_control': {
                'remove_duplicates': remove_duplicates,
                'remove_blurry': remove_blurry,
                'remove_corrupted': remove_corrupted,
                'stats': {
                    'duplicates_removed': 0,
                    'blurry_removed': 0,
                    'corrupted_removed': 0
                }
            }
        }

        processed_hashes = set()

        # ── Merge images ──────────────────────────────────────────────────────
        for dataset_path in dataset_paths:
            struct = self.validator.validate_dataset_structure(dataset_path)
            all_img_dirs = struct.get('image_dirs') or (
                [struct['images_path']] if struct.get('images_path') else [])

            if not all_img_dirs:
                continue

            for images_path in [Path(d) for d in all_img_dirs]:
                if not images_path.exists():
                    continue

                for image_file in images_path.iterdir():
                    if image_file.suffix.lower() not in self.validator.VALID_IMAGE_EXTENSIONS:
                        continue

                    if image_file.name in exclude_items['images']:
                        logger.info(f"Excluding image: {image_file.name}")
                        continue

                    if remove_duplicates:
                        file_hash = self.duplicate_detector.get_image_hash(str(image_file))
                        if file_hash in processed_hashes:
                            logger.info(f"Skipping duplicate: {image_file.name}")
                            metadata['quality_control']['stats']['duplicates_removed'] += 1
                            continue
                        if file_hash:
                            processed_hashes.add(file_hash)

                    quality = self.validator.check_image_quality(str(image_file))

                    if remove_corrupted and quality['corrupted']:
                        logger.info(f"Removing corrupted image: {image_file.name}")
                        metadata['quality_control']['stats']['corrupted_removed'] += 1
                        continue

                    if remove_blurry and quality['blurry']:
                        logger.info(f"Removing blurry image: {image_file.name}")
                        metadata['quality_control']['stats']['blurry_removed'] += 1
                        continue

                    split = get_split(images_path)
                    dest_path = merge_dir / split / 'images' / image_file.name
                    shutil.copy2(str(image_file), str(dest_path))
                    metadata['merged_images'].append(image_file.name)

        # ── Merge & remap annotations ─────────────────────────────────────────
        for dataset_path in dataset_paths:
            struct = self.validator.validate_dataset_structure(dataset_path)
            all_ann_dirs = struct.get('annotation_dirs') or (
                [struct['annotations_path']] if struct.get('annotations_path') else [])
            remap = dataset_remap.get(dataset_path, {})

            for annotations_path in [Path(d) for d in all_ann_dirs]:
                if not annotations_path.exists():
                    continue

                for ann_file in annotations_path.iterdir():
                    if ann_file.suffix.lower() not in self.validator.VALID_ANNOTATION_EXTENSIONS:
                        continue

                    if ann_file.name in exclude_items.get('annotations', []):
                        logger.info(f"Excluding annotation: {ann_file.name}")
                        continue

                    ann_info = self.validator.check_annotation_integrity(str(ann_file))
                    if remove_corrupted and ann_info['corrupted']:
                        logger.info(f"Removing corrupted annotation: {ann_file.name}")
                        continue

                    split = get_split(annotations_path)
                    dest_path = merge_dir / split / 'labels' / ann_file.name

                    # YOLO .txt — remap class IDs line by line
                    if ann_file.suffix == '.txt' and remap:
                        try:
                            original_lines = ann_file.read_text().splitlines()
                            remapped_lines = []
                            for line in original_lines:
                                parts = line.strip().split()
                                if not parts:
                                    continue
                                src_id = int(parts[0])
                                if src_id in remap:
                                    parts[0] = str(remap[src_id])
                                    remapped_lines.append(' '.join(parts))
                                else:
                                    # Class not in mapping — skip this box
                                    logger.debug(f"Dropping unmapped class {src_id} in {ann_file.name}")
                            if remapped_lines:
                                dest_path.write_text('\n'.join(remapped_lines) + '\n')
                                metadata['merged_annotations'].append(ann_file.name)
                        except Exception as e:
                            logger.warning(f"Could not remap {ann_file}: {e}")
                            shutil.copy2(str(ann_file), str(dest_path))
                            metadata['merged_annotations'].append(ann_file.name)
                    else:
                        shutil.copy2(str(ann_file), str(dest_path))
                        metadata['merged_annotations'].append(ann_file.name)

        # ── Write data.yaml ───────────────────────────────────────────────────
        try:
            import yaml
            data_yaml = {
                'train': 'train/images',
                'val': 'valid/images',
                'test': 'test/images',
                'nc': len(final_class_list),
                'names': final_class_list,
                'merge_info': {
                    'source_datasets': dataset_paths,
                    'class_mappings': class_mappings or {},
                    'merged_at': metadata['timestamp'],
                }
            }
            with open(merge_dir / 'data.yaml', 'w') as f:
                yaml.dump(data_yaml, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        except Exception as e:
            logger.warning(f"Could not write data.yaml: {e}")

        # ── Save metadata & package ───────────────────────────────────────────
        metadata_file = merge_dir / 'MERGE_METADATA.json'
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)

        zip_path = self._create_zip_archive(merge_dir, merge_name)
        shutil.rmtree(merge_dir, ignore_errors=True)

        self.merge_metadata[merge_name] = metadata

        logger.info(f"Merge complete: {zip_path}")
        logger.info(f"Merged images: {len(metadata['merged_images'])}")
        logger.info(f"Merged annotations: {len(metadata['merged_annotations'])}")
        logger.info(f"Final classes ({len(final_class_list)}): {final_class_list}")

        return zip_path, metadata

    
    def _create_zip_archive(self, merge_dir: Path, merge_name: str) -> str:
        """
        Create ZIP archive of merged dataset.
        
        Returns:
            str: Path to ZIP file
        """
        zip_path = self.output_dir / f"{merge_name}_merged_dataset.zip"
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(merge_dir):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(merge_dir)
                    zipf.write(file_path, arcname)
        
        logger.info(f"ZIP archive created: {zip_path}")
        return str(zip_path)
    
    def get_merge_status(self, merge_name: str) -> Optional[Dict]:
        """Get metadata for a completed merge."""
        return self.merge_metadata.get(merge_name)


# Example usage and testing
if __name__ == "__main__":
    # Initialize merger
    merger = DatasetMerger(
        output_dir="/storage/merged_datasets",
        temp_dir="/tmp/dataset_merge"
    )
    
    # Analyze datasets
    datasets = [
        "/storage/datasets/dataset_1",
        "/storage/datasets/dataset_2"
    ]
    
    analysis = merger.analyze_datasets(datasets)
    print("Analysis Report:")
    print(json.dumps(analysis, indent=2))
    
    # Merge datasets
    exclude = {
        'images': [],
        'annotations': []
    }
    
    zip_path, metadata = merger.merge_datasets(
        dataset_paths=datasets,
        merge_name="project_v1_merged",
        exclude_items=exclude,
        remove_duplicates=True,
        remove_blurry=False,
        remove_corrupted=True
    )
    
    print(f"\nMerge completed successfully!")
    print(f"ZIP file: {zip_path}")
    print(f"Metadata: {json.dumps(metadata, indent=2)}")
