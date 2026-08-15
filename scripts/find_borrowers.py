"""Find live Moonwell borrowers on Base and check their liquidity."""

from web3 import Web3

COMPTROLLER = "0xfBb21d0380beE3312B33c4353c8936a0F13EF26C"
MARKET      = "0xEdc817A28E8B93B03976FBd4a3dDBc9f7D176c22"   # Moonwell USDC
RPC         = "https://mainnet.base.org"
LOOKBACK    = 20000    # blocks (~11 hours on Base)
WINDOW      = 2000     # blocks per getLogs request
LIMIT       = 15       # borrowers to check

BORROW_ABI = [{
    "anonymous": False,
    "inputs": [
        {"indexed": False, "name": "borrower",       "type": "address"},
        {"indexed": False, "name": "borrowAmount",   "type": "uint256"},
        {"indexed": False, "name": "accountBorrows", "type": "uint256"},
        {"indexed": False, "name": "totalBorrows",   "type": "uint256"},
    ],
    "name": "Borrow", "type": "event",
}]

COMPTROLLER_ABI = [{
    "inputs": [{"name": "account", "type": "address"}],
    "name": "getAccountLiquidity",
    "outputs": [
        {"name": "error",     "type": "uint256"},
        {"name": "liquidity", "type": "uint256"},
        {"name": "shortfall", "type": "uint256"},
    ],
    "stateMutability": "view", "type": "function",
}]

w3 = Web3(Web3.HTTPProvider(RPC))
if not w3.is_connected():
    raise SystemExit("Cannot reach " + RPC)
if w3.eth.chain_id != 8453:
    raise SystemExit("Wrong chain: " + str(w3.eth.chain_id) + " (want 8453)")

head = w3.eth.block_number
print("Connected to Base mainnet. Head block:", format(head, ","))

topic = Web3.keccak(text="Borrow(address,uint256,uint256,uint256)").to_0x_hex()
market = w3.eth.contract(address=Web3.to_checksum_address(MARKET), abi=BORROW_ABI)

borrowers = []
to_block = head
floor = head - LOOKBACK
print("Scanning for Borrow events...")

while to_block > floor and len(borrowers) < LIMIT:
    from_block = max(floor, to_block - WINDOW + 1)
    try:
        logs = w3.eth.get_logs({
            "fromBlock": from_block,
            "toBlock": to_block,
            "address": Web3.to_checksum_address(MARKET),
            "topics": [topic],
        })
    except Exception as e:
        print("  ", from_block, "-", to_block, "failed:", str(e)[:60])
        to_block = from_block - 1
        continue

    for raw in logs:
        addr = market.events.Borrow().process_log(raw)["args"]["borrower"]
        if addr not in borrowers:
            borrowers.append(addr)

    if logs:
        print("  ", format(from_block, ","), "-", format(to_block, ","),
              ":", len(logs), "events,", len(borrowers), "unique borrowers")

    to_block = from_block - 1

if not borrowers:
    raise SystemExit("No Borrow events found. Try raising LOOKBACK.")

print()
print("Checking", len(borrowers[:LIMIT]), "borrowers against the Comptroller")
print()
print("address".ljust(44), "liquidity".rjust(16), "shortfall".rjust(16), " state")
print("-" * 100)

c = w3.eth.contract(address=Web3.to_checksum_address(COMPTROLLER), abi=COMPTROLLER_ABI)

for addr in borrowers[:LIMIT]:
    try:
        err, liq, short = c.functions.getAccountLiquidity(addr).call()
    except Exception as e:
        print(addr.ljust(44), "call failed:", str(e)[:40])
        continue
    if err != 0:
        print(addr.ljust(44), "comptroller error", err)
        continue
    state = "UNDERWATER" if short > 0 else ("healthy" if liq > 0 else "no position")
    print(addr.ljust(44),
          format(liq / 1e18, ",.2f").rjust(16),
          format(short / 1e18, ",.2f").rjust(16),
          "", state)

print()
print("NEXT: pick a healthy address above, look it up on app.moonwell.fi,")
print("and compare its borrowing capacity to the liquidity column.")
print("If they match, the 1e18 scaling is right. If off by 1000x, it is not.")