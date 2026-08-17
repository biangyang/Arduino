#!/usr/bin/env python3
"""
Summarize observations.csv produced by scan_arbitrage.py.

Answers the questions this whole project started from: how often does a
below-$1 gap actually show up, how big is it, and how long does it
persist before the market closes it?
"""
import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def parse_ts(s):
    return datetime.fromisoformat(s)


def load_rows(path):
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            row["sum_best_ask"] = float(row["sum_best_ask"])
            row["implied_gap"] = float(row["implied_gap"])
            row["min_top_of_book_size"] = float(row["min_top_of_book_size"])
            row["below_threshold"] = row["below_threshold"] == "True"
            row["timestamp"] = parse_ts(row["timestamp"])
            yield row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(Path(__file__).parent / "data"))
    args = parser.parse_args()

    csv_path = Path(args.data_dir) / "observations.csv"
    if not csv_path.exists():
        print(f"No data yet at {csv_path}. Run scan_arbitrage.py first.")
        return

    by_event = defaultdict(list)
    total_checks = 0
    for row in load_rows(csv_path):
        by_event[row["event_id"]].append(row)
        total_checks += 1

    print(f"Total scan-checks logged: {total_checks}")
    print(f"Distinct events tracked:  {len(by_event)}")
    print()

    opportunity_events = 0
    all_gaps = []
    all_durations = []

    for event_id, rows in by_event.items():
        rows.sort(key=lambda r: r["timestamp"])
        below_rows = [r for r in rows if r["below_threshold"]]
        if not below_rows:
            continue
        opportunity_events += 1
        title = rows[0]["event_title"]
        gaps = [r["implied_gap"] for r in below_rows]
        all_gaps.extend(gaps)

        # Estimate how long each contiguous streak of "below threshold"
        # observations lasted, using gaps between consecutive timestamps.
        streak_start = None
        prev_ts = None
        streaks = []
        for r in rows:
            if r["below_threshold"]:
                if streak_start is None:
                    streak_start = r["timestamp"]
                prev_ts = r["timestamp"]
            else:
                if streak_start is not None:
                    streaks.append((prev_ts - streak_start).total_seconds())
                    streak_start = None
        if streak_start is not None:
            streaks.append((prev_ts - streak_start).total_seconds())
        all_durations.extend(streaks)

        print(f"- {title!r} (event {event_id})")
        print(f"    hits: {len(below_rows)}/{len(rows)} checks   "
              f"best gap: {max(gaps):.4f}   avg gap: {sum(gaps)/len(gaps):.4f}")
        if streaks:
            print(f"    streaks (sec): {[round(s) for s in streaks]}   "
                  f"min top-of-book size seen: {min(r['min_top_of_book_size'] for r in below_rows):.2f}")

    print()
    print(f"Events with at least one below-threshold reading: {opportunity_events}/{len(by_event)}")
    if all_gaps:
        print(f"Average gap when present: {sum(all_gaps)/len(all_gaps):.4f}  "
              f"(max {max(all_gaps):.4f})")
    if all_durations:
        print(f"Streak duration (sec): min={min(all_durations):.0f} "
              f"avg={sum(all_durations)/len(all_durations):.0f} max={max(all_durations):.0f}")
        print("(a streak of 0s usually means it was gone by the very next scan cycle "
              "-- shrink --interval on the scanner to see finer detail)")


if __name__ == "__main__":
    main()
