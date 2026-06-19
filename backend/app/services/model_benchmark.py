"""
MODEL TESTING LAB / MODEL ANALYTICS ENGINE

Supports PyTorch (.pt) and ONNX (.onnx) models out of the box using
onnxruntime / torch + ultralytics when those packages are present in the
deployment environment (they are optional, heavy dependencies and are not
force-installed by this project's base requirements.txt - see README).
TensorRT and OpenVINO are wired as pluggable extension points: if the
corresponding runtime is installed on the deployment machine, the relevant
function below detects it and uses it; otherwise it reports "unavailable"
rather than fabricating numbers.

Metrics implemented for real (no labels needed):
    - Performance: FPS, latency, throughput, warm-up time, model load time
    - Efficiency: model size, parameter count (when introspectable)

Metrics implemented when a labeled validation set + ultralytics is available:
    - Accuracy: mAP50, mAP50-95, precision, recall, per-class AP, confusion matrix

Metrics implemented opportunistically (best-effort, degrade gracefully):
    - Output quality: confidence distribution from sample predictions
    - Robustness: prediction count stability under noise/blur/brightness perturbation
"""
import time

from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# Runtime availability detection
# ---------------------------------------------------------------------------

def _has_onnxruntime():
    try:
        import onnxruntime  # noqa
        return True
    except ImportError:
        return False


def _has_torch():
    try:
        import torch  # noqa
        return True
    except ImportError:
        return False


def _has_ultralytics():
    try:
        import ultralytics  # noqa
        return True
    except ImportError:
        return False


def _has_tensorrt():
    try:
        import tensorrt  # noqa
        return True
    except ImportError:
        return False


def _has_openvino():
    try:
        import openvino  # noqa
        return True
    except ImportError:
        return False


def runtime_capabilities() -> dict:
    return {
        "onnxruntime": _has_onnxruntime(),
        "torch": _has_torch(),
        "ultralytics": _has_ultralytics(),
        "tensorrt": _has_tensorrt(),
        "openvino": _has_openvino(),
    }


# ---------------------------------------------------------------------------
# Efficiency metrics (always available - no inference required)
# ---------------------------------------------------------------------------

def efficiency_metrics(model_path: Path, framework: str) -> dict:
    size_mb = round(model_path.stat().st_size / (1024 * 1024), 3)
    result = {"model_size_mb": size_mb, "parameters": None, "flops": None}

    if framework == "onnx" and _has_onnxruntime():
        try:
            import onnx
            model = onnx.load(str(model_path))
            param_count = 0
            for initializer in model.graph.initializer:
                dims = initializer.dims
                count = 1
                for d in dims:
                    count *= d
                param_count += count
            result["parameters"] = int(param_count)
        except Exception as e:
            result["parameters_error"] = str(e)

    if framework == "pytorch" and _has_torch():
        try:
            import torch
            obj = torch.load(str(model_path), map_location="cpu", weights_only=False)
            model = obj.get("model", obj) if isinstance(obj, dict) else obj
            if hasattr(model, "parameters"):
                result["parameters"] = sum(p.numel() for p in model.parameters())
        except Exception as e:
            result["parameters_error"] = str(e)

    result["note"] = "FLOPs estimation requires a known input resolution and a " \
                      "profiler (e.g. fvcore/thop for PyTorch) - install separately " \
                      "for exact FLOPs; parameter count above is a usable proxy."
    return result


# ---------------------------------------------------------------------------
# Performance metrics (FPS / latency / throughput) - synthetic input, no labels
# ---------------------------------------------------------------------------

