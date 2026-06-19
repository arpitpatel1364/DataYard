"""
DATASET HEALTH ENGINE

Orchestrates: structure checks, integrity, annotation validation, quality,
duplicate detection, leakage detection, and diversity - then rolls
everything into a single weighted Health Score + Grade.

Weights (per spec):
    Integrity             25%
    Annotation Quality    25%
    Balance               15%
    Image Quality         15%
    Diversity             10%
    Leakage               10%
"""
from pathlib import Path

from app.services import quality_analyzer, duplicate_detector, leakage_detector, annotation_validator

WEIGHTS = {
    "integrity": 0.25,
    "annotation": 0.25,
    "balance": 0.15,
    "image_quality": 0.15,
    "diversity": 0.10,
    "leakage": 0.10,
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def grade_for_score(score: float) -> str:
    if score >= 96:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _list_images(split_path: Path | None) -> list[Path]:
    if not split_path or not split_path.exists():
        return []
    images_dir = split_path / "images" if (split_path / "images").exists() else split_path
    return [f for f in images_dir.rglob("*") if f.suffix.lower() in IMAGE_EXTS]


def _resolve_labels_dir(split_path: Path | None) -> Path | None:
    if not split_path:
        return None
    if (split_path / "labels").exists():
        return split_path / "labels"
    sibling = split_path.parent / "labels" / split_path.name
    if sibling.exists():
        return sibling
    if split_path.name == "images" and (split_path.parent / "labels").exists():
        return split_path.parent / "labels"
    return split_path  # labels alongside images


def _score_integrity(images: list[Path], corrupted_count: int) -> float:
    if not images:
        return 0.0
    ratio_ok = 1 - (corrupted_count / len(images))
    return max(0.0, min(100.0, ratio_ok * 100))


def _score_annotation(annotation_result: dict, total_images: int) -> float:
    if total_images == 0:
        return 0.0
    missing = annotation_result.get("missing_annotations", 0)
    invalid = annotation_result.get("invalid_annotations", 0)
    total_labels = annotation_result.get("total_labels_found", 0) or 1
    missing_penalty = missing / total_images
    invalid_penalty = min(1.0, invalid / max(total_labels, 1))
    score = 100 * (1 - 0.6 * missing_penalty - 0.4 * invalid_penalty)
    return max(0.0, min(100.0, score))


def _score_balance(per_class_instances: dict[str, int]) -> float:
    counts = [c for c in per_class_instances.values() if c > 0]
    if len(counts) < 2:
        return 100.0 if counts else 0.0
    ratio = max(counts) / min(counts)
    # ratio of 1 => perfect balance => 100. Decays as ratio grows.
    score = 100 / (1 + 0.05 * (ratio - 1))
    return max(0.0, min(100.0, score))


def _score_image_quality(quality_result: dict) -> float:
    if quality_result.get("sampled_images", 0) == 0:
        return 0.0
    bad_pct = (quality_result.get("blurry_pct", 0) + quality_result.get("dark_pct", 0) +
               quality_result.get("overexposed_pct", 0)) / 3
    return max(0.0, min(100.0, 100 - bad_pct))


def _score_diversity(quality_result: dict, sampled_images: int) -> float:
    if sampled_images == 0:
        return 0.0
    unique_res = quality_result.get("resolution_diversity_count", 0)
    # more unique resolutions relative to sample size implies more capture diversity
    ratio = min(1.0, unique_res / max(1, sampled_images * 0.15))
    return round(ratio * 100, 2)


def _score_leakage(leakage_result: dict, total_images: int) -> float:
    if total_images == 0:
        return 100.0
    leaked = leakage_result.get("total_leaked_images", 0)
    penalty = min(1.0, leaked / max(1, total_images))
    return max(0.0, min(100.0, 100 * (1 - penalty)))


def run_health_scan(dataset_root: str, splits: dict, class_names: list[str],
                     annotation_format: str = "yolo", scan_mode: str = "standard") -> dict:
    """
    splits: {"train": "<path or None>", "val": "...", "test": "..."}
    scan_mode: quick | standard | deep - controls how much work is done.
    """
    split_paths = {k: (Path(v) if v else None) for k, v in splits.items()}
    images_by_split = {k: _list_images(p) for k, p in split_paths.items()}
    all_images = [img for imgs in images_by_split.values() for img in imgs]

    report: dict = {"scan_mode": scan_mode, "dataset_root": dataset_root}

    # ---- STRUCTURE ----
    structure_issues = []
    for split_name, p in split_paths.items():
        if p and not p.exists():
            structure_issues.append(f"{split_name} path missing: {p}")
    report["structure"] = {
        "issues": structure_issues,
        "splits_found": {k: bool(v and v.exists()) for k, v in split_paths.items()},
    }

    # ---- ANNOTATIONS (all modes) ----
    train_labels_dir = _resolve_labels_dir(split_paths.get("train"))
    annotation_result = annotation_validator.detect_and_validate(
        split_paths.get("train") or Path("."), train_labels_dir or Path("."),
        class_names, annotation_format
    ) if split_paths.get("train") else {"format": annotation_format, "total_images": 0}
    report["annotations"] = annotation_result

    # ---- INTEGRITY + QUALITY (standard & deep) ----
    corrupted_count = 0
    quality_result = {"sampled_images": 0}
    if scan_mode in ("standard", "deep"):
        sample_limit = 800 if scan_mode == "standard" else 3000
        quality_result = quality_analyzer.analyze_dataset_quality(all_images, sample_limit=sample_limit)
        corrupted_count = quality_result.get("corrupted_count", 0)
    report["quality"] = quality_result

    # ---- DUPLICATES + LEAKAGE (deep only, expensive) ----
    duplicate_result = {}
    leakage_result = {"total_leaked_images": 0}
    if scan_mode == "deep":
        duplicate_result = duplicate_detector.run_duplicate_detection(all_images)
        leakage_result = leakage_detector.detect_leakage(
            images_by_split.get("train", []), images_by_split.get("val", []),
            images_by_split.get("test", [])
        )
    report["duplicates"] = duplicate_result
    report["leakage"] = leakage_result

    # ---- SCORING ----
    per_class_instances = annotation_result.get("per_class_instances", {})
    integrity_score = _score_integrity(all_images, corrupted_count)
    annotation_score = _score_annotation(annotation_result, annotation_result.get("total_images", 0))
    balance_score = _score_balance(per_class_instances)
    image_quality_score = _score_image_quality(quality_result)
    diversity_score = _score_diversity(quality_result, quality_result.get("sampled_images", 0))
    leakage_score = _score_leakage(leakage_result, len(all_images))

    health_score = round(
        integrity_score * WEIGHTS["integrity"] +
        annotation_score * WEIGHTS["annotation"] +
        balance_score * WEIGHTS["balance"] +
        image_quality_score * WEIGHTS["image_quality"] +
        diversity_score * WEIGHTS["diversity"] +
        leakage_score * WEIGHTS["leakage"], 2
    )

    report["scores"] = {
        "integrity": round(integrity_score, 2),
        "annotation": round(annotation_score, 2),
        "balance": round(balance_score, 2),
        "image_quality": round(image_quality_score, 2),
        "diversity": round(diversity_score, 2),
        "leakage": round(leakage_score, 2),
        "health_score": health_score,
        "health_grade": grade_for_score(health_score),
    }

    report["counts"] = {
        "train_images": len(images_by_split.get("train", [])),
        "val_images": len(images_by_split.get("val", [])),
        "test_images": len(images_by_split.get("test", [])),
        "total_images": len(all_images),
    }

    return report
