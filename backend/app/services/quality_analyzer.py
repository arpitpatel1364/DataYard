"""
IMAGE QUALITY + INTEGRITY ENGINE

Computes per-image quality metrics (blur via Laplacian variance, brightness,
contrast, noise estimate) and dataset-level aggregates. Also performs
corruption / unsupported-format checks (the "Integrity" pillar).
"""
import cv2
import numpy as np
from pathlib import Path
from PIL import Image

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

# Heuristic thresholds (tunable)
BLUR_THRESHOLD = 100.0       # Laplacian variance below this => "blurry"
DARK_THRESHOLD = 40.0        # mean brightness (0-255) below this => "too dark"
BRIGHT_THRESHOLD = 220.0     # mean brightness above this => "overexposed"
LOW_CONTRAST_THRESHOLD = 20.0


def _load_gray(path: Path):
    img = cv2.imread(str(path))
    if img is None:
        return None
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def check_corruption(path: Path) -> dict | None:
    """Returns an issue dict if the file is corrupted/unreadable, else None."""
    if path.suffix.lower() not in IMAGE_EXTS:
        return {"file": str(path), "reason": f"unsupported format: {path.suffix}"}
    try:
        with Image.open(path) as im:
            im.verify()
        return None
    except Exception as e:
        return {"file": str(path), "reason": f"corrupted/unreadable: {e}"}


def analyze_image_quality(path: Path) -> dict | None:
    gray = _load_gray(path)
    if gray is None:
        return None
    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))
    # crude noise estimate: high-frequency residual after median blur
    median = cv2.medianBlur(gray, 3)
    noise = float(np.mean(np.abs(gray.astype(np.int16) - median.astype(np.int16))))

    flags = []
    if laplacian_var < BLUR_THRESHOLD:
        flags.append("blurry")
    if brightness < DARK_THRESHOLD:
        flags.append("too_dark")
    elif brightness > BRIGHT_THRESHOLD:
        flags.append("overexposed")
    if contrast < LOW_CONTRAST_THRESHOLD:
        flags.append("low_contrast")
    if noise > 15:
        flags.append("noisy")

    return {
        "file": str(path),
        "blur_score": round(laplacian_var, 2),
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "noise": round(noise, 2),
        "flags": flags,
        "resolution": [int(gray.shape[1]), int(gray.shape[0])],
    }


def analyze_dataset_quality(image_paths: list[Path], sample_limit: int = 1500) -> dict:
    """
    Runs corruption + quality checks across a (sampled, for speed) set of
    images and aggregates dataset-level stats.
    """
    sample = image_paths[:sample_limit]
    corrupted = []
    quality_records = []
    resolutions = []

    for p in sample:
        issue = check_corruption(p)
        if issue:
            corrupted.append(issue)
            continue
        q = analyze_image_quality(p)
        if q:
            quality_records.append(q)
            resolutions.append(tuple(q["resolution"]))

    n = max(len(quality_records), 1)
    blurry = sum(1 for r in quality_records if "blurry" in r["flags"])
    dark = sum(1 for r in quality_records if "too_dark" in r["flags"])
    bright = sum(1 for r in quality_records if "overexposed" in r["flags"])
    low_contrast = sum(1 for r in quality_records if "low_contrast" in r["flags"])
    noisy = sum(1 for r in quality_records if "noisy" in r["flags"])

    unique_resolutions = len(set(resolutions))

    return {
        "sampled_images": len(sample),
        "total_dataset_images": len(image_paths),
        "corrupted_count": len(corrupted),
        "corrupted_sample": corrupted[:25],
        "avg_blur_score": round(float(np.mean([r["blur_score"] for r in quality_records])), 2) if quality_records else 0,
        "avg_brightness": round(float(np.mean([r["brightness"] for r in quality_records])), 2) if quality_records else 0,
        "avg_contrast": round(float(np.mean([r["contrast"] for r in quality_records])), 2) if quality_records else 0,
        "blurry_count": blurry,
        "dark_count": dark,
        "overexposed_count": bright,
        "low_contrast_count": low_contrast,
        "noisy_count": noisy,
        "blurry_pct": round(100 * blurry / n, 2),
        "dark_pct": round(100 * dark / n, 2),
        "overexposed_pct": round(100 * bright / n, 2),
        "resolution_diversity_count": unique_resolutions,
        "worst_samples": sorted(quality_records, key=lambda r: r["blur_score"])[:10],
    }
