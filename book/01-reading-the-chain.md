\newpage

# Chapter 1 — Reading the Chain

> **Objectives**
>
> Upon completion of this chapter, the reader will be able to:
>
> 1. Explain what a lending protocol stores on-chain, and for what purpose it is stored
> 2. Describe the mechanics of overcollateralized lending: collateral factors, liquidity, shortfall, and liquidation
> 3. Query live wallet state from a lending market on Base utilizing a standard remote procedure call
> 4. State precisely what the returned values do and do not disclose concerning credit risk

## 1.1 The wrong question

The first action attempted was to score a wallet. This was the wrong initial move, and the manner of its wrongness merits examination.

A wallet address was in hand — a forty-two character string commencing with `0x` — and a number was wanted at the other end. A search was conducted for the function that would produce it. No such function exists. There is no `getRiskScore()` upon any lending protocol, for the protocols do not compute risk in the sense intended. They compute something considerably narrower, for a considerably more specific purpose, and the distinction between the two constitutes the substance of this chapter.

The correct initial question is not *how risky is this wallet?* The correct initial question is **what does the protocol know, and why does it trouble to know it?**

Answer that and the remainder follows, for a protocol's on-chain state is not a neutral description of a borrower. It is a set of values maintained for precisely one operational purpose: determining, at every instant, whether a given position may be seized. Everything the protocol stores exists to serve that determination and no other. A credit score, accordingly, must be constructed from components manufactured for a different machine.

## 1.2 What a lending protocol is

Stripped of vocabulary, a DeFi lending protocol is a smart contract holding a pool of assets, with two categories of participant.

**Suppliers** deposit assets into the pool and earn interest. The deposit is recorded, withdrawal is permitted, and the return is yield.

**Borrowers** deposit assets as collateral, borrow *different* assets against that collateral, and pay interest. The benefit is liquidity without disposal — exposure to the collateral is retained while the borrowed funds are spent.

Interest rates are established algorithmically according to utilization: the fuller the pool, the higher the rate, which attracts suppliers and discourages borrowers until equilibrium is restored. There is no loan officer, no term sheet, and no negotiation.

The difficulty this design creates is the difficulty identified in the preface. The protocol has no knowledge of the borrower's identity. It cannot verify income, cannot contact references, and — critically — **cannot sue**. A borrower who departs leaves nothing to pursue. There is no name, no jurisdiction, and no court.

The protocol therefore renders default economically irrational rather than legally punishable, employing two mechanisms.

**Overcollateralization.** Collateral exceeding the loan must be posted. Where the loan is $100 and the collateral $150, departure costs the borrower $50. Default becomes self-injury.

**Automatic liquidation.** Should collateral value decline toward debt value, the contract permits any party to repay a portion of the debt and seize a corresponding portion of the collateral, together with a premium. This is not a penalty the protocol administers; it is *an opportunity the protocol advertises to the world*. Automated agents monitor continuously, for liquidating an unhealthy position is profitable. The protocol delegates enforcement to the profit motive.

That is the entirety of the design. Every value the protocol stores concerning a borrower exists to serve it.

## 1.3 The mechanics, precisely

Precision is warranted here, because it becomes consequential the moment the values are read.

The protocol against which SCORE is constructed is **Moonwell**, a lending market deployed on Base. Moonwell is a fork of Compound V2, which is to say that its architecture — and its vocabulary — descend directly from the protocol studied by Achutha et al. (2026). That lineage is convenient: the paper's findings and this system speak a common dialect.

Compound-family protocols possess a central contract termed the **Comptroller**. It holds the risk logic: which markets exist, what risk parameters attach to each asset, and whether any given account is presently liquidatable.

**Collateral factor.** Each supported asset carries a collateral factor between 0 and 1 — the fraction of that asset's value counting toward borrowing capacity. A collateral factor of 0.75 upon ether renders $1,000 of deposited ether equivalent to $750 of borrowing power. The remaining $250 constitutes the protocol's buffer against price movement occurring between the moment a position deteriorates and the moment a liquidator is able to act. Volatile assets receive lower factors; stablecoins receive higher ones. These are governance parameters, and they constitute the protocol's entire risk model, established by vote rather than by data.

**Borrowing capacity** is the sum, across all deposited assets, of value multiplied by collateral factor.

**Liquidity and shortfall.** Capacity is then compared against debt. Compound's documentation is unusually lucid upon this point: the `getAccountLiquidity` function returns three values — an error code, a *liquidity* figure, and a *shortfall* figure — and specifies that at most one of liquidity or shortfall shall be non-zero (Compound Labs, n.d.).

That constraint contains the entire matter in a single sentence.

