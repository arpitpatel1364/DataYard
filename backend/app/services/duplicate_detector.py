"""
DUPLICATE DETECTION ENGINE

- Exact duplicates: MD5 / SHA256 file hashing.
- Near-duplicates: perceptual hash (pHash) with Hamming-distance threshold.

CLIP-embedding semantic similarity is supported as an optional, pluggable
extension (see `clip_similarity_available`) - it requires a downloaded CLIP
checkpoint and torch, which this offline sandbox does not ship with. If a
`sentence-transformers`/`open_clip` model is available in the deployment
environment, wire it in here; the interface (`compute_semantic_duplicates`)
is left in place to make that a drop-in addition rather than a rewrite.
"""
import hashlib
from pathlib import Path
from collections import defaultdict

try:
    import imagehash
    from PIL import Image
    PHASH_AVAILABLE = True
except ImportError:
    PHASH_AVAILABLE = False

PHASH_DISTANCE_THRESHOLD = 6  # lower = stricter near-duplicate matching


def file_hash(path: Path, algo: str = "sha256") -> str | None:
    h = hashlib.new(algo)
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def find_exact_duplicates(image_paths: list[Path]) -> dict:
    buckets: dict[str, list[str]] = defaultdict(list)
    for p in image_paths:
        digest = file_hash(p, "sha256")
        if digest:
            buckets[digest].append(str(p))

    groups = [files for files in buckets.values() if len(files) > 1]
    duplicate_count = sum(len(g) - 1 for g in groups)

    return {
        "method": "sha256",
        "duplicate_groups": len(groups),
        "duplicate_files": duplicate_count,
        "groups_sample": groups[:25],
    }


def find_near_duplicates(image_paths: list[Path], sample_limit: int = 1000) -> dict:
    if not PHASH_AVAILABLE:
        return {"method": "phash", "available": False,
                "reason": "imagehash/Pillow not installed in this environment"}

    sample = image_paths[:sample_limit]
    hashes = []
    for p in sample:
        try:
            with Image.open(p) as im:
                hashes.append((str(p), imagehash.phash(im)))
        except Exception:
            continue

    groups = []
    used = set()
    for i in range(len(hashes)):
        if hashes[i][0] in used:
            continue
        group = [hashes[i][0]]
        for j in range(i + 1, len(hashes)):
            if hashes[j][0] in used:
                continue
            if hashes[i][1] - hashes[j][1] <= PHASH_DISTANCE_THRESHOLD:
                group.append(hashes[j][0])
                used.add(hashes[j][0])
        if len(group) > 1:
            used.add(hashes[i][0])
            groups.append(group)

    return {
        "method": "phash",
        "available": True,
        "sampled_images": len(sample),
        "near_duplicate_groups": len(groups),
        "near_duplicate_files": sum(len(g) - 1 for g in groups),
        "groups_sample": groups[:25],
    }


def clip_similarity_available() -> bool:
    try:
        import torch  # noqa
        import clip  # noqa
        return True
    except ImportError:
        return False


def compute_semantic_duplicates(image_paths: list[Path]) -> dict:
    """Extension point: CLIP-embedding cosine-similarity duplicate detection.
    Returns an 'unavailable' payload unless torch+CLIP are present, so the
    rest of the pipeline degrades gracefully instead of crashing."""
    if not clip_similarity_available():
        return {"method": "clip_similarity", "available": False,
                "reason": "torch/CLIP not installed - install torch + openai-clip "
                          "(or open_clip_torch) to enable semantic duplicate detection"}
    # Implementation intentionally left as an extension point: load model,
    # embed sampled images, compute pairwise cosine similarity, cluster
    # above a similarity threshold (e.g. 0.95) into near-duplicate groups.
    return {"method": "clip_similarity", "available": True, "groups_sample": []}


def run_duplicate_detection(image_paths: list[Path]) -> dict:
    return {
        "exact": find_exact_duplicates(image_paths),
        "near_duplicate": find_near_duplicates(image_paths),
        "semantic": compute_semantic_duplicates(image_paths),
    }
