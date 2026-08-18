"""Find the getLogs block-range ceiling on this endpoint."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import requests
from web3 import Web3
import base.config as config

url = config.RPC_URL
TOPIC = Web3.keccak(text="LiquidateBorrow(address,address,uint256,address,uint256)").to_0x_hex()

def try_range(span):
    head = int(requests.post(url, json={"jsonrpc":"2.0","id":1,
        "method":"eth_blockNumber","params":[]}, timeout=15).json()["result"], 16)
    r = requests.post(url, json={"jsonrpc":"2.0","id":1,"method":"eth_getLogs",
        "params":[{"fromBlock":hex(head-span),"toBlock":hex(head),
                   "topics":[TOPIC]}]}, timeout=30)
    try:
        r.raise_for_status()
        j = r.json()
        if "error" in j:
            return "error: " + str(j["error"])[:80]
        return "OK (" + str(len(j["result"])) + " logs)"
    except Exception as e:
        # pull the JSON body if there is one
        try:
            body = r.json()
            return "HTTP " + str(r.status_code) + ": " + str(body)[:120]
        except Exception:
            return "HTTP " + str(r.status_code) + " (no body): " + str(e)[:80]

for span in [5, 10, 50, 100, 500, 1000, 2000]:
    print(str(span).rjust(5), "blocks:", try_range(span))