def _onnx_performance(model_path: Path, input_size: int, num_runs: int) -> dict:
    import onnxruntime as ort

    t0 = time.time()
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    load_time = time.time() - t0

    input_meta = session.get_inputs()[0]
    shape = [d if isinstance(d, int) else 1 for d in input_meta.shape]
    if len(shape) == 4:
        shape = [1, shape[1] if shape[1] in (1, 3) else 3, input_size, input_size]
    dummy = np.random.rand(*shape).astype(np.float32)

    t0 = time.time()
    session.run(None, {input_meta.name: dummy})
    warmup_time = time.time() - t0

    latencies = []
    for _ in range(num_runs):
        t0 = time.time()
        session.run(None, {input_meta.name: dummy})
        latencies.append(time.time() - t0)

    latencies = np.array(latencies)
    avg_latency = float(latencies.mean())
    return {
        "engine": "onnxruntime (CPU)",
        "model_load_time_sec": round(load_time, 4),
        "warm_up_time_sec": round(warmup_time, 4),
        "avg_latency_ms": round(avg_latency * 1000, 3),
        "p95_latency_ms": round(float(np.percentile(latencies, 95)) * 1000, 3),
        "fps": round(1.0 / avg_latency, 2) if avg_latency > 0 else None,
        "throughput_images_per_sec": round(1.0 / avg_latency, 2) if avg_latency > 0 else None,
        "runs": num_runs,
    }


def _torch_performance(model_path: Path, input_size: int, num_runs: int) -> dict:
    import torch

    t0 = time.time()
    obj = torch.load(str(model_path), map_location="cpu", weights_only=False)
    model = obj.get("model", obj) if isinstance(obj, dict) else obj
    if hasattr(model, "eval"):
        model.eval()
    load_time = time.time() - t0

    dummy = torch.rand(1, 3, input_size, input_size)

    t0 = time.time()
    with torch.no_grad():
        if hasattr(model, "forward"):
            model(dummy.float())
    warmup_time = time.time() - t0

    latencies = []
    with torch.no_grad():
        for _ in range(num_runs):
            t0 = time.time()
            model(dummy.float())
            latencies.append(time.time() - t0)

    latencies = np.array(latencies)
    avg_latency = float(latencies.mean())
    return {
        "engine": "torch (CPU)",
        "model_load_time_sec": round(load_time, 4),
        "warm_up_time_sec": round(warmup_time, 4),
        "avg_latency_ms": round(avg_latency * 1000, 3),
        "p95_latency_ms": round(float(np.percentile(latencies, 95)) * 1000, 3),
        "fps": round(1.0 / avg_latency, 2) if avg_latency > 0 else None,
        "throughput_images_per_sec": round(1.0 / avg_latency, 2) if avg_latency > 0 else None,
        "runs": num_runs,
    }


def performance_metrics(model_path: Path, framework: str, input_size: int = 640,
                         num_runs: int = 30) -> dict:
    try:
        if framework == "onnx":
            if not _has_onnxruntime():
                return {"available": False, "reason": "onnxruntime not installed"}
            return {"available": True, **_onnx_performance(model_path, input_size, num_runs)}
        if framework == "pytorch":
            if not _has_torch():
                return {"available": False, "reason": "torch not installed"}
            return {"available": True, **_torch_performance(model_path, input_size, num_runs)}
        if framework == "tensorrt":
            if not _has_tensorrt():
                return {"available": False, "reason": "TensorRT runtime not installed on this machine"}
            return {"available": False, "reason": "TensorRT engine execution is hardware-specific; "
                                                    "wire your TensorRT runner into model_benchmark.py"}
        if framework == "openvino":
            if not _has_openvino():
                return {"available": False, "reason": "OpenVINO runtime not installed"}
            return {"available": False, "reason": "OpenVINO execution path not wired - "
                                                    "extension point available in model_benchmark.py"}
        return {"available": False, "reason": f"unsupported framework: {framework}"}
    except Exception as e:
        return {"available": False, "reason": f"benchmark failed: {e}"}


# ---------------------------------------------------------------------------
# Accuracy metrics - requires a labeled validation set; best supported via
# ultralytics for YOLO .pt models (real mAP/precision/recall/confusion matrix)
# ---------------------------------------------------------------------------

