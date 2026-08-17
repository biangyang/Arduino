#!/usr/bin/env python3
"""
Polymarket neg-risk arbitrage observer.

This script does NOT place any orders and never touches a wallet or private
key. It only reads public market data and logs what it sees, so we can
answer a simple question with real numbers: how often does a genuine
risk-free arbitrage window appear on Polymarket, how big is it, and how
long does it last before it disappears?

Background
----------
Some Polymarket events are "neg-risk" markets: a single question with many
mutually-exclusive outcomes (e.g. "Who wins the election?"), where each
outcome is its own Yes/No market but exactly one outcome can resolve Yes.

If you buy one "Yes" share of every outcome in the group, you are
guaranteed exactly $1 at resolution (one leg pays $1, all others pay $0).
So if the sum of the best "Yes" ask prices across all legs is less than
$1, buying one of each locks in a profit *before fees, slippage, gas, and
execution risk*. That gap is what this script watches for.

This is an OBSERVATION tool, not a trading bot. It writes every check to a
CSV file so you can later analyze frequency / size / duration with
report.py, before anyone decides whether acting on this is worth it.
"""
import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"
CLOB_BOOKS_URL = "https://clob.polymarket.com/books"

CSV_FIELDS = [
    "timestamp",
    "event_id",
    "event_title",
    "num_legs",
    "sum_best_ask",
    "implied_gap",
    "min_top_of_book_size",
    "below_threshold",
]


def fetch_negrisk_groups(session, top_n):
    """Return active neg-risk event groups, sorted by 24h volume.

    Each group is: {event_id, title, legs: [{question, token_id}]}
    where token_id is the CLOB asset id for that leg's "Yes" outcome.
    """
    resp = session.get(
        GAMMA_EVENTS_URL,
        params={
            "closed": "false",
            "limit": 200,
            "order": "volume24hr",
            "ascending": "false",
        },
        timeout=20,
    )
    resp.raise_for_status()
    events = resp.json()

    groups = []
    for event in events:
        if not event.get("negRisk"):
            continue

        legs = []
        for market in event.get("markets", []):
            if not (market.get("active") and not market.get("closed") and not market.get("archived")):
                continue
            token_ids = market.get("clobTokenIds")
            outcomes = market.get("outcomes")
            if isinstance(token_ids, str):
                token_ids = json.loads(token_ids)
            if isinstance(outcomes, str):
                outcomes = json.loads(outcomes)
            if not token_ids or not outcomes:
                continue
            # clobTokenIds[0] is always the "Yes" outcome token.
            legs.append({"question": market.get("question", ""), "token_id": token_ids[0]})

        if len(legs) >= 2:
            groups.append({"event_id": event["id"], "title": event.get("title", ""), "legs": legs})

        if len(groups) >= top_n:
            break

    return groups


def fetch_books(session, token_ids):
    """Batch-fetch order books for a list of token ids. Returns {token_id: book}."""
    books = {}
    # The CLOB /books endpoint accepts a batch, but very large batches get
    # unreliable, so chunk requests defensively.
    chunk_size = 50
    for i in range(0, len(token_ids), chunk_size):
        chunk = token_ids[i:i + chunk_size]
        payload = [{"token_id": t} for t in chunk]
        resp = session.post(CLOB_BOOKS_URL, json=payload, timeout=20)
        resp.raise_for_status()
        for book in resp.json():
            books[book["asset_id"]] = book
    return books


def best_ask(book):
    """Return (price, size) of the lowest ask in a book, or (None, None)."""
    asks = book.get("asks") or []
    if not asks:
        return None, None
    lowest = min(asks, key=lambda a: float(a["price"]))
    return float(lowest["price"]), float(lowest["size"])


def scan_once(session, groups, threshold, writer, quiet=False):
    all_token_ids = [leg["token_id"] for group in groups for leg in group["legs"]]
    books = fetch_books(session, all_token_ids)
    now = datetime.now(timezone.utc).isoformat()

    hits = 0
    for group in groups:
        prices = []
        sizes = []
        missing = False
        for leg in group["legs"]:
            book = books.get(leg["token_id"])
            if book is None:
                missing = True
                break
            price, size = best_ask(book)
            if price is None:
                missing = True
                break
            prices.append(price)
            sizes.append(size)

        if missing:
            continue

        total = sum(prices)
        gap = 1.0 - total
        below_threshold = total < threshold
        writer.writerow({
            "timestamp": now,
            "event_id": group["event_id"],
            "event_title": group["title"],
            "num_legs": len(group["legs"]),
            "sum_best_ask": f"{total:.4f}",
            "implied_gap": f"{gap:.4f}",
            "min_top_of_book_size": f"{min(sizes):.2f}",
            "below_threshold": below_threshold,
        })

        if below_threshold:
            hits += 1
            if not quiet:
                print(f"[{now}] POSSIBLE ARB  {group['title']!r}  "
                      f"sum={total:.4f}  gap={gap:.4f}  "
                      f"min_size={min(sizes):.2f}  legs={len(group['legs'])}")

    return hits


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--top-n", type=int, default=25, help="how many neg-risk events to track, by 24h volume")
    parser.add_argument("--interval", type=int, default=60, help="seconds between scan cycles")
    parser.add_argument("--threshold", type=float, default=0.995,
                         help="flag a group when sum of best asks is below this "
                              "(leaves headroom for fees/slippage; 1.0 = no headroom)")
    parser.add_argument("--once", action="store_true", help="run a single scan cycle and exit")
    parser.add_argument("--data-dir", default=str(Path(__file__).parent / "data"),
                         help="directory to write observations.csv into")
    parser.add_argument("--refresh-groups-every", type=int, default=10,
                         help="re-fetch the tracked event list every N cycles (events open/close over time)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / "observations.csv"
    file_exists = out_path.exists()

    session = requests.Session()
    session.headers.update({"User-Agent": "pollymarket-arb-observer/1.0"})

    with open(out_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
            f.flush()

        groups = fetch_negrisk_groups(session, args.top_n)
        print(f"Tracking {len(groups)} neg-risk event groups "
              f"({sum(len(g['legs']) for g in groups)} legs total). "
              f"Logging to {out_path}")

        cycle = 0
        while True:
            if cycle > 0 and args.refresh_groups_every and cycle % args.refresh_groups_every == 0:
                groups = fetch_negrisk_groups(session, args.top_n)

            try:
                hits = scan_once(session, groups, args.threshold, writer, quiet=False)
                f.flush()
                if hits == 0:
                    print(f"[{datetime.now(timezone.utc).isoformat()}] scan complete, no gaps below threshold")
            except requests.RequestException as exc:
                print(f"request error, will retry next cycle: {exc}")

            cycle += 1
            if args.once:
                break
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
