"""Inspect what getAllMarkets returns - are all 21 addresses valid?"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from web3 import Web3
import base.config as config

w3 = Web3(Web3.HTTPProvider(config.RPC_URL))
comptroller = w3.eth.contract(
    address=Web3.to_checksum_address(config.COMPTROLLER),
    abi=[{"inputs": [], "name": "getAllMarkets",
          "outputs": [{"name": "", "type": "address[]"}],
          "stateMutability": "view", "type": "function"}],
)
markets = comptroller.functions.getAllMarkets().call()
print("count:", len(markets))
print()

symbol_abi = [{"inputs": [], "name": "symbol",
               "outputs": [{"name": "", "type": "string"}],
               "stateMutability": "view", "type": "function"}]

for i, m in enumerate(markets):
    cs = Web3.to_checksum_address(m)
    is_zero = int(m, 16) == 0
    code = w3.eth.get_code(cs)
    has_code = len(code) > 0
    try:
        sym = w3.eth.contract(address=cs, abi=symbol_abi).functions.symbol().call()
    except Exception:
        sym = "(no symbol)"
    flag = ""
    if is_zero:
        flag = "  <-- ZERO ADDRESS"
    elif not has_code:
        flag = "  <-- NO CONTRACT CODE"
    print(str(i).rjust(2), cs, sym.ljust(14), "code:" + str(len(code)).rjust(5), flag)