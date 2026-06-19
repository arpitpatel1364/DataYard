"""
ROBOFLOW IMPORT CLIENT

Talks to the Roboflow REST API to fetch project metadata and download a
dataset export (YOLO format) into local managed storage, where it is then
registered exactly like any other local dataset. This is the one optional
external integration allowed by the FREE OPERATION REQUIREMENT - everything
else in CIS runs fully offline.
"""
import zipfile
import requests
from pathlib import Path

ROBOFLOW_API_BASE = "https://api.roboflow.com"


class RoboflowError(Exception):
    pass


def fetch_project_metadata(api_key: str, workspace: str, project: str) -> dict:
    url = f"{ROBOFLOW_API_BASE}/{workspace}/{project}?api_key={api_key}"
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        raise RoboflowError(f"Roboflow metadata request failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def download_dataset(api_key: str, workspace: str, project: str, version: str,
                      dest_dir: Path, fmt: str = "yolov8") -> Path:
    """
    Downloads a dataset export from Roboflow as a zip and extracts it into
    dest_dir. Returns the extracted dataset folder path.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    export_url = (f"{ROBOFLOW_API_BASE}/{workspace}/{project}/{version}/{fmt}"
                  f"?api_key={api_key}")

    meta_resp = requests.get(export_url, timeout=60)
    if meta_resp.status_code != 200:
        raise RoboflowError(f"Roboflow export request failed ({meta_resp.status_code}): "
                             f"{meta_resp.text[:300]}")

    meta = meta_resp.json()
    link = meta.get("export", {}).get("link")
    if not link:
        raise RoboflowError("Roboflow response did not include a download link - "
                             "check workspace/project/version/api_key.")

    zip_path = dest_dir / "roboflow_export.zip"
    with requests.get(link, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(dest_dir)
    zip_path.unlink(missing_ok=True)

    return dest_dir
