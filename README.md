# Cactus Intelligence Suite (CIS)

Dataset Intelligence, Validation, Registry, Monitoring, Comparison & Model
Analytics platform, built for **Cactus Creatives**.

This build runs on **SQLite** (no PostgreSQL) and an **in-process scheduler**
(no Redis/Celery) — everything is a single Python process plus a vanilla
HTML/CSS/JS frontend served by that same process.

---

## 1. What's actually in this build

Real, working, tested code for:

- **Auth**: JWT access + refresh tokens, RBAC (admin/user), email
  verification + password reset (tokens are logged server-side instead of
  emailed — see `app/api/auth.py::send_email` to wire a real mail provider).
- **data.yaml auto-detection**: point CIS at a `data.yaml` file or a dataset
  folder and it resolves train/val/test paths, classes, and counts with no
  manual path entry (`app/services/yaml_parser.py`).
- **Import wizard**: local datasets + Roboflow import (downloads a YOLO
  export via the Roboflow REST API and registers it like any local dataset).
- **Class selection workflow + Class Intelligence**: distribution, quality
  flags, diversity heuristics, training readiness, and recommendations per
  selected class (`app/services/class_intelligence.py`).
- **Dataset Health Engine**: structure, integrity (corruption checks),
  annotation validation (YOLO fully, COCO/VOC supported), image quality
  (blur/brightness/contrast/noise via OpenCV), duplicate detection
  (SHA256 exact + pHash near-duplicate), train/val/test leakage detection,
  and a weighted Health Score + Grade exactly per the spec's weights.
- **Dataset Comparison Engine**: Local vs Local / Local vs Roboflow /
  Roboflow vs Roboflow — all normalized into the same model, so one code
  path handles every combination.
- **Versioning + Registry**: every scan creates a new `DatasetVersion`,
  so health-score timelines and a searchable registry (Grid.js) come for
  free.
- **Reporting**: PDF (ReportLab), Excel (openpyxl), CSV, JSON exports.
- **Monitoring**: APScheduler background jobs re-scan monitored datasets on
  an interval and append new versions automatically — this is the
  Celery-replacement.
- **Model Testing Lab**: upload `.pt`/`.onnx` models; real performance
  benchmarking (FPS/latency/throughput/warm-up/load time) via
  onnxruntime/torch; real efficiency metrics (size, parameter count); real
  accuracy metrics (mAP50/mAP50-95/precision/recall/per-class AP) via
  `ultralytics` for YOLO `.pt` models against a labeled validation set;
  output-quality (confidence distribution) and robustness (noise/blur/
  brightness/rotation detection-count stability) for the same.
- **Admin panel**: users, audit logs, system health/storage, active jobs.
- **AI Recommendation Engine**: fully offline, rule-based — no OpenAI or
  any paid API required anywhere in the platform.

## 2. What's intentionally a pluggable extension point, not faked

A few items in the original spec need GPU hardware or proprietary runtimes
that don't exist in a generic server/sandbox. Rather than fabricate numbers,
these report `"available": false` with a clear reason, and the code is
structured so wiring in the real thing is a drop-in addition:

- **TensorRT / OpenVINO execution** — `app/services/model_benchmark.py`
  detects whether `tensorrt`/`openvino` are importable on the host and has
  the call sites ready; the actual engine-build/inference calls are
  hardware-specific and left as an extension point.
- **CLIP-embedding semantic duplicate detection** — `duplicate_detector.py`
  exposes `compute_semantic_duplicates()`; install `torch` + `open_clip` (or
  `clip`) on the server to enable it. SHA256 exact and pHash near-duplicate
  detection work today without any extra install.
- **Exact FLOPs** — parameter count is computed for real; FLOPs needs a
  fixed input resolution + a profiler (`fvcore`/`thop`); the parameter count
  is reported as a usable proxy today.
- **ONNX/TensorRT/OpenVINO accuracy (mAP)** — works today for YOLO `.pt`
  models via `ultralytics`. Extending it to ONNX/TensorRT/OpenVINO is a
  matter of running the same model on the same validation set and reusing
  the per-class AP routine (pycocotools-based mAP).

## 3. Installation

### Local (no Docker)

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # edit SECRET_KEY/REFRESH_SECRET_KEY
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` — the frontend is served by the same process.
The first account you register automatically becomes Admin.

To unlock the Model Testing Lab's heavier benchmarks:

```bash
pip install -r requirements-optional.txt   # onnxruntime, torch, ultralytics
```

### Docker

```bash
docker compose up --build
```

No Postgres/Redis services are defined — just the one container. Mount your
real dataset directories into the container if they're not already on the
same machine (see the commented volume line in `docker-compose.yml`).

## 4. Running tests

```bash
cd backend
source venv/bin/activate
pip install pytest httpx
pytest tests/ -v
```

## 5. Architecture

```
cis/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app, mounts API + serves frontend
│   │   ├── config.py          Settings (SQLite path, JWT secrets, storage dirs)
│   │   ├── database.py        SQLAlchemy engine/session (SQLite)
│   │   ├── models/            users, datasets, versions, model_tests, audit_logs...
│   │   ├── schemas/           Pydantic request/response models
│   │   ├── core/               security.py (JWT/bcrypt), rbac.py (admin/user deps)
│   │   ├── api/                auth, datasets, compare, reports, models, admin routers
│   │   └── services/           yaml_parser, health_engine, class_intelligence,
│   │                           duplicate_detector, leakage_detector, quality_analyzer,
│   │                           annotation_validator, comparison_engine, roboflow_client,
│   │                           report_generator, model_benchmark, scheduler, monitoring_job
│   └── tests/
└── frontend/
    ├── *.html                  one page per sidebar destination
    ├── css/theme.css            CIS design tokens (#72ab52, glassmorphism, bento grid)
    └── js/                      api.js (fetch+JWT client), shell.js (sidebar/topbar),
                                 one script per page
```

## 6. API reference

Full interactive API docs are auto-generated by FastAPI at `/docs` (Swagger)
and `/redoc` once the server is running — every endpoint, request/response
schema, and auth requirement is there and stays in sync with the code
automatically.

## 7. Health Scoring weights (as specified)

```
Integrity             25%
Annotation Quality    25%
Balance               15%
Image Quality          15%
Diversity              10%
Leakage                10%

96-100  A+      90-95  A      80-89  B      70-79  C      60-69  D      0-59  F
```
