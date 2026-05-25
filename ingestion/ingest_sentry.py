"""Ingest Sentry issues into cognee.

Set SENTRY_AUTH_TOKEN (Settings -> Auth Tokens, scopes project:read event:read),
SENTRY_ORG and SENTRY_PROJECT (their slugs). For self-hosted Sentry, set
SENTRY_BASE_URL. Pulls issues, then runs pull -> JSON -> upload -> cognify.
"""

import os
import sys

import requests

from common.cognee_client import health, push_json_records

AUTH_TOKEN = os.getenv("SENTRY_AUTH_TOKEN")
ORG = os.getenv("SENTRY_ORG")
PROJECT = os.getenv("SENTRY_PROJECT")
DATASET = os.getenv("SENTRY_DATASET_NAME", "flowly_sentry")
BASE_URL = os.getenv("SENTRY_BASE_URL", "https://sentry.io").rstrip("/")
QUERY = os.getenv("SENTRY_QUERY", "is:unresolved")
STATS_PERIOD = os.getenv("SENTRY_STATS_PERIOD", "14d")
MAX_PAGES = int(os.getenv("SENTRY_MAX_PAGES", "10"))

FIELDS = (
    "shortId", "title", "culprit", "level", "status", "count", "userCount",
    "firstSeen", "lastSeen", "permalink",
)


def fetch_records():
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    url = f"{BASE_URL}/api/0/projects/{ORG}/{PROJECT}/issues/"
    params = {"query": QUERY, "statsPeriod": STATS_PERIOD, "limit": 100}
    records = []
    for _ in range(MAX_PAGES):
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        for issue in resp.json():
            records.append({k: issue.get(k) for k in FIELDS})
        # Sentry paginates via a cursor in the Link header.
        link = resp.links.get("next", {})
        if link.get("results") != "true" or not link.get("cursor"):
            break
        params = {"cursor": link["cursor"]}
        url = link["url"]
    return records


def main():
    if not (AUTH_TOKEN and ORG and PROJECT):
        print("[sentry] SENTRY_AUTH_TOKEN/SENTRY_ORG/SENTRY_PROJECT not set; skipping.")
        return
    if not health():
        print("[sentry] cognee API not healthy; aborting.")
        sys.exit(1)
    try:
        records = fetch_records()
    except (requests.RequestException, RuntimeError) as error:
        print(f"[sentry] API request failed: {error}")
        return
    if not records:
        print("[sentry] no issues returned.")
        return
    print(f"[sentry] pushing {len(records)} issues to dataset '{DATASET}'...")
    push_json_records(records, DATASET, "sentry")
    print("[sentry] done.")


if __name__ == "__main__":
    main()
