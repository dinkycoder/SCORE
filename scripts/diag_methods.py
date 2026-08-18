"""Confirm eth_call works while eth_getLogs 400s, and surface any error body."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import requests
from web3 import Web3
import base.config as config

url = config.RPC_URL

# 1. Does eth_blockNumber work? (basic connectivity)
r = requests.post(url, json={"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]})
print("eth_blockNumber:", r.status_code, r.text[:200])

# 2. Does eth_call work? (this is what ran all session)
comptroller = config.COMPTROLLER
# getAllMarkets() selector
selector = Web3.keccak(text="getAllMarkets()").to_0x_hex()[:10]
r = requests.post(url, json={"jsonrpc":"2.0","id":1,"method":"eth_call",
    "params":[{"to":comptroller,"data":selector},"latest"]})
print("eth_call:       ", r.status_code, r.text[:120])

# 3. Does eth_getLogs work? Print the FULL body, not the wrapped exception.
head_r = requests.post(url, json={"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]})
head = int(head_r.json()["result"], 16)
r = requests.post(url, json={"jsonrpc":"2.0","id":1,"method":"eth_getLogs",
    "params":[{"fromBlock":hex(head-5),"toBlock":hex(head)}]})
print("eth_getLogs:    ", r.status_code)
print("  body:", r.text[:400])