"""
scripts/count_liquidations.py - Moonwell Base liquidation feasibility.

Answers PHASE_0.md open question 1 with a counted, dated dataset instead
of a fee-revenue inference: how many LiquidateBorrow events has Moonwell
on Base actually emitted, over what window, and at what RPC cost.

The free-tier RPC caps eth_getLogs at EXACTLY a 10-block range (confirmed
empirically 2026-08-22 via scripts/probe_range.py - Alchemy's own error
message states the number). A previous version of this script queried in
500-block windows and bisected on failure, which meant most requests were
wasted discovering a limit that is now known in advance. This version
queries in exactly 10-block windows from the start and threads the
requests, since 10-block windows over any real window are tens of
thousands of individual round trips - sequential would take hours.

Queries by topic only (no address filter), then keeps events emitted by
a Moonwell market - matches the previous script's finding that address
filtering doesn't change the block-range cap, and topic-only lets one
query serve all markets instead of one call per market per window.

All reads. No transaction, no gas, no signature.

Usage:
    py -u scripts/count_liquidations.py --days 7 --workers 8 --out liquidations.csv
"""

import argparse
import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import requests
from eth_abi import decode as abi_decode
from web3 import Web3
import base.config as config

LIQUIDATE_TOPIC = Web3.keccak(
    text="LiquidateBorrow(address,address,uint256,address,uint256)"
).to_0x_hex()

BLOCKS_PER_DAY = 43_200
WINDOW = 10          # the confirmed free-tier eth_getLogs cap - see module docstring
MAX_RETRIES = 12     # the account-wide rate limit is real and sustained (measured
                      # ~5 req/s ceiling regardless of worker count); patience here
                      # trades wall time for a CLEAN zero-failure count instead of
                      # a "lower bound" - see module docstring.

_session = requests.Session()


def rpc(url, method, params):
    r = _session.post(url, json={"jsonrpc": "2.0", "id": 1,
                                  "method": method, "params": params},
                       timeout=30)
    r.raise_for_status()
    j = r.json()
    if "error" in j:
        raise RuntimeError(j["error"])
    return j["result"]


def get_window(url, lo, hi):
    """Fetch one <=WINDOW-block range, retrying with backoff on rate limits.
    Any other failure is re-raised - a gap in the count must be visible,
    not silently dropped, or the final number is a claim without evidence."""
    delay = 0.5
    for attempt in range(MAX_RETRIES):
        try:
            return rpc(url, "eth_getLogs", [{
                "fromBlock": hex(lo), "toBlock": hex(hi),
                "topics": [LIQUIDATE_TOPIC],
            }])
        except Exception as e:
            if "429" in str(e) or "Too Many" in str(e):
                time.sleep(delay)
                delay = min(delay * 2, 8.0)
                continue
            raise
    raise RuntimeError("exhausted retries on window " + str((lo, hi)))


def decode_event(log):
    data = bytes.fromhex(log["data"][2:])
    liquidator, borrower, repay_amount, mtoken_collateral, seize_tokens = (
        abi_decode(["address", "address", "uint256", "address", "uint256"], data)
    )
    return {
        "block_number": int(log["blockNumber"], 16),
        "tx_hash": log["transactionHash"],
        "market": Web3.to_checksum_address(log["address"]),
        "liquidator": Web3.to_checksum_address(liquidator),
        "borrower": Web3.to_checksum_address(borrower),
        "repay_amount_raw": str(repay_amount),
        "seize_tokens_raw": str(seize_tokens),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=1.0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="liquidations.csv")
    args = ap.parse_args()

    url = config.RPC_URL
    w3 = Web3(Web3.HTTPProvider(url))
    if w3.eth.chain_id != config.CHAIN_ID:
        sys.exit("Wrong chain")

    comptroller = w3.eth.contract(
        address=Web3.to_checksum_address(config.COMPTROLLER),
        abi=[{"inputs": [], "name": "getAllMarkets",
              "outputs": [{"name": "", "type": "address[]"}],
              "stateMutability": "view", "type": "function"}])
    markets = {m.lower() for m in comptroller.functions.getAllMarkets().call()}
    print("Moonwell markets:", len(markets), flush=True)

    head = w3.eth.block_number
    span = int(args.days * BLOCKS_PER_DAY)
    floor = max(0, head - span)
    n_windows = (span + WINDOW - 1) // WINDOW
    print(f"Scanning blocks {floor:,} to {head:,} (~{args.days:g} days, "
          f"{n_windows:,} windows of {WINDOW} blocks, {args.workers} workers)",
          flush=True)

    windows = []
    hi = head
    while hi >= floor:
        lo = max(floor, hi - WINDOW + 1)
        windows.append((lo, hi))
        hi = lo - 1

    events = []
    failures = []
    start = time.perf_counter()
    done = 0
    report_every = max(1, len(windows) // 20)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(get_window, url, lo, hi): (lo, hi)
                   for lo, hi in windows}
        for fut in as_completed(futures):
            lo, hi = futures[fut]
            done += 1
            try:
                logs = fut.result()
                for log in logs:
                    if log["address"].lower() in markets:
                        events.append(decode_event(log))
            except Exception as e:
                failures.append((lo, hi, str(e)[:120]))

            if done % report_every == 0 or done == len(windows):
                elapsed = time.perf_counter() - start
                rate = done / elapsed if elapsed > 0 else 0
                print(f"  {done:,}/{len(windows):,} windows | "
                      f"{len(events)} events so far | "
                      f"{rate:.1f} windows/s | {elapsed:.0f}s elapsed",
                      flush=True)

    elapsed = time.perf_counter() - start

    events.sort(key=lambda e: e["block_number"])
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "block_number", "tx_hash", "market", "liquidator", "borrower",
            "repay_amount_raw", "seize_tokens_raw",
        ])
        writer.writeheader()
        writer.writerows(events)

    distinct_borrowers = len({e["borrower"] for e in events})

    print()
    print("=" * 60)
    print(f"RESULTS over ~{args.days:g} days (blocks {floor:,}-{head:,})")
    print("=" * 60)
    print(f"  windows queried:            {len(windows):,}")
    print(f"  windows failed:             {len(failures)}")
    print(f"  elapsed:                    {elapsed:.0f}s "
          f"({len(windows) / elapsed:.1f} windows/s)")
    print(f"  Moonwell liquidation events: {len(events)}")
    print(f"  distinct liquidated wallets: {distinct_borrowers}")
    print(f"  CSV written:                {args.out}")
    if failures:
        print(f"\n  WARNING: {len(failures)} windows never succeeded - the "
              f"count above is a LOWER BOUND, not exact. First failure:")
        print(f"    {failures[0]}")
    print()

    if len(windows) > 0 and elapsed > 0:
        rate = len(windows) / elapsed
        full_year_windows = (365 * BLOCKS_PER_DAY) / WINDOW
        print(f"  At this measured rate ({rate:.1f} windows/s, "
              f"{args.workers} workers), a full year would take "
              f"~{full_year_windows / rate / 60:.0f} minutes of wall time "
              f"and ~{full_year_windows:,.0f} RPC requests.")


if __name__ == "__main__":
    main()