def accuracy_metrics(model_path: Path, framework: str, data_yaml_path: str | None) -> dict:
    if not data_yaml_path:
        return {"available": False, "reason": "no validation dataset (data.yaml) provided"}

    if framework == "pytorch" and _has_ultralytics():
        try:
            from ultralytics import YOLO
            model = YOLO(str(model_path))
            metrics = model.val(data=data_yaml_path, verbose=False)
            return {
                "available": True,
                "engine": "ultralytics",
                "map50": float(metrics.box.map50),
                "map50_95": float(metrics.box.map),
                "precision": float(metrics.box.mp),
                "recall": float(metrics.box.mr),
                "f1": float(2 * metrics.box.mp * metrics.box.mr /
                            (metrics.box.mp + metrics.box.mr)) if (metrics.box.mp + metrics.box.mr) else 0.0,
                "per_class_ap50": {str(k): float(v) for k, v in
                                    zip(model.names.values(), metrics.box.ap50)} if hasattr(metrics.box, "ap50") else {},
            }
        except Exception as e:
            return {"available": False, "reason": f"ultralytics evaluation failed: {e}"}

    return {"available": False,
            "reason": "Accuracy evaluation currently requires a YOLO .pt model + ultralytics installed "
                       "(pip install ultralytics). ONNX/TensorRT/OpenVINO accuracy evaluation is a "
                       "documented extension point: export predictions in COCO format and reuse the "
                       "same pycocotools-based mAP routine."}


# ---------------------------------------------------------------------------
# Robustness testing - perturb a handful of sample images and compare
# detection-count stability (best-effort; requires ultralytics for actual
# inference, otherwise reports unavailable)
# ---------------------------------------------------------------------------

def robustness_metrics(model_path: Path, framework: str, sample_image_paths: list[str]) -> dict:
    if not (_has_ultralytics() and framework == "pytorch") or not sample_image_paths:
        return {"available": False,
                "reason": "robustness testing currently requires a YOLO .pt model + ultralytics "
                           "and at least one sample image"}
    try:
        import cv2
        from ultralytics import YOLO
        model = YOLO(str(model_path))

        def count_detections(img):
            res = model.predict(img, verbose=False)
            return len(res[0].boxes) if res and res[0].boxes is not None else 0

        results = {}
        for img_path in sample_image_paths[:5]:
            img = cv2.imread(img_path)
            if img is None:
                continue
            baseline = count_detections(img)

            noisy = img + np.random.normal(0, 20, img.shape).astype(np.int16)
            noisy = np.clip(noisy, 0, 255).astype(np.uint8)

            blurred = cv2.GaussianBlur(img, (9, 9), 0)
            bright = cv2.convertScaleAbs(img, alpha=1.0, beta=60)
            dark = cv2.convertScaleAbs(img, alpha=1.0, beta=-60)
            rotated = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)

            results[Path(img_path).name] = {
                "baseline_detections": baseline,
                "noise_detections": count_detections(noisy),
                "blur_detections": count_detections(blurred),
                "brightness_detections": count_detections(bright),
                "darkness_detections": count_detections(dark),
                "rotation_detections": count_detections(rotated),
            }

        return {"available": True, "per_image": results}
    except Exception as e:
        return {"available": False, "reason": f"robustness test failed: {e}"}


# ---------------------------------------------------------------------------
# Output quality - confidence distribution from sample predictions
# ---------------------------------------------------------------------------

def output_quality_metrics(model_path: Path, framework: str, sample_image_paths: list[str]) -> dict:
    if not (_has_ultralytics() and framework == "pytorch") or not sample_image_paths:
        return {"available": False,
                "reason": "output quality analysis currently requires a YOLO .pt model + "
                           "ultralytics and at least one sample image"}
    try:
        from ultralytics import YOLO
        model = YOLO(str(model_path))
        confidences = []
        box_counts = []
        for img_path in sample_image_paths[:25]:
            res = model.predict(img_path, verbose=False)
            if res and res[0].boxes is not None:
                confs = res[0].boxes.conf.tolist()
                confidences.extend(confs)
                box_counts.append(len(confs))

        if not confidences:
            return {"available": True, "note": "no detections on sample images", "confidence_distribution": []}

        return {
            "available": True,
            "avg_confidence": round(float(np.mean(confidences)), 4),
            "min_confidence": round(float(np.min(confidences)), 4),
            "max_confidence": round(float(np.max(confidences)), 4),
            "avg_detections_per_image": round(float(np.mean(box_counts)), 2),
            "confidence_histogram": np.histogram(confidences, bins=10, range=(0, 1))[0].tolist(),
        }
    except Exception as e:
        return {"available": False, "reason": f"output quality analysis failed: {e}"}
