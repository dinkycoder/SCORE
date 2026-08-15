"""Time a burst of RPC calls against whatever endpoint config points at."""

import sys
import time
sys.path.insert(0, "../src")

from web3 import Web3
import base.config as config

print(config.describe())
print()

w3 = Web3(Web3.HTTPProvider(config.RPC_URL))
if not w3.is_connected():
    sys.exit("Cannot connect")
if w3.eth.chain_id != config.CHAIN_ID:
    sys.exit("Wrong chain: " + str(w3.eth.chain_id))

COMPTROLLER_ABI = [
    {"inputs": [{"name": "account", "type": "address"}],
     "name": "getAccountLiquidity",
     "outputs": [{"name": "error", "type": "uint256"},
                 {"name": "liquidity", "type": "uint256"},
                 {"name": "shortfall", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
]

c = w3.eth.contract(address=Web3.to_checksum_address(config.COMPTROLLER),
                    abi=COMPTROLLER_ABI)
wallet = Web3.to_checksum_address("0xAA503ae37ba4A6FCC2fD6CC3F3Dc776Ab11B7b67")

N = 40
print("Firing", N, "calls with no pacing...")
start = time.perf_counter()
errors = 0
for i in range(N):
    try:
        c.functions.getAccountLiquidity(wallet).call()
    except Exception as e:
        errors += 1
        if errors == 1:
            print("  first error:", str(e)[:70])
elapsed = time.perf_counter() - start

print()
print("elapsed:      " + format(elapsed, ".2f") + "s")
print("per call:     " + format(elapsed / N * 1000, ".0f") + "ms")
print("errors:       " + str(errors) + "/" + str(N))
print()
if errors == 0 and elapsed < 10:
    print("PASS - endpoint can sustain the call volume a score needs.")
else:
    print("PROBLEM - still throttled or slow. Do not proceed.")