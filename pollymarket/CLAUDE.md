# pollymarket

Read-only Polymarket neg-risk arbitrage observer. No wallet, no order placement, no API keys required — all endpoints used are public.

Full context, decisions made, and open next steps: see `HANDOFF.md` in this directory (written for the human user, but has the full picture).

## Quick facts

- `scan_arbitrage.py`: fetches active neg-risk events from Gamma API (`gamma-api.polymarket.com/events`), batch-fetches order books from CLOB API (`clob.polymarket.com/books`), logs every scan cycle to `data/observations.csv` (gitignored).
- `report.py`: aggregates `data/observations.csv` into per-event stats (hit rate, gap size, streak duration).
- Tested working as of 2026-08-17 — a live `--once` run found a real 1.7% gap on a small Russian parliamentary election market, size-limited to ~20 shares (i.e. real but not economically meaningful at that size — consistent with the project's hypothesis that most retail-visible arb is too small/fleeting to matter).
- This directory currently lives inside `biangyang/Arduino` (the Arduino IDE source fork) purely because that's the repo this session was bound to — unrelated to the Arduino codebase around it. User may migrate it to a dedicated repo later (attempted via `mcp__github__create_repository` but the GitHub App integration lacked repo-creation permission — 403).

## If asked to continue this project

Check `data/observations.csv` first to see if any real monitoring history has accumulated since the handoff — that data (not assumptions) should drive whatever comes next.
