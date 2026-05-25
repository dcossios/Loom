"""Ingest a source-code repository into cognee as the agent's factual memory.

Walks REPO_PATH, uploads source/text files to /api/v1/add, then cognifies.
Files load via cognee's TextLoader; cognify extracts entities/relationships.
"""

import os
import sys
from pathlib import Path

from common.cognee_client import cognify, health, upload_files

REPO_PATH = os.getenv("REPO_PATH", "/repos/flowly")
DATASET = os.getenv("CODE_DATASET_NAME", "flowly_code")
MAX_BYTES = int(os.getenv("CODE_MAX_FILE_BYTES", "1000000"))

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".next", ".nuxt", ".idea", ".vscode", ".mypy_cache", ".pytest_cache",
    "target", ".cache", "coverage", ".turbo", "vendor",
}
ALLOWED_EXT = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".rb", ".php",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".kt", ".swift", ".scala", ".m",
    ".sh", ".bash", ".sql", ".md", ".rst", ".txt", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".json", ".html", ".css", ".scss", ".vue", ".svelte", ".graphql",
}


def collect():
    root = Path(REPO_PATH)
    if not root.exists():
        print(f"[codebase] REPO_PATH '{REPO_PATH}' not found; skipping.")
        return []
    items = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in ALLOWED_EXT:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size == 0 or size > MAX_BYTES:
            continue
        rel = path.relative_to(root).as_posix()
        items.append((str(path), rel.replace("/", "__")))
    return items


def main():
    if not health():
        print("[codebase] cognee API not healthy; aborting.")
        sys.exit(1)
    items = collect()
    if not items:
        print("[codebase] nothing to ingest.")
        return
    print(f"[codebase] uploading {len(items)} files to dataset '{DATASET}'...")
    upload_files(items, DATASET)
    print("[codebase] running cognify (this calls the LLM and may take a while)...")
    cognify(DATASET)
    print("[codebase] done.")


if __name__ == "__main__":
    main()
