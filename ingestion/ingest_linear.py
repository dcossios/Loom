"""Ingest Linear issues (with comments) into cognee.

Set LINEAR_API_KEY (Settings -> Security & access -> Personal API keys).
Pulls issues via the Linear GraphQL API, then runs pull -> JSON -> upload -> cognify.
"""

import os
import sys

import requests

from common.cognee_client import health, push_json_records

API_KEY = os.getenv("LINEAR_API_KEY")
DATASET = os.getenv("LINEAR_DATASET_NAME", "flowly_linear")
MAX_PAGES = int(os.getenv("LINEAR_MAX_PAGES", "20"))
ENDPOINT = "https://api.linear.app/graphql"

QUERY = """
query Issues($after: String) {
  issues(first: 100, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      identifier
      title
      description
      priority
      url
      createdAt
      updatedAt
      state { name type }
      assignee { name email }
      team { name key }
      labels { nodes { name } }
      comments { nodes { body createdAt user { name } } }
    }
  }
}
"""


def fetch_records():
    headers = {"Authorization": API_KEY, "Content-Type": "application/json"}
    records = []
    after = None
    for _ in range(MAX_PAGES):
        resp = requests.post(
            ENDPOINT, json={"query": QUERY, "variables": {"after": after}}, headers=headers, timeout=60
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("errors"):
            raise RuntimeError(f"Linear API errors: {payload['errors']}")
        block = payload["data"]["issues"]
        for node in block["nodes"]:
            node["labels"] = [label["name"] for label in node.get("labels", {}).get("nodes", [])]
            node["comments"] = node.get("comments", {}).get("nodes", [])
            records.append(node)
        if not block["pageInfo"]["hasNextPage"]:
            break
        after = block["pageInfo"]["endCursor"]
    return records


def main():
    if not API_KEY:
        print("[linear] LINEAR_API_KEY not set; skipping.")
        return
    if not health():
        print("[linear] cognee API not healthy; aborting.")
        sys.exit(1)
    try:
        records = fetch_records()
    except (requests.RequestException, RuntimeError) as error:
        print(f"[linear] API request failed: {error}")
        return
    if not records:
        print("[linear] no issues returned.")
        return
    print(f"[linear] pushing {len(records)} issues to dataset '{DATASET}'...")
    push_json_records(records, DATASET, "linear")
    print("[linear] done.")


if __name__ == "__main__":
    main()
