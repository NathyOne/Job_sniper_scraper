import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


def _parse_bool(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_items(tsv_path, max_items):
    items = []
    total = 0
    truncated = False
    with open(tsv_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            total += 1
            if len(items) < max_items:
                items.append(row)
            else:
                truncated = True
    return items, total, truncated


def send_webhook_if_configured(tsv_path):
    url = os.getenv("WEBHOOK_URL")
    if not url:
        return

    path = Path(tsv_path)
    if not path.exists():
        raise FileNotFoundError(f"Results file not found: {path}")

    mode = os.getenv("WEBHOOK_MODE", "json").strip().lower()
    timeout_seconds = int(os.getenv("WEBHOOK_TIMEOUT", "30"))
    send_empty = _parse_bool(os.getenv("WEBHOOK_SEND_EMPTY"), default=False)
    max_items = int(os.getenv("WEBHOOK_MAX_ITEMS", "200"))

    headers = {}
    bearer = os.getenv("WEBHOOK_BEARER_TOKEN")
    auth_header = os.getenv("WEBHOOK_AUTH_HEADER")
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    elif auth_header:
        headers["Authorization"] = auth_header

    if mode == "tsv":
        body = path.read_bytes()
        if not body and not send_empty:
            return
        headers["Content-Type"] = "text/tab-separated-values; charset=utf-8"
    else:
        items, total, truncated = _load_items(path, max_items)
        if total == 0 and not send_empty:
            return
        payload = {
            "source": "lead_generator",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "item_count": total,
            "items_truncated": truncated,
            "items": items,
        }
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    request = Request(url, data=body, headers=headers, method="POST")
    with urlopen(request, timeout=timeout_seconds) as response:
        if response.status >= 400:
            raise RuntimeError(f"Webhook failed with HTTP {response.status}")
