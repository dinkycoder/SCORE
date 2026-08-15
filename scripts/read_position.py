"""Reconstruct a wallet's Moonwell position. Rate-limit tolerant."""

import sys
import time
from web3 import Web3

COMPTROLLER = "0xfBb21d0380beE3312B33c4353c8936a0F13EF26C"
RPC = "https://mainnet.base.org"
WAD = 10 ** 18
PAUSE = 0.25          # seconds between calls
MAX_RETRIES = 6

COMPTROLLER_ABI = [
    {"inputs": [{"name": "account", "type": "address"}],
     "name": "getAssetsIn",
     "outputs": [{"name": "", "type": "address[]"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "account", "type": "address"}],
     "name": "getAccountLiquidity",
     "outputs": [{"name": "error", "type": "uint256"},
                 {"name": "liquidity", "type": "uint256"},
                 {"name": "shortfall", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "oracle",
     "outputs": [{"name": "", "type": "address"}],
     "stateMutability": "view", "type": "function"},
]

MARKETS_ABI_2 = [
    {"inputs": [{"name": "", "type": "address"}], "name": "markets",
     "outputs": [{"name": "isListed", "type": "bool"},
                 {"name": "collateralFactorMantissa", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
]
MARKETS_ABI_3 = [
    {"inputs": [{"name": "", "type": "address"}], "name": "markets",
     "outputs": [{"name": "isListed", "type": "bool"},
                 {"name": "collateralFactorMantissa", "type": "uint256"},
                 {"name": "isComped", "type": "bool"}],
     "stateMutability": "view", "type": "function"},
]

MTOKEN_ABI = [
    {"inputs": [{"name": "account", "type": "address"}],
     "name": "getAccountSnapshot",
     "outputs": [{"name": "error", "type": "uint256"},
                 {"name": "mTokenBalance", "type": "uint256"},
                 {"name": "borrowBalance", "type": "uint256"},
                 {"name": "exchangeRateMantissa", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "symbol",
     "outputs": [{"name": "", "type": "string"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "underlying",
     "outputs": [{"name": "", "type": "address"}],
     "stateMutability": "view", "type": "function"},
]

ORACLE_ABI = [
    {"inputs": [{"name": "mToken", "type": "address"}],
     "name": "getUnderlyingPrice",
     "outputs": [{"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
]

ERC20_ABI = [
    {"inputs": [], "name": "decimals",
     "outputs": [{"name": "", "type": "uint8"}],
     "stateMutability": "view", "type": "function"},
]


def rpc(fn, *args, label=""):
    """Call a contract function, backing off on rate limits."""
    delay = 1.0
    for attempt in range(MAX_RETRIES):
        try:
            time.sleep(PAUSE)
            return fn(*args).call()
        except Exception as e:
            msg = str(e)
            if "429" in msg or "Too Many Requests" in msg:
                print("    rate limited" + (" (" + label + ")" if label else "") +
                      ", waiting " + format(delay, ".0f") + "s...")
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise SystemExit("Gave up after " + str(MAX_RETRIES) + " retries. "
                     "Consider a dedicated RPC endpoint.")


if len(sys.argv) < 2:
    sys.exit("Usage: py read_position.py <wallet_address>")

wallet = Web3.to_checksum_address(sys.argv[1])
w3 = Web3(Web3.HTTPProvider(RPC))
if not w3.is_connected():
    sys.exit("Cannot reach " + RPC)
if w3.eth.chain_id != 8453:
    sys.exit("Wrong chain: " + str(w3.eth.chain_id))

comptroller = w3.eth.contract(address=Web3.to_checksum_address(COMPTROLLER),
                              abi=COMPTROLLER_ABI)
oracle_addr = rpc(comptroller.functions.oracle, label="oracle")
oracle = w3.eth.contract(address=Web3.to_checksum_address(oracle_addr),
                         abi=ORACLE_ABI)

print("Wallet: ", wallet)
print("Block:  ", format(w3.eth.block_number, ","))
print("Oracle: ", oracle_addr)
print()

markets = rpc(comptroller.functions.getAssetsIn, wallet, label="getAssetsIn")
if not markets:
    sys.exit("Wallet has entered no markets.")

print("Entered", len(markets), "market(s). Reading positions...")
print()

# Work out which markets() variant this fork uses -- once, not per market.
markets_abi = None
for abi in (MARKETS_ABI_2, MARKETS_ABI_3):
    try:
        probe = w3.eth.contract(address=Web3.to_checksum_address(COMPTROLLER), abi=abi)
        rpc(probe.functions.markets, Web3.to_checksum_address(markets[0]), label="markets probe")
        markets_abi = abi
        break
    except SystemExit:
        raise
    except Exception:
        continue

cf_contract = (w3.eth.contract(address=Web3.to_checksum_address(COMPTROLLER),
                               abi=markets_abi) if markets_abi else None)

rows = []
total_coll = 0
total_weighted = 0
total_debt = 0

for m in markets:
    m_cs = Web3.to_checksum_address(m)
    mt = w3.eth.contract(address=m_cs, abi=MTOKEN_ABI)

    err, m_bal, borrow_bal, exch = rpc(mt.functions.getAccountSnapshot, wallet,
                                       label="snapshot")
    if err != 0:
        print("  ", m, "snapshot error", err)
        continue

    # Skip empty markets entirely -- saves 4 calls each.
    if m_bal == 0 and borrow_bal == 0:
        continue

    try:
        symbol = rpc(mt.functions.symbol, label="symbol")
    except Exception:
        symbol = m[:8]

    try:
        u = rpc(mt.functions.underlying, label="underlying")
        erc20 = w3.eth.contract(address=Web3.to_checksum_address(u), abi=ERC20_ABI)
        d = int(rpc(erc20.functions.decimals, label="decimals"))
    except Exception:
        d = 18

    price = rpc(oracle.functions.getUnderlyingPrice, m_cs, label="price")

    cf = None
    if cf_contract is not None:
        try:
            cf = int(rpc(cf_contract.functions.markets, m_cs, label="CF")[1])
        except Exception:
            cf = None

    supplied_raw = m_bal * exch // WAD
    coll_usd = supplied_raw * price // WAD
    debt_usd = borrow_bal * price // WAD
    weighted = coll_usd * cf // WAD if cf is not None else 0

    total_coll += coll_usd
    total_weighted += weighted
    total_debt += debt_usd

    rows.append((symbol[:10], supplied_raw / (10 ** d), borrow_bal / (10 ** d),
                 coll_usd / WAD, debt_usd / WAD,
                 format(cf / WAD, ".2f") if cf is not None else "?"))

print("market".ljust(10) + "supplied".rjust(18) + "borrowed".rjust(18) +
      "coll USD".rjust(16) + "debt USD".rjust(14) + "  CF")
print("-" * 78)
for r in rows:
    print(r[0].ljust(10) + format(r[1], ",.4f").rjust(18) +
          format(r[2], ",.4f").rjust(18) + format(r[3], ",.2f").rjust(16) +
          format(r[4], ",.2f").rjust(14) + "  " + r[5])

print()
print("TOTALS")
print("  collateral (unweighted): $" + format(total_coll / WAD, ",.2f"))
print("  collateral (weighted):   $" + format(total_weighted / WAD, ",.2f"))
print("  debt:                    $" + format(total_debt / WAD, ",.2f"))

print()
print("REAL LEVERAGE")
if total_coll > 0:
    print("  LTV (debt/collateral):           " + format(total_debt / total_coll, ".4f"))
if total_weighted > 0:
    util = total_debt / total_weighted
    print("  Capacity used (debt/weighted):   " + format(util, ".4f"))
    print("  Headroom to liquidation:         " + format(1 - util, ".4f"))

err, liquidity, shortfall = rpc(comptroller.functions.getAccountLiquidity,
                                wallet, label="liquidity")
derived = total_weighted - total_debt
reported = liquidity - shortfall

print()
print("DENOMINATION CHECK")
print("  derived  (weighted coll - debt): " + format(derived / WAD, ",.2f"))
print("  reported (getAccountLiquidity):  " + format(reported / WAD, ",.2f"))

if reported == 0 and derived == 0:
    print("  -> both zero; inconclusive")
elif reported != 0:
    ratio = derived / reported
    print("  ratio:                           " + format(ratio, ".6f"))
    if 0.98 <= ratio <= 1.02:
        print()
        print("  CONFIRMED. Values are USD scaled by 1e18.")
    else:
        print()
        print("  MISMATCH. Scaling assumption is wrong. Do not build on it.")