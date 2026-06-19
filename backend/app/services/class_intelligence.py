"""
ADVANCED CLASS INTELLIGENCE ENGINE

For a set of user-selected classes, computes:
  - Distribution Analysis (instances, image count, density, frequency)
  - Dataset Quality flags relevant to those classes
  - Diversity signals (scale / lighting / background, heuristically)
  - Training Readiness (sufficiency, recommended sample counts, risk)
  - Recommendations (collect more / merge / split / improve annotations)
"""

# Heuristic minimum recommended instance count per class for a reasonably
# trainable detector - intentionally conservative & documented as tunable.
RECOMMENDED_MIN_INSTANCES = 1500
RECOMMENDED_MIN_IMAGES = 500
IMBALANCE_RATIO_WARNING = 5.0   # max/min instance ratio considered "imbalanced"


def distribution_analysis(per_class_instances: dict[str, int],
                           per_class_images: dict[str, int],
                           selected_classes: list[str]) -> dict:
    total_instances = sum(per_class_instances.values()) or 1
    result = {}
    for cls in selected_classes:
        instances = per_class_instances.get(cls, 0)
        images = per_class_images.get(cls, 0)
        result[cls] = {
            "total_instances": instances,
            "image_count": images,
            "density_per_image": round(instances / images, 2) if images else 0,
            "frequency_pct": round(100 * instances / total_instances, 2),
        }
    return result


def class_quality_flags(per_class_instances: dict[str, int],
                         invalid_annotations: list[dict],
                         selected_classes: list[str]) -> dict:
    out = {}
    for cls in selected_classes:
        related_invalid = [a for a in invalid_annotations if cls in str(a.get("reason", ""))]
        out[cls] = {
            "missing_annotations": per_class_instances.get(cls, 0) == 0,
            "invalid_annotation_hits": len(related_invalid),
        }
    return out


def diversity_signals(per_class_images: dict[str, int], selected_classes: list[str],
                       total_images: int) -> dict:
    """
    Heuristic diversity scoring (0-100) per class based on how broadly the
    class is spread across the dataset's images. True scale/lighting/
    background diversity requires per-instance crops + clustering; this
    gives a fast, defensible proxy and is documented as an extension point
    for a deeper visual-embedding-based diversity score.
    """
    out = {}
    for cls in selected_classes:
        images = per_class_images.get(cls, 0)
        spread_pct = round(100 * images / total_images, 2) if total_images else 0
        out[cls] = {
            "spread_pct_of_dataset": spread_pct,
            "diversity_note": (
                "Well distributed across the dataset" if spread_pct > 15 else
                "Concentrated in a small subset of images - may limit "
                "lighting/background/scale diversity"
            ),
        }
    return out


def training_readiness(per_class_instances: dict[str, int], per_class_images: dict[str, int],
                        selected_classes: list[str]) -> dict:
    out = {}
    counts = [per_class_instances.get(c, 0) for c in selected_classes if per_class_instances.get(c, 0) > 0]
    max_count = max(counts) if counts else 0
    min_count = min(counts) if counts else 0
    imbalance_ratio = round(max_count / min_count, 2) if min_count else None

    for cls in selected_classes:
        instances = per_class_instances.get(cls, 0)
        images = per_class_images.get(cls, 0)
        sufficiency = "sufficient" if instances >= RECOMMENDED_MIN_INSTANCES else (
            "marginal" if instances >= RECOMMENDED_MIN_INSTANCES * 0.4 else "insufficient"
        )
        gap = max(0, RECOMMENDED_MIN_INSTANCES - instances)
        risk = "low" if sufficiency == "sufficient" else ("medium" if sufficiency == "marginal" else "high")

        out[cls] = {
            "instances": instances,
            "images": images,
            "sufficiency": sufficiency,
            "recommended_additional_instances": gap,
            "risk": risk,
        }

    out["_overall"] = {
        "class_imbalance_ratio": imbalance_ratio,
        "imbalanced": bool(imbalance_ratio and imbalance_ratio > IMBALANCE_RATIO_WARNING),
    }
    return out


def generate_class_recommendations(readiness: dict, distribution: dict) -> list[dict]:
    recs = []
    overall = readiness.get("_overall", {})
    if overall.get("imbalanced"):
        recs.append({
            "type": "class_imbalance",
            "severity": "high",
            "message": "Significant class imbalance detected (ratio > "
                       f"{IMBALANCE_RATIO_WARNING}x). Consider collecting more samples "
                       "for under-represented classes or applying class-balanced sampling/loss weighting.",
        })

    for cls, info in readiness.items():
        if cls == "_overall":
            continue
        if info["sufficiency"] == "insufficient":
            recs.append({
                "type": "collect_more_samples",
                "severity": "high",
                "class": cls,
                "message": f"'{cls}' has only {info['instances']} instances - collect at least "
                           f"{info['recommended_additional_instances']} more for reliable training.",
            })
        elif info["sufficiency"] == "marginal":
            recs.append({
                "type": "collect_more_samples",
                "severity": "medium",
                "class": cls,
                "message": f"'{cls}' is marginally sufficient ({info['instances']} instances). "
                           "More data would improve robustness.",
            })

    for cls, dist in distribution.items():
        if dist["image_count"] and dist["density_per_image"] > 8:
            recs.append({
                "type": "annotation_review",
                "severity": "low",
                "class": cls,
                "message": f"'{cls}' has a high average density per image "
                           f"({dist['density_per_image']}) - verify annotations aren't over-segmented "
                           "or duplicated.",
            })

    return recs


def run_class_intelligence(per_class_instances: dict[str, int], per_class_images: dict[str, int],
                            invalid_annotations: list[dict], selected_classes: list[str],
                            total_images: int) -> dict:
    distribution = distribution_analysis(per_class_instances, per_class_images, selected_classes)
    quality = class_quality_flags(per_class_instances, invalid_annotations, selected_classes)
    diversity = diversity_signals(per_class_images, selected_classes, total_images)
    readiness = training_readiness(per_class_instances, per_class_images, selected_classes)
    recommendations = generate_class_recommendations(readiness, distribution)

    return {
        "distribution": distribution,
        "quality": quality,
        "diversity": diversity,
        "training_readiness": readiness,
        "recommendations": recommendations,
    }
