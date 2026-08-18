"""Fast probe: are there ANY Moonwell liquidations in recent history?
Checks a few sample windows and reports immediately."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import requests
from web3 import Web3
import base.config as config

url = config.RPC_URL
TOPIC = Web3.keccak(text="LiquidateBorrow(address,address,uint256,address,uint256)").to_0x_hex()

def rpc(method, params):
    r = requests.post(url, json={"jsonrpc":"2.0","id":1,"method":method,"params":params}, timeout=30)
    r.raise_for_status()
    j = r.json()
    if "error" in j:
        raise RuntimeError(j["error"])
    return j["result"]

w3 = Web3(Web3.HTTPProvider(url))
comptroller = w3.eth.contract(
    address=Web3.to_checksum_address(config.COMPTROLLER),
    abi=[{"inputs": [], "name": "getAllMarkets",
          "outputs": [{"name": "", "type": "address[]"}],
          "stateMutability": "view", "type": "function"}])
markets = {m.lower() for m in comptroller.functions.getAllMarkets().call()}

head = int(rpc("eth_blockNumber", []), 16)
print("head block:", format(head, ","))
print("probing 2,000-block windows at several depths...\n")

# Sample windows at increasing age: ~1 day, ~1 week, ~1 month, ~3 months back.
for label, back in [("~1 day", 43_200), ("~1 week", 302_400),
                    ("~1 month", 1_296_000), ("~3 months", 3_888_000)]:
    hi = head - back
    lo = hi - 2000
    try:
        logs = rpc("eth_getLogs", [{"fromBlock": hex(lo), "toBlock": hex(hi),
                                    "topics": [TOPIC]}])
        mw = [l for l in logs if l["address"].lower() in markets]
        print(label.ljust(12), "block", format(hi, ",").rjust(12),
              "|", len(logs), "total LiquidateBorrow,", len(mw), "Moonwell")
    except Exception as e:
        print(label.ljust(12), "FAIL:", str(e)[:80])