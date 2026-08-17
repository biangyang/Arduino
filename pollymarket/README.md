# pollymarket — arbitrage observer

Not a trading bot. This watches Polymarket's public market data and records
how often a specific, well-defined risk-free arbitrage window actually
appears, so that's answered with real numbers instead of "I saw someone
online say it works." No wallet, no private key, no order placement
anywhere in this code.

## What it's looking for

Polymarket has "neg-risk" events: one question, several mutually exclusive
outcomes (e.g. "Who wins the election?" with a market per candidate), where
exactly one outcome resolves Yes. Buy one Yes share of every outcome and
you're guaranteed $1 at resolution. So if the sum of the best "Yes" ask
price across every outcome is less than $1, that gap is a real arbitrage
edge *before* fees, slippage, gas, and the risk of not getting all legs
filled at once.

## Setup

```bash
cd pollymarket
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run the observer

```bash
python3 scan_arbitrage.py                # loop forever, 60s between scans
python3 scan_arbitrage.py --once          # single pass, useful for testing
python3 scan_arbitrage.py --top-n 50 --interval 30 --threshold 0.99
```

Every cycle it checks the top N neg-risk events by 24h volume and appends
one row per event to `data/observations.csv` — whether or not a gap was
found. That's on purpose: you need the non-events too, to know the real
frequency.

Flags:
- `--top-n`: how many events to track (by volume). Low-volume markets have
  wide, thin books where an "arbitrage" is really just no one having
  bothered to fill the order book — not real money you could capture.
- `--threshold`: sum-of-best-asks cutoff to flag as a hit. Default `0.995`,
  i.e. only flag gaps with at least 0.5% headroom, since Polymarket fees,
  slippage on size, and gas on withdrawal all eat into the raw gap.
- `--interval`: seconds between scans. Real windows can close in seconds,
  so a coarse interval will undercount how often they appear and won't
  tell you much about how long they last.

## Read the results

```bash
python3 report.py
```

Prints, per event: how many scans hit the threshold, the biggest and
average gap seen, how long each streak lasted before the market closed it,
and the smallest top-of-book size available (i.e. how much you could
actually have captured, not just the quoted price).

## Reading the output honestly

- A gap that appears once for one scan cycle and never again is most
  likely fleeting and probably not realistically capturable by hand.
- A gap with tiny `min_top_of_book_size` is real on paper but you can't
  put meaningful money into it.
- None of this accounts for the risk of only some legs filling before the
  price moves — this script checks quoted prices, it doesn't simulate
  execution.

This is step 1 of "does this opportunity actually exist and is it worth
building on." No money moves until the data says it's worth the next step.
