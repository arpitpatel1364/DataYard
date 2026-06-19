"""
ANNOTATION VALIDATION

Validates label files against their declared format and surfaces:
  - missing annotations
  - invalid / malformed annotations
  - out-of-range class ids
  - out-of-range / degenerate bounding boxes
Per-class instance counts are also produced here, feeding the
Class Intelligence engine (distribution analysis).
"""
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict


def validate_yolo_labels(images_dir: Path, labels_dir: Path, class_names: list[str]) -> dict:
    images = [f for f in images_dir.rglob("*") if f.suffix.lower() in
              {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}] if images_dir.exists() else []
    label_map = {f.stem: f for f in labels_dir.rglob("*.txt")} if labels_dir.exists() else {}

    missing_annotations = []
    invalid_annotations = []
    per_class_instances: dict[str, int] = defaultdict(int)
    per_class_images: dict[str, set] = defaultdict(set)
    total_instances = 0
    empty_label_files = 0

    for img in images:
        label_file = label_map.get(img.stem)
        if label_file is None:
            missing_annotations.append(str(img))
            continue

        try:
            lines = [l.strip() for l in label_file.read_text().splitlines() if l.strip()]
        except Exception:
            invalid_annotations.append({"file": str(label_file), "reason": "unreadable file"})
            continue

        if not lines:
            empty_label_files += 1
            continue

        for line_no, line in enumerate(lines, start=1):
            parts = line.split()
            if len(parts) != 5:
                invalid_annotations.append({
                    "file": str(label_file), "line": line_no,
                    "reason": f"expected 5 fields (class x y w h), got {len(parts)}"
                })
                continue
            try:
                cls_id = int(float(parts[0]))
                x, y, w, h = (float(v) for v in parts[1:])
            except ValueError:
                invalid_annotations.append({
                    "file": str(label_file), "line": line_no, "reason": "non-numeric values"
                })
                continue

            if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
                invalid_annotations.append({
                    "file": str(label_file), "line": line_no,
                    "reason": "bounding box coordinates out of normalized [0,1] range"
                })
                continue

            if cls_id < 0 or (class_names and cls_id >= len(class_names)):
                invalid_annotations.append({
                    "file": str(label_file), "line": line_no,
                    "reason": f"class id {cls_id} out of range (0-{len(class_names) - 1})"
                })
                continue

            cls_name = class_names[cls_id] if class_names and cls_id < len(class_names) else str(cls_id)
            per_class_instances[cls_name] += 1
            per_class_images[cls_name].add(img.stem)
            total_instances += 1

    return {
        "format": "yolo",
        "total_images": len(images),
        "total_labels_found": len(label_map),
        "missing_annotations": len(missing_annotations),
        "missing_annotations_sample": missing_annotations[:25],
        "invalid_annotations": len(invalid_annotations),
        "invalid_annotations_sample": invalid_annotations[:25],
        "empty_label_files": empty_label_files,
        "total_instances": total_instances,
        "per_class_instances": dict(per_class_instances),
        "per_class_image_count": {k: len(v) for k, v in per_class_images.items()},
    }


def validate_coco_labels(annotation_json_path: Path) -> dict:
    if not annotation_json_path.exists():
        return {"format": "coco", "error": "annotation file not found"}
    try:
        data = json.loads(annotation_json_path.read_text())
    except Exception as e:
        return {"format": "coco", "error": f"invalid JSON: {e}"}

    cat_map = {c["id"]: c["name"] for c in data.get("categories", [])}
    per_class_instances: dict[str, int] = defaultdict(int)
    invalid_annotations = []
    for ann in data.get("annotations", []):
        bbox = ann.get("bbox")
        cat_id = ann.get("category_id")
        if not bbox or len(bbox) != 4 or any(v < 0 for v in bbox[2:]):
            invalid_annotations.append({"id": ann.get("id"), "reason": "invalid bbox"})
            continue
        cls_name = cat_map.get(cat_id, str(cat_id))
        per_class_instances[cls_name] += 1

    return {
        "format": "coco",
        "total_images": len(data.get("images", [])),
        "total_instances": sum(per_class_instances.values()),
        "invalid_annotations": len(invalid_annotations),
        "invalid_annotations_sample": invalid_annotations[:25],
        "per_class_instances": dict(per_class_instances),
        "classes": list(cat_map.values()),
    }


def validate_voc_labels(labels_dir: Path) -> dict:
    if not labels_dir.exists():
        return {"format": "voc", "error": "labels directory not found"}

    xml_files = list(labels_dir.rglob("*.xml"))
    per_class_instances: dict[str, int] = defaultdict(int)
    invalid_annotations = []
    total_instances = 0

    for xf in xml_files:
        try:
            tree = ET.parse(xf)
        except ET.ParseError as e:
            invalid_annotations.append({"file": str(xf), "reason": f"XML parse error: {e}"})
            continue
        root = tree.getroot()
        for obj in root.findall("object"):
            name_el = obj.find("name")
            bbox_el = obj.find("bndbox")
            if name_el is None or bbox_el is None:
                invalid_annotations.append({"file": str(xf), "reason": "missing name/bndbox"})
                continue
            per_class_instances[name_el.text] += 1
            total_instances += 1

    return {
        "format": "voc",
        "total_images": len(xml_files),
        "total_instances": total_instances,
        "invalid_annotations": len(invalid_annotations),
        "invalid_annotations_sample": invalid_annotations[:25],
        "per_class_instances": dict(per_class_instances),
    }


def detect_and_validate(images_dir: Path, labels_dir: Path, class_names: list[str],
                         annotation_format: str = "yolo") -> dict:
    """Dispatch to the right validator. CVAT/Label Studio typically export as
    COCO/VOC/YOLO under the hood, so those are handled via the same paths
    once exported - documented in the README as an extension point for
    direct CVAT XML / Label Studio JSON ingestion."""
    fmt = (annotation_format or "yolo").lower()
    if fmt == "coco":
        coco_json = next(iter(labels_dir.glob("*.json")), None) if labels_dir.exists() else None
        if coco_json:
            return validate_coco_labels(coco_json)
        return {"format": "coco", "error": "no COCO annotation JSON found"}
    if fmt == "voc":
        return validate_voc_labels(labels_dir)
    # default: yolo
    return validate_yolo_labels(images_dir, labels_dir, class_names)
