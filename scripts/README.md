# scripts/

Ad-hoc, uncommitted-to-test diagnostic and data-gathering tools. Nothing
here is imported by `src/` or covered by `pytest`; each script is a
standalone investigation. Several earlier scripts that answered a specific
one-off question and have since been superseded by committed code or a
definitive finding were removed (`diag_getlogs.py`, `diag_methods.py`,
`diag_markets.py`, `probe_liq.py`, `read_position.py` - all recoverable
from git history if the reasoning behind a since-fixed bug is ever needed
again).

## What's here and why

- **`count_liquidations.py`** - the real tool. Answers PHASE_0.md open
  question 1 with a counted, dated CSV of Moonwell `LiquidateBorrow`
  events, instead of the fee-revenue inference the docs previously relied
  on. Queries in exactly 10-block windows (the confirmed free-tier
  `eth_getLogs` cap - see `probe_range.py` below), threaded, with retry
  and backoff so a rate-limited window fails loud into a retry rather than
  silently undercounting.

- **`probe_range.py`** - finds the exact `eth_getLogs` block-range cap on
  whatever endpoint `config.RPC_URL` points at. Confirmed 2026-08-22:
  exactly 10 blocks on this Alchemy free tier (their own error message
  states the number). Re-run this first if the RPC provider or tier ever
  changes - `count_liquidations.py`'s `WINDOW` constant assumes the
  current answer, not a rediscovered one.

- **`bench_rpc.py`** - fires a burst of unpaced `eth_call`s and reports
  whether the endpoint can sustain the volume a live score needs. Quick
  sanity check before trusting a new endpoint or tier.

- **`find_borrowers.py`** - scans recent `Borrow` events (via the public
  `mainnet.base.org` endpoint, deliberately not the configured RPC key -
  see below) and checks each borrower's live liquidity, to find real
  wallets with open positions. Useful whenever a previously-known
  reference wallet closes its position (as the one in
  `tests/test_latency.py` has) and a new one is needed.

## Two things worth knowing before running any of these

**Endpoint choice matters.** `count_liquidations.py`, `probe_range.py`,
and `bench_rpc.py` all use `config.RPC_URL` (the configured key in
`.env`). `find_borrowers.py` deliberately hardcodes the public
`mainnet.base.org` endpoint instead. Don't run two `config.RPC_URL`-based
scripts at once - the rate limit that matters is account-wide, not
per-script, and running one while another is mid-scan measurably slows
both down (observed directly: a `bench_rpc.py` run during a
`count_liquidations.py` scan coincided with that scan's throughput
dropping from ~3.2 to ~2.5 windows/s for several minutes).

**The rate limit is not fixable by adding workers.** Measured 2026-08-22:
`count_liquidations.py`'s sustained throughput was ~4.4 windows/s with 2
workers AND with 5 workers - the ceiling is an account-wide throttle, not
a concurrency limit. More workers just means more requests queue up
waiting on the same budget.