1. **Liquidity greater than zero.** Capacity exceeds debt. The surplus represents additional borrowing available. The position is safe.
2. **Shortfall greater than zero.** Debt exceeds capacity. The deficit represents the extent of the deterioration. **The position is liquidatable at this instant.**
3. **Both zero.** The account stands precisely at the boundary, or holds no position whatever.

The two are mutually exclusive because they constitute two directions along a single axis. There exists one quantity — capacity minus debt — and the protocol reports its magnitude in whichever field corresponds to its sign.

**Close factor and liquidation incentive.** Where shortfall is positive, the position is available to liquidators, though not without limitation. The *close factor* is defined as the percentage, ranging from zero to one hundred, of a liquidatable account's borrow that may be repaid within a single liquidation transaction (Compound Labs, n.d.) — typically fifty percent, such that a liquidator cannot extinguish an entire position in one action. The *liquidation incentive* is the premium the liquidator receives: repay $100 of debt, seize perhaps $108 of collateral. That spread is what causes the enforcement apparatus to operate.

## 1.4 What the protocol does not do

The foregoing constitutes, in its entirety, a **current-state** calculation. Liquidity and shortfall answer the question "may this position be seized *at this instant*, given *today's* prices?" That is a snapshot. It possesses neither memory nor foresight.

Consider two wallets, each reporting $10,000 of liquidity and zero shortfall. Identical, so far as the protocol is concerned. Suppose, however, that:

- **Wallet A** has borrowed and repaid on eleven occasions across two years, has never approached within twenty percent of its liquidation threshold, and adds collateral whenever prices decline.
- **Wallet B** was opened last week, borrowed the maximum immediately, has been liquidated twice upon a prior address, and sits perpetually two percent from the boundary.

The protocol perceives no distinction. It is not designed to. It inquires only whether the position is presently seizable, and for both the answer is no.

A *lender*, however — a party determining whether to extend superior terms, or a risk desk determining where to direct attention — cares enormously about the distinction. That distinction is *behavioral*, and it resides in the transaction history rather than in the current state.

Taiichi Ohno, the originator of the Toyota Production System from which lean manufacturing in the United States derives, taught that root cause is reached by asking "Why?" five times (Ohno, 1988). Applied to the present matter, the interrogation proceeds as follows:

1. **Why is this wallet at risk?** Its debt approaches its borrowing capacity.
2. **Why does its debt approach its capacity?** The borrower increased leverage, or collateral prices declined.
3. **Why did the borrower increase leverage?** The borrower is disposed to operate near the boundary.
4. **Why is the borrower so disposed?** Prior conduct establishes a pattern of maximal borrowing without commensurate repayment.
5. **Why does that pattern matter?** Because it is predictive of the next occasion.

The protocol answers the first question. It cannot answer the second, and the remaining three lie entirely beyond its scope. Yet questions three through five constitute credit assessment; question one constitutes merely a solvency check.

This is the gap. It is the gap exploited by Achutha et al. (2026), and it is the gap into which SCORE is constructed. The protocol computes **solvency**. Credit requires **propensity**. These are not the same inquiry, and the second is answered nowhere on-chain; it must be constructed.

## 1.5 Reading the chain

By what method, then, are these values obtained?

A blockchain node exposes a JSON-RPC interface: a structured request is transmitted over HTTP, and structured data is returned. For present purposes a single method is material.

**`eth_call`** executes a contract function *without* creating a transaction. It runs the code against current state, returns the result, alters nothing, consumes no gas, and requires neither wallet nor signature. It is a read. Practically, this signifies that the financial state of every borrower within a lending market may be queried, continuously, for the cost of the HTTP requests.

The significance of that warrants a pause, for it is genuinely peculiar to any reader arriving from traditional finance. There is no application, no data-sharing agreement, and no per-inquiry fee payable to a bureau. The equivalent of every borrower's file within a lending market is available to any party possessing an internet connection, in real time.

Calling a contract function requires its **ABI** — Application Binary Interface — a JSON description of the contract's functions, their inputs, and their outputs. The ABI instructs the client how to encode the request and decode the response. It is a schema, and nothing more mysterious than that.

An **RPC endpoint** is also required: a URL addressing a node. Base publishes public endpoints for both its main network and its Sepolia test network.

A word is warranted here concerning which of the two this project employs, as the answer proved contrary to the original plan. Development against a test network is the ordinary practice, and the initial specification for this work assumed it. Moonwell, however, maintains no deployment upon any Base test network; its contracts exist upon Base mainnet, Ethereum, OP Mainnet, and Moonbeam, and upon no testnet whatever. The plan did not survive consultation with the protocol's own documentation.

The consequence is less severe than it appears. Reads are performed by `eth_call`, which creates no transaction, consumes no gas, and requires no signature. Reading Moonwell upon mainnet is therefore entirely safe, and it possesses the considerable advantage of returning real borrowers holding real positions rather than the empty state of an unused testnet. Contract deployment, when that stage arrives in Chapter 5, may still target Sepolia. Reading and writing are separable in this respect, and only writing carries risk.

