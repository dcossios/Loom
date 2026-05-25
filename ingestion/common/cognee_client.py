"""Thin HTTP client for the cognee API used by the ingestion-cron sidecar.

Single-writer model: the sidecar never touches the databases directly. It only
uploads files to POST /api/v1/add and triggers POST /api/v1/cognify, so the main
cognee service stays the sole writer of SQLite/LanceDB/FalkorDB.
"""

import json
import os
import tempfile
from pathlib import Path

import requests

COGNEE_API_URL = os.getenv("COGNEE_API_URL", "http://cognee:8000").rstrip("/")
HTTP_TIMEOUT = int(os.getenv("COGNEE_HTTP_TIMEOUT", "1800"))
ADD_BATCH_SIZE = int(os.getenv("COGNEE_ADD_BATCH_SIZE", "50"))


def health() -> bool:
    try:
        resp = requests.get(f"{COGNEE_API_URL}/health", timeout=30)
        return resp.ok
    except requests.RequestException:
        return False


def upload_files(items, dataset_name, batch_size=ADD_BATCH_SIZE) -> int:
    """Upload local files to /api/v1/add in batches.

    items: iterable of (local_path, upload_name) tuples. upload_name is the
    filename cognee sees — encode the relative path into it to keep names unique.
    """
    items = list(items)
    uploaded = 0
    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        _post_add(batch, dataset_name)
        uploaded += len(batch)
    return uploaded


def _post_add(batch, dataset_name):
    handles = []
    files = []
    try:
        for local_path, upload_name in batch:
            handle = open(local_path, "rb")
            handles.append(handle)
            files.append(("data", (upload_name, handle, "application/octet-stream")))
        resp = requests.post(
            f"{COGNEE_API_URL}/api/v1/add",
            files=files,
            data={"datasetName": dataset_name},
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    finally:
        for handle in handles:
            handle.close()


def cognify(dataset_name):
    resp = requests.post(
        f"{COGNEE_API_URL}/api/v1/cognify",
        json={"datasets": [dataset_name], "run_in_background": False},
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def push_json_records(records, dataset_name, source_name):
    """Helper for SaaS sources: dump records to a JSON file, upload, cognify."""
    tmpdir = tempfile.mkdtemp(prefix=f"{source_name}_")
    out = Path(tmpdir) / f"{source_name}.json"
    out.write_text(json.dumps(records, indent=2, default=str))
    upload_files([(str(out), f"{source_name}.json")], dataset_name)
    cognify(dataset_name)
