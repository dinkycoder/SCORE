"""Diagnose the getLogs 400 by making one tiny request and printing the
full error, plus the exact params sent."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from web3 import Web3
import base.config as config

w3 = Web3(Web3.HTTPProvider(config.RPC_URL))
print("connected:", w3.is_connected(), "chain:", w3.eth.chain_id)

head = w3.eth.block_number
comptroller = w3.eth.contract(
    address=Web3.to_checksum_address(config.COMPTROLLER),
    abi=[{"inputs": [], "name": "getAllMarkets",
          "outputs": [{"name": "", "type": "address[]"}],
          "stateMutability": "view", "type": "function"}],
)
market = comptroller.functions.getAllMarkets().call()[0]
market = Web3.to_checksum_address(market)
topic = Web3.keccak(text="LiquidateBorrow(address,address,uint256,address,uint256)").to_0x_hex()

print("market:", market)
print("topic: ", topic)
print("head:  ", head)
print()

# Attempt 1: exactly what the failing script sends.
params = {
    "fromBlock": head - 20,
    "toBlock": head,
    "address": market,
    "topics": [topic],
}
print("Attempt 1 - integer blocks, checksummed address:")
try:
    logs = w3.eth.get_logs(params)
    print("  OK,", len(logs), "logs")
except Exception as e:
    print("  FAIL:", str(e)[:300])

# Attempt 2: hex block numbers.
params2 = {
    "fromBlock": hex(head - 20),
    "toBlock": hex(head),
    "address": market,
    "topics": [topic],
}
print("\nAttempt 2 - hex block strings:")
try:
    logs = w3.eth.get_logs(params2)
    print("  OK,", len(logs), "logs")
except Exception as e:
    print("  FAIL:", str(e)[:300])

# Attempt 3: no topic filter at all (does address alone work?).
print("\nAttempt 3 - address only, no topics:")
try:
    logs = w3.eth.get_logs({"fromBlock": head - 20, "toBlock": head, "address": market})
    print("  OK,", len(logs), "logs")
except Exception as e:
    print("  FAIL:", str(e)[:300])

# Attempt 4: raw JSON-RPC, bypassing web3 formatting, to see Alchemy's own message.
print("\nAttempt 4 - raw eth_getLogs via provider:")
try:
    raw = w3.provider.make_request("eth_getLogs", [{
        "fromBlock": hex(head - 20),
        "toBlock": hex(head),
        "address": market,
        "topics": [topic],
    }])
    print("  response:", json.dumps(raw)[:400])
except Exception as e:
    print("  FAIL:", str(e)[:300])