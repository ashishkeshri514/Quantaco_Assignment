#!/usr/bin/env python3
"""
POS transaction simulator.

Why a simulator that POSTs to the ingest API (vs seeding the DB directly):
- Exercises the same write path a real venue POS would use
- Proves auth, validation, and SSE fan-out end-to-end
- Easy to demonstrate "live" updates while the dashboard is open

Usage (from repo root, with backend running):
  source .venv/bin/activate
  python scripts/simulate_transactions.py --token <TOKEN>
"""

from __future__ import annotations

import argparse
import random
import time
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone

import requests

MENU = [
    ("ITM-01", "Schwartz Pale Ale", 9.5),
    ("ITM-02", "House Red Wine", 12.0),
    ("ITM-03", "Chicken Parma", 28.0),
    ("ITM-04", "Fish & Chips", 26.0),
    ("ITM-05", "Cheeseburger", 22.0),
    ("ITM-06", "Caesar Salad", 18.0),
    ("ITM-07", "Espresso Martini", 18.0),
    ("ITM-08", "Garlic Bread", 10.0),
    ("ITM-09", "Sticky Date Pudding", 14.0),
    ("ITM-10", "Sparkling Water", 5.0),
]

VENUE_CODES = [f"VEN-{i:02d}" for i in range(1, 41)]


def post_json(url: str, payload: dict, token: str, session: requests.Session | None = None) -> tuple[int, str]:
    client = session or requests
    resp = client.post(
        url,
        json=payload,
        headers={"Authorization": f"Token {token}"},
        timeout=10,
    )
    return resp.status_code, resp.text


def build_txn(
    venue: str,
    txn_type: str,
    when: datetime | None = None,
) -> dict:
    when = when or datetime.now(dt_timezone.utc)
    items = []
    for _ in range(random.randint(1, 4)):
        item_id, name, price = random.choice(MENU)
        qty = random.randint(1, 3)
        items.append(
            {
                "item_id": item_id,
                "name": name,
                "qty": qty,
                "price": price,
            }
        )
    total = round(sum(i["qty"] * i["price"] for i in items), 2)
    if txn_type in ("void", "refund"):
        total = -abs(total) if txn_type == "refund" else abs(total)

    return {
        "venue_id": venue,
        "transaction_id": f"TXN-{uuid.uuid4().hex[:12]}",
        "timestamp": when.isoformat().replace("+00:00", "Z"),
        "type": txn_type,
        "items": items,
        "total": abs(total),
        "staff_id": f"STAFF-{random.randint(1, 20):02d}",
    }


def backfill(url: str, token: str, hours: int = 2, baseline_days: int = 2) -> None:
    """Seed recent history + light prior-day samples for daypart baselines."""
    now = datetime.now(dt_timezone.utc)
    count = 0
    session = requests.Session()
    session.headers.update({"Authorization": f"Token {token}"})

    print(f"Backfilling baselines ({baseline_days}d) + last {hours}h…")

    for day in range(1, baseline_days + 1):
        for hour_ago in range(hours, 0, -1):
            window_start = now - timedelta(days=day, hours=hour_ago)
            for venue in VENUE_CODES:
                for _ in range(2):  # light sample — enough for MIN_BASELINE_SAMPLES
                    offset = timedelta(minutes=random.randint(0, 55))
                    payload = build_txn(venue, "sale", window_start + offset)
                    status, body = post_json(url, payload, token, session=session)
                    if status >= 400:
                        print(f"baseline error {status}: {body}")
                    else:
                        count += 1
        print(f"  …day -{day} done ({count} txns)")

    for hour_ago in range(hours, 0, -1):
        window_start = now - timedelta(hours=hour_ago)
        for venue in VENUE_CODES:
            quiet = venue in {"VEN-07", "VEN-13", "VEN-22"} and hour_ago == 1
            n = random.randint(1, 2) if quiet else random.randint(2, 5)
            for _ in range(n):
                offset = timedelta(minutes=random.randint(0, 55), seconds=random.randint(0, 59))
                txn_type = random.choices(
                    ["sale", "void", "refund"],
                    weights=[0.9, 0.05, 0.05]
                    if venue not in {"VEN-03", "VEN-18"}
                    else [0.7, 0.15, 0.15],
                )[0]
                payload = build_txn(venue, txn_type, window_start + offset)
                status, body = post_json(url, payload, token, session=session)
                if status >= 400:
                    print(f"backfill error {status}: {body}")
                else:
                    count += 1
        print(f"  …hour -{hour_ago} done ({count} txns)")

    print(f"Backfill complete: {count} transactions")


def stream(url: str, token: str, interval: float, spike_venue: str | None) -> None:
    print(f"Streaming to {url} every ~{interval}s (Ctrl+C to stop)")
    session = requests.Session()
    while True:
        venue = spike_venue or random.choice(VENUE_CODES)
        if spike_venue and random.random() < 0.35:
            txn_type = random.choice(["void", "refund"])
        else:
            txn_type = random.choices(["sale", "void", "refund"], weights=[0.92, 0.04, 0.04])[0]

        payload = build_txn(venue, txn_type)
        status, body = post_json(url, payload, token, session=session)
        print(f"[{status}] {payload['venue_id']} {payload['type']} ${payload['total']} {body[:80]}")
        time.sleep(max(0.1, random.uniform(interval * 0.5, interval * 1.5)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate POS transaction stream")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", required=True, help="DRF auth token for ops user")
    parser.add_argument("--interval", type=float, default=1.2, help="Mean seconds between txns")
    parser.add_argument("--backfill", action="store_true", help="Seed history first, then stream")
    parser.add_argument("--hours", type=int, default=2)
    parser.add_argument(
        "--spike-venue",
        default=None,
        help="Bias voids/refunds toward this venue code (e.g. VEN-03)",
    )
    args = parser.parse_args()

    url = f"{args.base_url.rstrip('/')}/api/transactions/"
    if args.backfill:
        backfill(url, args.token, hours=args.hours)
    stream(url, args.token, args.interval, args.spike_venue)


if __name__ == "__main__":
    main()
