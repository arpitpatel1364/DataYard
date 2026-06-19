"""
LEAKAGE DETECTION ENGINE

Detects images that appear in more than one split (train/val/test) by
comparing exact content hashes (SHA256) across splits - the canonical,
filename-agnostic way to catch real data leakage (e.g. someone copy-pasted
the same image into two folders under different names).
"""
from pathlib import Path
from app.services.duplicate_detector import file_hash


def _hash_set(image_paths: list[Path]) -> dict[str, str]:
    """Returns {sha256_hash: filepath} for the given images."""
    out = {}
    for p in image_paths:
        digest = file_hash(p, "sha256")
        if digest:
            out[digest] = str(p)
    return out


def detect_leakage(train_images: list[Path], val_images: list[Path],
                    test_images: list[Path]) -> dict:
    train_h = _hash_set(train_images)
    val_h = _hash_set(val_images)
    test_h = _hash_set(test_images)

    train_val = set(train_h) & set(val_h)
    train_test = set(train_h) & set(test_h)
    val_test = set(val_h) & set(test_h)

    def pairs(common: set, a: dict, b: dict, limit=25):
        return [{"a": a[h], "b": b[h]} for h in list(common)[:limit]]

    return {
        "train_val_leaks": len(train_val),
        "train_test_leaks": len(train_test),
        "val_test_leaks": len(val_test),
        "train_val_sample": pairs(train_val, train_h, val_h),
        "train_test_sample": pairs(train_test, train_h, test_h),
        "val_test_sample": pairs(val_test, val_h, test_h),
        "total_leaked_images": len(train_val) + len(train_test) + len(val_test),
    }
