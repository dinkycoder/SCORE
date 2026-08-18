"""
scripts/count_liquidations.py - Moonwell Base liquidation feasibility.

Queries LiquidateBorrow events by TOPIC across all contracts (which the
endpoint handles reliably), then keeps those emitted by a Moonwell market.
Avoids per-address getLogs, which 400s on markets deployed mid-window.

All reads. No transaction, no gas, no signature.

Usage:
    py scripts/count_liquidations.py --days 90
"""

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import requests
from web3 import Web3
import base.config as config

LIQUIDATE_TOPIC = Web3.keccak(
    text="LiquidateBorrow(address,address,uint256,address,uint256)"
).to_0x_hex()

BLOCKS_PER_DAY = 43_200
WINDOW = 500          # topic-only queries return more, so keep windows small
MAX_RETRIES = 5


def rpc(url, method, params):
    r = requests.post(url, json={"jsonrpc": "2.0", "id": 1,
                                 "method": method, "params": params},
                      timeout=30)
    r.raise_for_status()
    j = r.json()
    if "error" in j:
        raise RuntimeError(j["error"])
    return j["result"]


def get_logs(url, lo, hi):
    """Topic-only getLogs over [lo, hi], bisecting on any failure."""
    try:
        return rpc(url, "eth_getLogs", [{
            "fromBlock": hex(lo), "toBlock": hex(hi),
            "topics": [LIQUIDATE_TOPIC],
        }])
    except Exception as e:
        if "429" in str(e):
            time.sleep(1.0)
        if hi - lo <= 1:
            return []
        mid = lo + (hi - lo) // 2
        return get_logs(url, lo, mid) + get_logs(url, mid + 1, hi)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    args = ap.parse_args()

    url = config.RPC_URL
    w3 = Web3(Web3.HTTPProvider(url))
    if w3.eth.chain_id != config.CHAIN_ID:
        sys.exit("Wrong chain")

    # Set of Moonwell markets, lowercased for comparison.
    comptroller = w3.eth.contract(
        address=Web3.to_checksum_address(config.COMPTROLLER),
        abi=[{"inputs": [], "name": "getAllMarkets",
              "outputs": [{"name": "", "type": "address[]"}],
              "stateMutability": "view", "type": "function"}])
    markets = {m.lower() for m in comptroller.functions.getAllMarkets().call()}
    print("Moonwell markets:", len(markets))

    head = int(rpc(url, "eth_blockNumber", []), 16)
    floor = max(0, head - args.days * BLOCKS_PER_DAY)
    print("Scanning blocks", format(floor, ","), "to", format(head, ","),
          "(~" + str(args.days) + " days)\n")

    borrower_counts = Counter()
    market_counts = Counter()
    total = 0
    non_moonwell = 0

    hi = head
    last_report = head
    while hi >= floor:
        lo = max(floor, hi - WINDOW + 1)
        for log in get_logs(url, lo, hi):
            emitter = log["address"].lower()
            if emitter not in markets:
                non_moonwell += 1
                continue
            data = bytes.fromhex(log["data"][2:])
            borrower = Web3.to_checksum_address("0x" + data[44:64].hex())
            borrower_counts[borrower] += 1
            market_counts[emitter] += 1
            total += 1
        # progress every ~200k blocks
        if last_report - hi >= 200_000:
            print("  ...through block", format(hi, ","),
                  "|", total, "Moonwell liquidations so far")
            last_report = hi
        hi = lo - 1

    distinct = len(borrower_counts)
    repeats = sum(1 for c in borrower_counts.values() if c > 1)

    print()
    print("=" * 56)
    print("RESULTS over ~" + str(args.days) + " days")
    print("=" * 56)
    print("  Moonwell liquidation events:   " + str(total))
    print("  distinct liquidated wallets:   " + str(distinct))
    print("  wallets liquidated >1 time:    " + str(repeats))
    print("  (non-Moonwell events ignored:  " + str(non_moonwell) + ")")
    print()

    if market_counts:
        print("  by market:")
        sym_abi = [{"inputs": [], "name": "symbol",
                    "outputs": [{"name": "", "type": "string"}],
                    "stateMutability": "view", "type": "function"}]
        for m, c in market_counts.most_common():
            try:
                s = w3.eth.contract(address=Web3.to_checksum_address(m),
                                    abi=sym_abi).functions.symbol().call()
            except Exception:
                s = m[:10]
            print("    " + s.ljust(12) + str(c))
        print()

    print("FEASIBILITY (hurdle model on Base)")
    print("  Reference: Achutha et al. trained loss-severity on 139 wallets")
    print("  after filtering, from 6 years of Compound V2.\n")
    if distinct == 0:
        print("  -> ZERO on this window. Widen --days.")
    elif distinct < 50:
        print("  -> THIN (" + str(distinct) + "). Ship triage; defer model.")
    elif distinct < 200:
        print("  -> MARGINAL (" + str(distinct) + "). PD plausible, LGD fragile.")
    else:
        print("  -> VIABLE (" + str(distinct) + "). Both stages attemptable.")

    if distinct > 0:
        print("\n  Extrapolated: ~" + str(int(distinct * 365 / args.days)) +
              " distinct wallets/year")


if __name__ == "__main__":
    main()