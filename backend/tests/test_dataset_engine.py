import os
import tempfile
import shutil
import yaml
from PIL import Image

from app.services import yaml_parser, health_engine, class_intelligence


def _make_synthetic_dataset(root):
    classes = ["person", "car"]
    for split, n in (("train", 6), ("val", 2)):
        images_dir = os.path.join(root, split, "images")
        labels_dir = os.path.join(root, split, "labels")
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(labels_dir, exist_ok=True)
        for i in range(n):
            img = Image.new("RGB", (64, 64), color=(100 + i, 120, 140))
            img.save(os.path.join(images_dir, f"img{i}.jpg"))
            with open(os.path.join(labels_dir, f"img{i}.txt"), "w") as f:
                cls_id = i % 2
                f.write(f"{cls_id} 0.5 0.5 0.2 0.2\n")

    data_yaml = {
        "train": os.path.join(root, "train", "images"),
        "val": os.path.join(root, "val", "images"),
        "nc": len(classes),
        "names": classes,
    }
    with open(os.path.join(root, "data.yaml"), "w") as f:
        yaml.dump(data_yaml, f)
    return classes


def test_detect_dataset_from_yaml():
    root = tempfile.mkdtemp()
    try:
        classes = _make_synthetic_dataset(root)
        result = yaml_parser.detect_dataset(os.path.join(root, "data.yaml"))
        assert result.classes == classes
        assert result.splits["train"].image_count == 6
        assert result.splits["val"].image_count == 2
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_health_scan_runs_end_to_end():
    root = tempfile.mkdtemp()
    try:
        classes = _make_synthetic_dataset(root)
        report = health_engine.run_health_scan(
            dataset_root=root,
            splits={"train": os.path.join(root, "train"), "val": os.path.join(root, "val"), "test": None},
            class_names=classes,
            scan_mode="standard",
        )
        assert "scores" in report
        assert 0 <= report["scores"]["health_score"] <= 100
        assert report["scores"]["health_grade"] in ("A+", "A", "B", "C", "D", "F")
        assert report["counts"]["train_images"] == 6
        assert report["counts"]["val_images"] == 2
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_class_intelligence_distribution():
    per_class_instances = {"person": 100, "car": 10}
    per_class_images = {"person": 80, "car": 9}
    result = class_intelligence.run_class_intelligence(
        per_class_instances, per_class_images, [], ["person", "car"], total_images=90,
    )
    assert result["distribution"]["person"]["total_instances"] == 100
    assert result["training_readiness"]["_overall"]["imbalanced"] is True
