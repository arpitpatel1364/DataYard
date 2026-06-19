"""
DATA.YAML AUTO-DETECTION ENGINE

Given either:
  (A) a direct path to a data.yaml file
  (B) a dropped data.yaml file (path resolved by the caller)
  (C) a dataset folder (we look for data.yaml inside it, or infer structure)

...this module resolves: dataset root, train/val/test paths, classes,
class count, and basic validation (folder existence, image/label counts,
missing files) - with NO manual path entry required by the user.
"""

import yaml
from pathlib import Path
from dataclasses import dataclass, field

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
LABEL_EXTS = {".txt"}  # YOLO labels; COCO/VOC handled separately by annotation_validator


@dataclass
class SplitInfo:
    name: str
    path: str | None = None
    exists: bool = False
    image_count: int = 0
    label_count: int = 0
    missing_labels: int = 0
    images_sample: list[str] = field(default_factory=list)


@dataclass
class DetectionResult:
    dataset_root: str
    data_yaml_path: str | None
    classes: list[str]
    num_classes: int
    splits: dict[str, SplitInfo]
    dataset_type: str
    warnings: list[str] = field(default_factory=list)

    def to_summary(self) -> dict:
        return {
            "dataset_root": self.dataset_root,
            "data_yaml_path": self.data_yaml_path,
            "classes": self.num_classes,
            "class_names": self.classes,
            "dataset_type": self.dataset_type,
            "train_images": self.splits.get("train").image_count if self.splits.get("train") else 0,
            "val_images": self.splits.get("val").image_count if self.splits.get("val") else 0,
            "test_images": self.splits.get("test").image_count if self.splits.get("test") else 0,
            "warnings": self.warnings,
        }


def _resolve_split_path(root: Path, raw_value) -> Path | None:
    if raw_value is None:
        return None
    # data.yaml train/val/test may be a string path or a list of paths
    if isinstance(raw_value, list):
        raw_value = raw_value[0] if raw_value else None
        if raw_value is None:
            return None
            
    raw_str = str(raw_value)
    p = Path(raw_str)
    if not p.is_absolute():
        p = (root / raw_str).resolve()
        # Roboflow export fix: 'train: ../train/images' but train is alongside data.yaml
        if not p.exists() and raw_str.startswith("../"):
            fallback = (root / raw_str[3:]).resolve()
            if fallback.exists() or fallback.parent.exists():
                return fallback
    return p


def _count_images_and_labels(split_path: Path) -> SplitInfo:
    info = SplitInfo(name=split_path.name, path=str(split_path))
    if not split_path.exists():
        return info
    info.exists = True

    # Common YOLO layouts: <split>/images + <split>/labels, OR split itself is the images dir
    images_dir = split_path
    labels_dir = None
    if (split_path / "images").exists():
        images_dir = split_path / "images"
        labels_dir = split_path / "labels"
    else:
        # sibling "labels" folder next to an "images" folder
        sibling_labels = split_path.parent / "labels" / split_path.name
        if sibling_labels.exists():
            labels_dir = sibling_labels
        elif (split_path.parent / "labels").exists() and split_path.name == "images":
            labels_dir = split_path.parent / "labels"

    images = []
    if images_dir.exists():
        for f in images_dir.rglob("*"):
            if f.suffix.lower() in IMAGE_EXTS:
                images.append(f)

    info.image_count = len(images)
    info.images_sample = [str(p) for p in images[:5]]

    if labels_dir and labels_dir.exists():
        label_files = {f.stem for f in labels_dir.rglob("*.txt")}
        info.label_count = len(label_files)
        image_stems = {f.stem for f in images}
        info.missing_labels = len(image_stems - label_files)
    else:
        # labels might sit right next to images (same folder)
        label_files = {f.stem for f in images_dir.rglob("*.txt")} if images_dir.exists() else set()
        info.label_count = len(label_files)
        image_stems = {f.stem for f in images}
        info.missing_labels = len(image_stems - label_files) if label_files else len(images)

    return info


def find_data_yaml(input_path: str) -> Path | None:
    p = Path(input_path)
    if p.is_file() and p.suffix.lower() in {".yaml", ".yml"}:
        return p
    if p.is_dir():
        candidates = list(p.glob("data.yaml")) + list(p.glob("*.yaml")) + list(p.glob("*.yml"))
        if candidates:
            return candidates[0]
        # search one level deeper
        for sub in p.iterdir():
            if sub.is_dir():
                deeper = list(sub.glob("data.yaml"))
                if deeper:
                    return deeper[0]
    return None


def detect_dataset(input_path: str) -> DetectionResult:
    """
    Main entry point. input_path may be:
      - a direct data.yaml file path
      - a dataset root folder (we search for data.yaml, or fall back to
        inferring train/valid/test folders directly)
    """
    warnings: list[str] = []
    input_p = Path(input_path)

    if not input_p.exists():
        raise FileNotFoundError(f"Path does not exist: {input_path}")

    yaml_path = find_data_yaml(input_path)

    if yaml_path and yaml_path.exists():
        with open(yaml_path, "r", encoding="utf-8") as f:
            content = yaml.safe_load(f) or {}

        root = yaml_path.parent
        # data.yaml may itself specify an explicit "path:" root
        if content.get("path"):
            candidate_root = Path(content["path"])
            root = candidate_root if candidate_root.is_absolute() else (root / content["path"]).resolve()

        names = content.get("names", [])
        if isinstance(names, dict):
            # {0: 'person', 1: 'car'} style
            names = [names[k] for k in sorted(names.keys(), key=lambda x: int(x))]
        nc = content.get("nc", len(names))

        splits = {}
        for split_key in ("train", "val", "test"):
            raw = content.get(split_key) or content.get("valid") if split_key == "val" else content.get(split_key)
            split_path = _resolve_split_path(root, raw)
            if split_path is None:
                splits[split_key] = SplitInfo(name=split_key)
                continue
            splits[split_key] = _count_images_and_labels(split_path)
            if not splits[split_key].exists:
                warnings.append(f"{split_key} path not found: {split_path}")

        if not names:
            warnings.append("data.yaml has no 'names' field - classes unknown")

        return DetectionResult(
            dataset_root=str(root),
            data_yaml_path=str(yaml_path),
            classes=list(names),
            num_classes=int(nc) if nc else len(names),
            splits=splits,
            dataset_type="yolo",
            warnings=warnings,
        )

    # FALLBACK: no data.yaml found - infer structure directly from folder layout
    root = input_p if input_p.is_dir() else input_p.parent
    warnings.append("No data.yaml found - inferred structure from folder layout")

    splits = {}
    for split_key, aliases in (("train", ["train", "training"]),
                                ("val", ["val", "valid", "validation"]),
                                ("test", ["test", "testing"])):
        found = None
        for alias in aliases:
            candidate = root / alias
            if candidate.exists():
                found = candidate
                break
        splits[split_key] = _count_images_and_labels(found) if found else SplitInfo(name=split_key)

    # Try to discover classes from a classes.txt / labels.txt if present
    classes: list[str] = []
    for fname in ("classes.txt", "labels.txt"):
        cpath = root / fname
        if cpath.exists():
            classes = [line.strip() for line in cpath.read_text().splitlines() if line.strip()]
            break

    if not classes:
        warnings.append("No class names found (no data.yaml / classes.txt) - "
                         "class list will be empty until classes are detected from labels")

    return DetectionResult(
        dataset_root=str(root),
        data_yaml_path=None,
        classes=classes,
        num_classes=len(classes),
        splits=splits,
        dataset_type="yolo-inferred",
        warnings=warnings,
    )