Base warrants brief description, as the platform selection is not incidental. It is an Ethereum Layer 2 constructed upon the OP Stack and launched by Coinbase in August 2023. Layer 2 signifies that transactions execute upon Base and are periodically committed to Ethereum for security — cheaper and faster than Ethereum itself, with Ethereum's settlement guarantees beneath. As of mid-2026 Base carried approximately $11.86 billion in total value locked, the highest of any Layer 2 by that measure, and led all Layer 2 networks in activity with approximately 12.89 million daily transactions and 382,500 active addresses (AMBCrypto, 2026; SpotedCrypto, 2026). Such figures move; they should be regarded as a dated snapshot rather than as a fact.

The detail of greatest consequence to this project is **Flashblocks**, introduced in 2025: 200-millisecond pre-confirmations, with transactions typically settling in approximately two seconds. A credit system intending to operate in *real time* rather than in *daily batch* requires an underlying chain upon which two seconds constitutes the unit of time. That is the specific reason this is a Base project rather than an Ethereum mainnet project.

## 1.6 The client

The client follows. It is brief, and the brevity is the point — the conceptual labor of this chapter resides almost entirely in comprehending the meaning of the values, and scarcely at all in obtaining them.

```python
"""
Base RPC client for querying lending-protocol wallet state.
"""

import logging
from typing import Dict, Any
from web3 import Web3

logger = logging.getLogger(__name__)

# Minimal ABI: only the function required.
COMPTROLLER_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "getAccountLiquidity",
        "outputs": [
            {"internalType": "uint256", "name": "error", "type": "uint256"},
            {"internalType": "uint256", "name": "liquidity", "type": "uint256"},
            {"internalType": "uint256", "name": "shortfall", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    }
]


class BaseRPCClient:
    """Reads wallet state from a Compound-family lending market on Base."""

    def __init__(self, rpc_url: str, comptroller_address: str):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError(f"Cannot connect to {rpc_url}")

        logger.info("Connected to Base. Chain ID: %s", self.w3.eth.chain_id)

        self.comptroller = self.w3.eth.contract(
            address=Web3.to_checksum_address(comptroller_address),
            abi=COMPTROLLER_ABI,
        )

    def get_account_liquidity(self, wallet_address: str) -> Dict[str, Any]:
        """
        Query borrowing capacity against outstanding debt.

        Returns liquidity (surplus capacity) and shortfall (deficit).
        At most one is non-zero. A non-zero shortfall indicates that the
        position is liquidatable at this instant.
        """
        addr = Web3.to_checksum_address(wallet_address)
        error, liquidity, shortfall = (
            self.comptroller.functions.getAccountLiquidity(addr).call()
        )

        if error != 0:
            raise RuntimeError(f"Comptroller returned error code {error}")

        return {
            "liquidity_raw": int(liquidity),
            "shortfall_raw": int(shortfall),
        }
```

Three elements warrant comment.

**`.call()` is the `eth_call`.** That single method constitutes the distinction between reading and writing. A transaction would require a signature, gas, and a wait for inclusion. This requires none of them.

**The `stateMutability: "view"` marker** within the ABI is the contract declaring that the function does not modify state. It is what renders the read both safe and free.

**Raw integers are returned deliberately.** Solidity possesses no floating-point numbers; values are stored as large integers with an implied number of decimal places. The conversion to dollars requires knowing the scaling convention, and that convention is *asserted but not yet verified*. Converting prematurely would embed an unverified assumption within every downstream figure. Chapter 2 addresses the verification; until then the raw values are preserved.

## 1.7 What may and may not yet be asserted

A wallet's solvency state may now be read on demand, in real time, for any address within the market.

What this affords is a **point-in-time solvency check**. It is genuinely useful — a positive shortfall constitutes a hard and unambiguous signal that a position is presently in difficulty — and it is genuinely insufficient. It possesses no memory. A wallet liquidated four times in the previous year and a wallet holding a spotless two-year record are indistinguishable where their current positions coincide.

Three requirements remain, each constituting a later chapter.

**History.** Prior conduct is the strongest predictor available. This requires reading *events* — the log entries protocols emit upon every deposit, borrow, repayment, and liquidation — rather than current state alone.

**Relationships.** Achutha et al. (2026) determined that features derived from the transaction *graph* — the manner in which wallets connect to one another and to assets — carried genuine predictive signal, and within their loss-severity model outperformed financial features outright. A wallet is not an island.

