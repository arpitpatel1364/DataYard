# Cactus Intelligence Suite (CIS)

Cactus Intelligence Suite (CIS) is a comprehensive platform for Dataset Intelligence, Validation, Registry, Monitoring, Comparison, and Model Analytics. It is designed specifically for Cactus Creatives to streamline and enhance the machine learning lifecycle.

The platform is engineered for simplicity and self-containment. It runs on SQLite and utilizes an in-process scheduler, eliminating the need for external dependencies like PostgreSQL, Redis, or Celery. The architecture consists of a single Python process serving both the backend API and a vanilla HTML/CSS/JS frontend.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
  - [Local Installation](#local-installation)
  - [Docker Installation](#docker-installation)
- [Testing](#testing)
- [Pluggable Extensions](#pluggable-extensions)
- [Health Scoring Weights](#health-scoring-weights)

## Features

- **Authentication & Authorization**: Role-Based Access Control (Admin/User), JWT access and refresh tokens, email verification, and password resets.
- **Dataset Auto-Detection**: Point CIS at a `data.yaml` file or a dataset folder, and it automatically resolves train/val/test paths, classes, and counts without manual entry.
- **Import Wizard**: Supports local dataset imports and Roboflow integration (downloads YOLO exports via the Roboflow REST API).
- **Class Intelligence**: Analyzes class distribution, quality flags, diversity heuristics, training readiness, and provides recommendations per selected class.
- **Dataset Health Engine**: Performs structural and integrity checks, annotation validation (YOLO, COCO, VOC), image quality analysis (blur, brightness, contrast, noise via OpenCV), duplicate detection (SHA256 exact and pHash near-duplicate), and train/val/test leakage detection. Computes a weighted Health Score and Grade.
- **Dataset Comparison Engine**: Normalizes and compares datasets across different sources (Local vs. Local, Local vs. Roboflow, Roboflow vs. Roboflow).
- **Versioning & Registry**: Automatically creates a new `DatasetVersion` upon every scan, maintaining a searchable registry and timeline of health scores.
- **Reporting**: Generates and exports reports in PDF (ReportLab), Excel (openpyxl), CSV, and JSON formats.
- **Monitoring**: Background jobs via APScheduler automatically re-scan monitored datasets on defined intervals.
- **Model Testing Lab**: Benchmark `.pt` and `.onnx` models for performance (FPS, latency, throughput) and efficiency (size, parameters). Evaluates accuracy (mAP50, mAP50-95, precision, recall) and robustness against noise/blur/brightness/rotation.
- **AI Recommendation Engine**: Fully offline, rule-based recommendation system requiring no external or paid APIs.

## Architecture

The project is structured into a backend FastAPI server and a frontend client:

```text
cis/
├── backend/
│   ├── app/
│   │   ├── main.py            (FastAPI app, mounts API and serves frontend)
│   │   ├── config.py          (Settings, SQLite path, JWT secrets)
│   │   ├── database.py        (SQLAlchemy engine and session)
│   │   ├── models/            (Database models: users, datasets, versions, etc.)
│   │   ├── schemas/           (Pydantic request/response models)
│   │   ├── core/              (Security, JWT/bcrypt, RBAC)
│   │   ├── api/               (Routers: auth, datasets, compare, reports, models)
│   │   └── services/          (Business logic: parsers, engines, detectors)
│   └── tests/                 (Pytest suite)
└── frontend/
    ├── *.html                 (Views)
    ├── css/theme.css          (Design tokens, glassmorphism, bento grid)
    └── js/                    (API clients and page-specific scripts)
```

## Installation

### Local Installation

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env to set SECRET_KEY and REFRESH_SECRET_KEY
   ```

5. Start the application:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

The application will be available at `http://localhost:8000`. The first registered user will automatically be assigned Admin privileges.

To enable the Model Testing Lab's advanced benchmarks, install the optional dependencies:
```bash
pip install -r requirements-optional.txt
```

### Docker Installation

To run the application using Docker, execute:

```bash
docker compose up --build
```

The application runs entirely within a single container. To access local datasets, ensure your dataset directories are mounted as volumes in the `docker-compose.yml` file.

## Testing

To run the test suite locally:

```bash
cd backend
source venv/bin/activate
pip install pytest httpx
pytest tests/ -v
```

## Pluggable Extensions

Certain features require specific hardware (e.g., GPUs) or proprietary runtimes. If these are unavailable, the platform gracefully reports them as unsupported. These components are designed as pluggable extensions:

- **TensorRT / OpenVINO Execution**: Detected dynamically by `app/services/model_benchmark.py`.
- **Semantic Duplicate Detection (CLIP)**: Requires `torch` and `open_clip` to enable `compute_semantic_duplicates()`. Standard SHA256 and pHash detection work out-of-the-box.
- **Exact FLOPs**: Requires a fixed input resolution and a profiler (`fvcore`/`thop`). Parameter count is currently provided as a proxy.
- **ONNX/TensorRT/OpenVINO Accuracy (mAP)**: Accuracy evaluation currently supports YOLO `.pt` models via `ultralytics`. Extension to other formats is straightforward using the existing validation logic.

## Health Scoring Weights

Dataset health scores are calculated using the following weighted distribution:

- **Integrity**: 25%
- **Annotation Quality**: 25%
- **Balance**: 15%
- **Image Quality**: 15%
- **Diversity**: 10%
- **Leakage**: 10%

**Grading Scale:**
- A+ : 96-100
- A  : 90-95
- B  : 80-89
- C  : 70-79
- D  : 60-69
- F  : 0-59

## API Reference

Interactive API documentation is automatically generated by FastAPI. Once the server is running, navigate to:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
