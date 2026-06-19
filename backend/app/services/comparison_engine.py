"""
DATASET COMPARISON ENGINE

Compares two dataset versions (each version stores a full_report JSON from
a health scan) and produces a structured diff: image/class/label deltas,
health score deltas, duplicate/leakage deltas, and added/removed classes.
Works the same regardless of source type (local/Roboflow) since both are
normalized into the same Dataset/DatasetVersion model on import.
"""


def _image_set(report: dict) -> dict:
    return report.get("counts", {})


def compare_versions(version_a: dict, version_b: dict,
                      classes_a: list[str], classes_b: list[str]) -> dict:
    counts_a = version_a.get("full_report", {}).get("counts", {})
    counts_b = version_b.get("full_report", {}).get("counts", {})

    added_classes = sorted(set(classes_b) - set(classes_a))
    removed_classes = sorted(set(classes_a) - set(classes_b))
    common_classes = sorted(set(classes_a) & set(classes_b))

    ann_a = version_a.get("full_report", {}).get("annotations", {}).get("per_class_instances", {})
    ann_b = version_b.get("full_report", {}).get("annotations", {}).get("per_class_instances", {})

    per_class_change = {}
    for cls in set(list(ann_a.keys()) + list(ann_b.keys())):
        a_count = ann_a.get(cls, 0)
        b_count = ann_b.get(cls, 0)
        per_class_change[cls] = {
            "before": a_count, "after": b_count, "delta": b_count - a_count,
        }

    image_delta = {
        "train_images": counts_b.get("train_images", 0) - counts_a.get("train_images", 0),
        "val_images": counts_b.get("val_images", 0) - counts_a.get("val_images", 0),
        "test_images": counts_b.get("test_images", 0) - counts_a.get("test_images", 0),
        "total_images": counts_b.get("total_images", 0) - counts_a.get("total_images", 0),
    }

    score_delta = {
        "health_score": round(version_b.get("health_score", 0) - version_a.get("health_score", 0), 2),
        "integrity_score": round(version_b.get("integrity_score", 0) - version_a.get("integrity_score", 0), 2),
        "annotation_score": round(version_b.get("annotation_score", 0) - version_a.get("annotation_score", 0), 2),
        "balance_score": round(version_b.get("balance_score", 0) - version_a.get("balance_score", 0), 2),
        "image_quality_score": round(version_b.get("image_quality_score", 0) - version_a.get("image_quality_score", 0), 2),
        "diversity_score": round(version_b.get("diversity_score", 0) - version_a.get("diversity_score", 0), 2),
        "leakage_score": round(version_b.get("leakage_score", 0) - version_a.get("leakage_score", 0), 2),
    }

    stats_a = {
        "health_score": version_a.get("health_score", 0),
        "health_grade": version_a.get("health_grade", "F"),
        "total_images": counts_a.get("total_images", 0),
        "train_images": counts_a.get("train_images", 0),
        "val_images": counts_a.get("val_images", 0),
        "test_images": counts_a.get("test_images", 0),
        "total_classes": len(classes_a),
        "classes": classes_a,
        "class_counts": {c: ann_a.get(c, 0) for c in classes_a},
        "scores": {
            "Integrity": version_a.get("integrity_score", 0),
            "Annotation": version_a.get("annotation_score", 0),
            "Balance": version_a.get("balance_score", 0),
            "Image Quality": version_a.get("image_quality_score", 0),
            "Diversity": version_a.get("diversity_score", 0),
        }
    }

    stats_b = {
        "health_score": version_b.get("health_score", 0),
        "health_grade": version_b.get("health_grade", "F"),
        "total_images": counts_b.get("total_images", 0),
        "train_images": counts_b.get("train_images", 0),
        "val_images": counts_b.get("val_images", 0),
        "test_images": counts_b.get("test_images", 0),
        "total_classes": len(classes_b),
        "classes": classes_b,
        "class_counts": {c: ann_b.get(c, 0) for c in classes_b},
        "scores": {
            "Integrity": version_b.get("integrity_score", 0),
            "Annotation": version_b.get("annotation_score", 0),
            "Balance": version_b.get("balance_score", 0),
            "Image Quality": version_b.get("image_quality_score", 0),
            "Diversity": version_b.get("diversity_score", 0),
        }
    }

    return {
        "stats_a": stats_a,
        "stats_b": stats_b,
        "added_classes": added_classes,
        "removed_classes": removed_classes,
        "common_classes": common_classes,
        "per_class_instance_change": per_class_change,
        "image_delta": image_delta,
        "score_delta": score_delta,
        "summary": {
            "a_health_grade": version_a.get("health_grade"),
            "b_health_grade": version_b.get("health_grade"),
            "improved": score_delta["health_score"] > 0,
        },
    }