**A decomposition.** Banking has decomposed credit risk in the same manner for decades: **Expected Loss = PD × LGD × EAD** — probability of default, loss given default, and exposure at default. This framing derives from the Basel capital framework and the single-risk-factor model beneath it (Basel Committee on Banking Supervision, 2006; Gordy, 2003), and Achutha et al. (2026) map it directly onto on-chain data: liquidation substitutes for default, liquidation severity for loss given default, and outstanding position for exposure. That decomposition constitutes the spine of everything following.

## 1.8 One warning, stated early

A wallet is not a person.

Ten thousand addresses may be created this afternoon at effectively no cost. Nothing binds them to their creator, and nothing prevents their use in any manner desired — constructing clean histories upon nine in order to cultivate a favorable score while borrowing recklessly upon the tenth, or distributing a single risky position across one hundred addresses such that no individual address appears alarming.

This is the **Sybil attack**, named and analyzed by John Douceur (2002), whose central result is unforgiving: absent a logically centralized authority, Sybil attacks are always possible except under assumptions concerning resource parity that do not obtain in practice. No cryptographic ingenuity causes the difficulty to disappear.

Candor concerning the implication is warranted. Any wallet-level credit score is, in principle, subject to manipulation by any party willing to operate multiple wallets. This is not a defect awaiting correction in a subsequent version; it is a structural property of pseudonymous systems. What may be accomplished is the elevation of cost and the narrowing of exposure — graph analysis detecting coordinated clusters, conservative priors applied to wallets possessing thin history, verifiable credentials optionally binding an attested identity to an address (W3C, 2022), and design choices constraining how far any single score may move. Achutha et al. (2026) are candid concerning this fragility within their own work rather than claiming a resolved defense, and this book maintains the same position.

The matter is raised in Chapter 1, prior to any modeling, because it should color the reading of everything subsequent. What is under construction is useful. What is under construction is not unbreakable.

## Summary

The chapter's conclusions are as follows.

1. A lending protocol's on-chain state exists to answer one operational question: whether a position may be seized at this instant.
2. Overcollateralization combined with automatic liquidation substitutes for the legal enforcement that pseudonymity forecloses.
3. `getAccountLiquidity` returns liquidity (surplus capacity) or shortfall (deficit); at most one is non-zero, as they constitute two signs of a single quantity.
4. `eth_call` reads contract state without a transaction and without cost, rendering every borrower's financial position continuously readable by any party.
5. Current state measures **solvency**. Credit requires **propensity**, which resides in history and relationships rather than in the present snapshot.
6. Wallets are not persons, and no score constructed upon wallet addresses is Sybil-proof.

## Exercises

1. Explain to a reader possessing no background why a lending protocol requires collateral exceeding the sum it lends. Then explain what that requirement renders impossible.
2. A wallet reports liquidity of zero and shortfall of zero. Identify three materially distinct circumstances producing this reading, and describe how they might be distinguished.
3. `getAccountLiquidity` employs the protocol's own price oracle. What might go wrong with that arrangement, and what would the consequence be for a score constructed upon it? Achutha et al. (2026) name this as an explicit limitation of their own pipeline; locate the passage and read it.
4. Sketch a method employing a wallet's *event history*, rather than its current state, to distinguish Wallet A from Wallet B in §1.4. What would be counted?

## References

Achutha, M., Hegde, B. R., & Das, B. (2026). Transaction graph-based predictive hurdle model for credit scoring in DeFi lending protocols. *International Journal of Data Science and Analytics, 22*, 124. https://doi.org/10.1007/s41060-026-01097-7

AMBCrypto. (2026). *Layer 2 total value locked rankings* [Data reported from L2BEAT].

Basel Committee on Banking Supervision. (2006). *International convergence of capital measurement and capital standards: A revised framework, comprehensive version.* Bank for International Settlements.

Compound Labs. (n.d.). *Compound v2 documentation: Comptroller.* https://docs.compound.finance/v2/comptroller/

Douceur, J. R. (2002). The Sybil attack. In P. Druschel, F. Kaashoek, & A. Rowstron (Eds.), *Peer-to-peer systems: IPTPS 2002* (Lecture Notes in Computer Science, Vol. 2429, pp. 251–260). Springer. https://doi.org/10.1007/3-540-45748-8_24

Gordy, M. B. (2003). A risk-factor model foundation for ratings-based bank capital rules. *Journal of Financial Intermediation, 12*(3), 199–232. https://doi.org/10.1016/S1042-9573(03)00040-8

Ohno, T. (1988). *Toyota production system: Beyond large-scale production.* Productivity Press.

SpotedCrypto. (2026). *Layer 2 activity analysis* [Data reported from CoinBureau].

W3C. (2022). *Decentralized identifiers (DIDs) v1.0* [W3C Recommendation]. World Wide Web Consortium. https://www.w3.org/TR/did-core/
