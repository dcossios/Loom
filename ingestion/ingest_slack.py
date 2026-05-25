"""Ingest Slack messages into cognee.

Create a Slack app, add bot scopes (channels:history, channels:read,
groups:history, users:read), install it, and invite the bot to the channels.
Set SLACK_BOT_TOKEN (xoxb-...) and SLACK_CHANNELS (names or IDs, comma-separated).
Pulls message history, then runs pull -> JSON -> upload -> cognify.
"""

import os
import sys
import time

import requests

from common.cognee_client import health, push_json_records

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
CHANNELS = [c.strip().lstrip("#") for c in os.getenv("SLACK_CHANNELS", "").split(",") if c.strip()]
DATASET = os.getenv("SLACK_DATASET_NAME", "flowly_slack")
HISTORY_LIMIT = int(os.getenv("SLACK_HISTORY_LIMIT", "200"))
MAX_PAGES = int(os.getenv("SLACK_MAX_PAGES", "5"))
INCLUDE_THREADS = os.getenv("SLACK_INCLUDE_THREADS", "true").lower() == "true"
BASE = "https://slack.com/api"


def _call(method, params):
    headers = {"Authorization": f"Bearer {BOT_TOKEN}"}
    for _ in range(5):
        resp = requests.get(f"{BASE}/{method}", headers=headers, params=params, timeout=60)
        if resp.status_code == 429:
            time.sleep(int(resp.headers.get("Retry-After", "5")))
            continue
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack {method} error: {data.get('error')}")
        return data
    raise RuntimeError(f"Slack {method}: rate-limited repeatedly")


def _paginate(method, params, key):
    items = []
    cursor = None
    for _ in range(MAX_PAGES):
        page_params = dict(params)
        if cursor:
            page_params["cursor"] = cursor
        data = _call(method, page_params)
        items.extend(data.get(key, []))
        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return items


def _channel_map():
    chans = _paginate(
        "conversations.list",
        {"types": "public_channel,private_channel", "limit": 1000},
        "channels",
    )
    return {c["name"]: c["id"] for c in chans}, {c["id"]: c["name"] for c in chans}


def _user_map():
    users = _paginate("users.list", {"limit": 1000}, "members")
    return {u["id"]: (u.get("real_name") or u.get("name")) for u in users}


def fetch_records():
    name_to_id, id_to_name = _channel_map()
    users = _user_map()
    records = []
    for ref in CHANNELS:
        channel_id = ref if ref in id_to_name else name_to_id.get(ref)
        if not channel_id:
            print(f"[slack] channel '{ref}' not found or bot not a member; skipping.")
            continue
        channel_name = id_to_name.get(channel_id, ref)
        messages = _paginate(
            "conversations.history", {"channel": channel_id, "limit": HISTORY_LIMIT}, "messages"
        )
        for msg in messages:
            if msg.get("type") != "message" or msg.get("subtype"):
                continue
            records.append(_to_record(msg, channel_name, users))
            if INCLUDE_THREADS and int(msg.get("reply_count", 0)) > 0:
                replies = _call(
                    "conversations.replies", {"channel": channel_id, "ts": msg["ts"], "limit": 200}
                ).get("messages", [])
                for reply in replies[1:]:
                    records.append(_to_record(reply, channel_name, users))
    return records


def _to_record(msg, channel_name, users):
    return {
        "channel": channel_name,
        "user": users.get(msg.get("user"), msg.get("user")),
        "text": msg.get("text", ""),
        "ts": msg.get("ts"),
        "thread_ts": msg.get("thread_ts"),
    }


def main():
    if not BOT_TOKEN:
        print("[slack] SLACK_BOT_TOKEN not set; skipping.")
        return
    if not CHANNELS:
        print("[slack] SLACK_CHANNELS not set; skipping.")
        return
    if not health():
        print("[slack] cognee API not healthy; aborting.")
        sys.exit(1)
    try:
        records = fetch_records()
    except (requests.RequestException, RuntimeError) as error:
        print(f"[slack] API request failed: {error}")
        return
    if not records:
        print("[slack] no messages returned.")
        return
    print(f"[slack] pushing {len(records)} messages to dataset '{DATASET}'...")
    push_json_records(records, DATASET, "slack")
    print("[slack] done.")


if __name__ == "__main__":
    main()
