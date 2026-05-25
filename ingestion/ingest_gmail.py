"""STUB: ingest Gmail messages into cognee.

Wire up fetch_records() against the Gmail API, then this runs the same
pull -> JSON -> upload -> cognify flow as the functional sources.
"""

import os
import sys

from common.cognee_client import health, push_json_records

CREDENTIALS_PATH = os.getenv("GMAIL_CREDENTIALS_PATH")
GMAIL_QUERY = os.getenv("GMAIL_QUERY", "newer_than:7d")
DATASET = os.getenv("GMAIL_DATASET_NAME", "flowly_gmail")


def fetch_records():
    # TODO: use google-api-python-client with the OAuth/service-account creds at
    #   CREDENTIALS_PATH. List messages matching GMAIL_QUERY, then fetch each and
    #   return a list of plain dicts (from, to, subject, date, snippet, body).
    raise NotImplementedError


def main():
    if not CREDENTIALS_PATH:
        print("[gmail] GMAIL_CREDENTIALS_PATH not set; skipping.")
        return
    if not health():
        print("[gmail] cognee API not healthy; aborting.")
        sys.exit(1)
    try:
        records = fetch_records()
    except NotImplementedError:
        print("[gmail] fetch_records() is a stub — implement the Gmail API call.")
        return
    if not records:
        print("[gmail] no records returned.")
        return
    print(f"[gmail] pushing {len(records)} records to dataset '{DATASET}'...")
    push_json_records(records, DATASET, "gmail")
    print("[gmail] done.")


if __name__ == "__main__":
    main()
