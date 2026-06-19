"""
AI RECOMMENDATION ENGINE

Generates Critical Issues, Suggested Fixes, Data Collection Recommendations,
Annotation Improvements, and a Training Readiness summary from a completed
health scan report. Entirely rule-based / offline - no OpenAI or other paid
API required, per the FREE OPERATION REQUIREMENT.
"""


def generate_recommendations(health_report: dict) -> list[dict]:
    recs: list[dict] = []
    scores = health_report.get("scores", {})
    annotations = health_report.get("annotations", {})
    quality = health_report.get("quality", {})
    leakage = health_report.get("leakage", {})
    duplicates = health_report.get("duplicates", {})
    structure = health_report.get("structure", {})

    # --- Critical issues ---
    for issue in structure.get("issues", []):
        recs.append({"category": "critical_issue", "severity": "critical", "message": issue})

    if annotations.get("missing_annotations", 0) > 0:
        recs.append({
            "category": "critical_issue", "severity": "high",
            "message": f"{annotations['missing_annotations']} images have no corresponding "
                       "annotation file. These will be skipped or harm training if treated as background."
        })

    if annotations.get("invalid_annotations", 0) > 0:
        recs.append({
            "category": "annotation_improvement", "severity": "high",
            "message": f"{annotations['invalid_annotations']} label lines are malformed or out of range. "
                       "Fix or remove these before training to avoid silent data corruption."
        })

    leaked = leakage.get("total_leaked_images", 0)
    if leaked > 0:
        recs.append({
            "category": "critical_issue", "severity": "critical",
            "message": f"{leaked} images leak across train/val/test splits, inflating validation/test "
                       "metrics. Remove duplicates from at least one side of each split."
        })

    dup_groups = duplicates.get("exact", {}).get("duplicate_groups", 0)
    if dup_groups:
        recs.append({
            "category": "suggested_fix", "severity": "medium",
            "message": f"{dup_groups} exact duplicate image groups found. Deduplicating will reduce "
                       "storage and avoid over-weighting repeated samples."
        })

    near_dup = duplicates.get("near_duplicate", {}).get("near_duplicate_groups", 0)
    if near_dup:
        recs.append({
            "category": "suggested_fix", "severity": "low",
            "message": f"{near_dup} groups of visually near-identical images detected (pHash). "
                       "Consider thinning these to improve diversity per sample collected."
        })

    if quality.get("blurry_pct", 0) > 10:
        recs.append({
            "category": "data_collection", "severity": "medium",
            "message": f"{quality['blurry_pct']}% of sampled images are blurry. Re-capture or filter "
                       "these to improve detector precision."
        })

    if quality.get("dark_pct", 0) > 10 or quality.get("overexposed_pct", 0) > 10:
        recs.append({
            "category": "data_collection", "severity": "medium",
            "message": "A notable share of images are too dark or overexposed - collect more "
                       "samples across varied lighting conditions."
        })

    if quality.get("corrupted_count", 0) > 0:
        recs.append({
            "category": "critical_issue", "severity": "critical",
            "message": f"{quality['corrupted_count']} corrupted or unreadable image files found - "
                       "remove or re-export these before training."
        })

    # --- Score-driven summary recommendations ---
    if scores.get("balance", 100) < 70:
        recs.append({
            "category": "data_collection", "severity": "high",
            "message": "Significant class imbalance detected at the dataset level. Prioritize "
                       "collecting more samples for under-represented classes, or apply "
                       "class-weighted loss / oversampling during training."
        })

    if scores.get("diversity", 100) < 50:
        recs.append({
            "category": "data_collection", "severity": "medium",
            "message": "Low resolution/capture diversity detected. Vary camera angles, distances, "
                       "and lighting when collecting additional samples."
        })

    health_score = scores.get("health_score", 0)
    if health_score >= 90:
        readiness_msg = "Dataset is training-ready with high confidence."
    elif health_score >= 70:
        readiness_msg = "Dataset is usable for training but has notable quality gaps worth fixing first."
    else:
        readiness_msg = "Dataset is NOT recommended for training until critical issues above are resolved."

    recs.append({"category": "training_readiness", "severity": "info", "message": readiness_msg})

    return recs
