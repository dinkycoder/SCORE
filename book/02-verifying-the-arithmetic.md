\newpage

# Chapter 2 — Verifying the Arithmetic

> **Objectives**
>
> Upon completion of this chapter, the reader will be able to:
>
> 1. Reconstruct a wallet's complete position across every market of a lending protocol
> 2. Explain the decimal scaling conventions of Compound-family protocols, and why they resolve as they do
> 3. Verify a numerical assumption by independent derivation rather than by inspection
> 4. Distinguish leverage measures that describe a position from the single measure a protocol enforces
> 5. Recognize the class of defect that passes its own tests

## 2.1 The debt incurred in Chapter 1

Chapter 1 concluded with a client capable of reading a wallet's solvency state, and with an obligation left unsatisfied.

The client returned raw integers. It did not convert them to dollars, and the omission was deliberate. Solidity possesses no floating-point arithmetic; values are stored as large integers with an implied number of decimal places. Eighteen decimals is the prevailing convention, and the conversion would therefore be a division by 10^18. The convention is prevailing, however, rather than universal, and the difference between those two conditions is the difference between a figure that is correct and a figure that is wrong by three orders of magnitude.

Converting prematurely would have embedded an unverified assumption within every subsequent number the system produced. A wallet reporting forty thousand dollars of borrowing capacity would report forty million, or forty, and nothing in the software would object. The error would be silent, plausible, and total.

This chapter discharges that obligation. In doing so it produces something more valuable than the answer: a method for establishing such answers, and a demonstration of what occurs when the method is omitted.

The chapter's organizing observation is that every defect encountered during this stage of construction shared a single property. **Each was an assumption that passed its own tests.** Not a careless assumption, and not an obviously fragile one — an assumption held upon grounds that appeared sufficient, which nonetheless required independent confirmation before it could be relied upon.

## 2.2 What one function cannot tell you

Consider two wallets, each returning identical values from `getAccountLiquidity`:

```
0xAA503a...   liquidity: 9,160.32   shortfall: 0.00
0x753218...   liquidity:     2.64   shortfall: 0.00
```

The intuitive reading is that the first is a substantial position and the second a trivial one. The intuitive reading is unsupported.

Recall from Chapter 1 that `liquidity` reports *remaining borrowing capacity* — the sum a wallet could still borrow before reaching its limit. It does not report collateral, and it does not report debt. A wallet returning 2.64 might hold five hundred thousand dollars of collateral and have borrowed to within three dollars of its ceiling. Such a wallet is arguably the more precarious of the two, and the function reporting on both cannot distinguish them.

Leverage is a ratio. `getAccountLiquidity` returns a difference. No arrangement of a single difference will produce the ratio, because the denominator is absent.

Obtaining it requires three further inquiries:

1. **`getAssetsIn(address)`** upon the Comptroller, returning the markets a wallet has entered.
2. **`getAccountSnapshot(address)`** upon each market contract, returning the wallet's supplied balance, borrowed balance, and the exchange rate converting protocol tokens to underlying tokens.
3. **`getUnderlyingPrice(market)`** upon the protocol's price oracle, returning the value the protocol itself assigns to each asset.

The third warrants emphasis. The oracle is not consulted because prices are otherwise unavailable; prices are available from numerous commercial sources. The oracle is consulted because it supplies *the price against which liquidation is enforced*. A model scoring positions at one price while the protocol enforces at another will be wrong precisely when accuracy matters most, which is to say during the volatility that precedes liquidation. Achutha et al. (2026) identify their own pricing pipeline as a limitation of their work for a closely related reason, observing that transaction-implied values are practical but do not substitute for a manipulation-resistant oracle.

## 2.3 The scaling, worked through

Here resides the chapter's one passage of genuine arithmetic. It is worth following closely, because the convention appears arbitrary until it is multiplied out, whereupon it becomes elegant.

Let *d* denote the number of decimals of a market's underlying token. USD Coin employs six. Wrapped ether employs eighteen. Coinbase Wrapped Bitcoin employs eight.

The values returned by the protocol are scaled as follows:

| Value | Source | Scaling |
|---|---|---|
| `mTokenBalance` | `getAccountSnapshot` | 10^8 |
| `borrowBalance` | `getAccountSnapshot` | 10^d |
| `exchangeRateMantissa` | `getAccountSnapshot` | 10^(18 − 8 + d) |
| `price` | `getUnderlyingPrice` | 10^(36 − d) |

The final row is the peculiar one. Why should an oracle scale its prices according to the decimals of the asset being priced? The reason emerges upon performing the conversion.

Converting a protocol-token balance to an underlying-token balance:

```
underlying_raw = mTokenBalance × exchangeRate / 10^18
               = 10^8 × 10^(10+d) / 10^18
               = 10^d
```

The result is the underlying token in its native units. Converting that to a dollar value:

```
usd = underlying_raw × price / 10^18
    = 10^d × 10^(36−d) / 10^18
    = 10^18
```

**The *d* cancels.** That is the entire purpose of the 36 − *d* convention. Whatever the decimals of the underlying token, the resulting dollar value arrives scaled by 10^18. A position in six-decimal USD Coin and a position in eighteen-decimal wrapped ether may be summed directly, without per-asset adjustment, because the oracle's scaling was designed to make them commensurable.

This also supplies the answer to Chapter 1's outstanding question. USD values are scaled by 10^18, and dividing by 10^18 therefore yields dollars.

That statement, however, remains an assumption. It has been derived from documented conventions, which is superior to having been guessed, and it is not yet the same as having been verified. Documentation describes intent. Deployed contracts exhibit behavior. Where the two diverge, the deployed contract is correct by definition.

## 2.4 Verification by independent derivation

The weak form of verification is inspection: compute a figure, observe that it appears plausible, and proceed. This method is worthless. A figure wrong by a factor of one thousand appears entirely plausible when nothing establishes the expected magnitude.

The strong form is independent derivation. Compute the same quantity by two routes that share no assumptions, and compare.

The Comptroller's `getAccountLiquidity` returns the difference between a wallet's risk-weighted collateral and its debt. That computation occurs within the contract, in Solidity, employing the protocol's own arithmetic. It is available directly.

The same quantity may also be assembled from components: retrieve each market's supplied and borrowed balances, convert them to dollars using the oracle price and the scaling derived in §2.3, apply each market's collateral factor to the collateral, sum across markets, and subtract debt from weighted collateral.

The two routes share nothing but the underlying chain state. If the scaling assumption is mistaken, the derived figure will diverge from the reported figure by whatever factor the mistake introduces. If the assumption is correct, they will agree.

Applied to a live wallet on 15 August 2026:

```
market       supplied      borrowed     coll USD    debt USD    CF
mUSDC     18,967.1682        0.0000    18,964.60        0.00    0.88
mWETH          0.0000        6.5000         0.00   12,242.38    0.84

collateral (unweighted): $18,964.60
collateral (weighted):   $16,688.84
debt:                    $12,242.38

derived  (weighted collateral − debt):  4,446.46
reported (getAccountLiquidity):         4,446.46
ratio:                                  1.000000
```

Agreement to six decimal places. The scaling assumption is confirmed, and confirmed in a manner admitting no alternative explanation: two computations sharing no arithmetic arrived at one number.

A subsidiary confirmation appears within the same output. Multiplying the unweighted collateral by the mUSDC collateral factor — 18,964.60 × 0.88 — yields 16,688.85, matching the weighted figure. The collateral-factor logic is correct as well. Observe also that the mWETH collateral factor of 0.84 contributes nothing, the wallet having supplied no wrapped ether. A verification that produced the right total by way of a compensating error would be unlikely to reproduce each component correctly.

The general principle merits statement plainly, as it governs the remainder of this project:

> **A numerical assumption is verified when a second derivation, sharing none of its premises, reproduces its result. It is not verified by appearing reasonable.**

## 2.5 The defect that passed its tests

The verification just performed exposed a defect in software that had been written, tested, and committed.

Chapter 1's feature extraction computed a loan-to-value ratio in the following manner:

```python
total_value = liquidity + shortfall
ltv = shortfall / total_value
```

The reasoning is not absurd. Shortfall measures the extent to which a position exceeds its capacity; liquidity measures the extent to which it falls short of that capacity; their sum was taken to represent the position's scale.

Recall, however, the constraint stated in Chapter 1: at most one of liquidity and shortfall is non-zero. For any solvent wallet, shortfall is zero. The numerator is therefore zero, and:

**For every healthy wallet in existence, this feature returned exactly 0.0.**

The feature acquired a non-zero value only once a wallet had become liquidatable — at which point no model is required, as the protocol has already reached the same conclusion and automated agents are already acting upon it. As a predictor the feature carried no information whatever. Its column would have been constant across the entire training set.

The wallet examined in §2.4 carries an actual loan-to-value ratio of 0.6446 and employs 73 percent of its borrowing capacity. Chapter 1's feature reported zero leverage.

The circumstance warranting attention is that **the unit tests passed.** They passed because they were written against the same misunderstanding that produced the defect. A test constructed by the author of a mistaken function, in the same session and upon the same premises, examines internal consistency rather than correctness. It verifies that the code performs what its author intended. It cannot verify that the intention was sound.

What exposed the defect was not a test. It was the arrival of real data, and the observation that a feature purporting to measure leverage reported zero for a wallet that was plainly leveraged.

The corrective is a test asserting a property the defect would violate, independent of implementation:

```python
def test_capacity_used_exceeds_ltv_when_cf_below_one():
    """Regression guard: the Week 1 defect reported zero leverage for
    every healthy wallet. Both measures must be positive for a real
    borrower, and the capacity measure must exceed raw LTV whenever
    collateral factors fall below one."""
    p = make_position([
        market("mUSDC", collateral=18_966, cf=0.88),
        market("mWETH", debt=12_226, cf=0.84),
    ])

    f = extract_features(p)
    assert f.ltv > 0
    assert f.capacity_used > f.ltv
```

This test would have failed against the original implementation. It encodes a relationship that must obtain among the quantities regardless of how they are computed, and it is therefore not susceptible to sharing the defect's premises.

## 2.6 Two ratios, only one of which is enforced

Correcting the defect required determining what ought to have been computed, and the answer proved to be two quantities rather than one.

**Loan-to-value** is debt divided by collateral. For the wallet in §2.4:

```
12,242.38 / 18,964.60 = 0.6446
```

This is the intuitive measure and the one general audiences recognize. It is also not the quantity the protocol enforces.

**Capacity utilization** is debt divided by *risk-weighted* collateral, weighting each asset by its collateral factor:

```
12,242.38 / 16,688.84 = 0.7336
```

Nearly nine percentage points higher, and this is the ratio that governs. It reaches 1.0 at precisely the moment a position becomes liquidatable, because it is the same comparison the Comptroller performs. Loan-to-value understates risk by the extent to which collateral factors fall below unity, and that extent varies by asset, so the understatement is not even uniform across wallets.

A third quantity follows directly and proves more legible to a lender than either ratio. If liquidation occurs when weighted collateral declines to meet debt, then the adverse price movement required is:

```
(16,688.84 / 12,242.38) − 1 = 0.3651
```

**A 36.5 percent adverse move would render this position liquidatable.** That figure requires no familiarity with collateral factors to interpret, which matters considerably given the regulatory constraint discussed in the preface: a credit decision must be explicable to the party it affects (CFPB, 2022).

## 2.7 A feature absent from the paper

Examination of the wallet in §2.4 disclosed something the source literature does not address.

The wallet supplies USD Coin and borrows wrapped ether. Its collateral is designed to hold constant value; its debt is not. The position is, in economic substance, a short position in ether.

The consequence is that this wallet is liquidated by a price *increase*. Not a decrease. Should ether appreciate by 36.5 percent, the dollar value of the debt rises to meet the weighted collateral and the position becomes seizable, though the borrower has done nothing and the collateral has not moved at all.

Now consider a second wallet supplying USD Coin and borrowing USD Coin, at identical capacity utilization of 0.7336. Every leverage measure discussed thus far reports the two as equivalent. They are not remotely equivalent. The second wallet carries essentially no price risk; its collateral and debt move together by construction. The first carries full directional exposure to a volatile asset.

Treating these positions as equivalent is a modeling error, and it is an error that raw leverage measurement cannot detect. The remedy is a feature recording whether collateral and debt occupy assets of differing volatility characteristics:

```python
volatility_mismatch: bool
"""True when collateral and debt are in different assets, so the
position carries directional price risk beyond its leverage. A wallet
with stable collateral and volatile debt is short that asset and can
be liquidated by a price RISE, which LTV alone does not reveal."""
```

The provenance of this feature warrants comment, as it bears upon the argument of this book. It did not originate in Achutha et al. (2026), whose financial feature set comprises loan-to-value, net depositing, net borrowing, net flow, repayment ratio, transaction frequency, and average transaction size — every one of them a scalar computed over a wallet's aggregate activity, and none of them recording the *composition* of a position. Nor did it originate in the Basel framework, which decomposes expected loss into probability, severity, and exposure without addressing which assets constitute the exposure.

It originated in the examination of a single wallet's actual holdings, and in noticing that the two columns contained different tickers.

This is the return on constructing rather than merely reading. The literature supplies the framework, and the framework is indispensable — the expected-loss decomposition is the spine of everything this system does. What the literature cannot supply is the particular observation that follows from watching real positions on a real protocol. Achutha et al. worked upon a static extract of Compound V2 spanning six years. Their method could not readily surface a composition effect, because composition was not among the features they extracted, and it was not among the features they extracted because nothing in the framework directed attention toward it.

Ten minutes with one live wallet did.

## 2.8 Performance as a correctness problem

There remains a difficulty that presents as engineering and is in fact epistemic.

The position reconstruction described in §2.2 requires numerous contract calls: one to enumerate the markets, one snapshot per market, one price per market holding a position, one for the account liquidity. Against the wallet examined, this amounted to approximately twelve network round trips.

The first attempt failed outright. The public endpoint at `mainnet.base.org` returned HTTP 429 — Too Many Requests — partway through, having been asked for roughly forty-five calls in immediate succession. This is not a defect in the software. It is a shared free resource behaving as shared free resources behave, and it constitutes an architectural constraint rather than an inconvenience. A system intending to score wallets continuously requires an endpoint provisioned for the purpose.

With a dedicated endpoint the calls succeeded, at approximately 149 milliseconds each. Measured across ten complete scoring operations:

```
p50:  1,647 ms
p95:  1,683 ms
```

The Phase 0 specification stipulates a 95th-percentile latency below 500 milliseconds. The system exceeded its target by a factor exceeding three.

The order in which this was addressed matters more than the remedy. **The test was written first, and permitted to fail.**

```python
assert p95 < P95_TARGET_MS, (
    "p95 of " + format(p95, ".0f") + "ms exceeds the "
    + str(P95_TARGET_MS) + "ms target. Sequential eth_call round trips "
    "are the bottleneck; batching via Multicall3 is the fix."
)
```

Optimization undertaken without such a test proceeds until the author judges the result adequate. Optimization undertaken against a failing assertion proceeds until a stated condition obtains. The first is a matter of sentiment; the second is a matter of specification.

A second test accompanied it, and this is the one that renders the exercise a verification rather than an optimization:

```python
def test_correctness_survives_optimisation(client):
    """Batched reads must produce the same numbers as sequential ones.
    Compares the client against the Comptroller's own liquidity figure,
    which is computed independently on-chain."""
    position = client.get_wallet_position(TEST_WALLET)
    derived = position.total_weighted_collateral_usd - position.total_debt_usd
    reported = (position.reported_liquidity_usd
                - position.reported_shortfall_usd)
    assert derived == pytest.approx(reported, rel=0.02)
```

This is the §2.4 verification, converted from a one-time investigation into a standing guarantee. Any change to how the client reads the chain must continue to reproduce the Comptroller's own arithmetic. Speed that compromises truth is not an improvement; it is a regression that happens to run quickly.

The remedy itself is a contract called Multicall3, deployed at an identical address upon essentially every Ethereum-compatible chain by way of deterministic deployment. It exposes a function accepting an array of calls and executing all of them within a single `eth_call`. Twelve round trips become one.

An additional property of the arrangement deserves note. Multicall3 guarantees that every value returned originates from the same block. A client issuing twelve sequential requests may straddle a block boundary and assemble a position that never existed — collateral from one block, debt from the next. For a credit system this is not a theoretical concern, as block boundaries are precisely where liquidations occur.

Results following the change:

```
p50:    156 ms
p95:    173 ms
target: 500 ms
```

A single network round trip to the provider was measured at 149 milliseconds. A complete scoring operation — every market snapshot, every price, the account liquidity, the block number — now costs seven milliseconds more than one request. There is nothing further to optimize along this axis; the residual cost is the propagation delay to the provider's datacenter.

The correctness test remained green throughout.

## 2.9 The pattern

Four defects were encountered during this stage, and their common structure is worth stating explicitly, as it constitutes the chapter's transferable lesson.

1. **A contract address supplied from memory.** Thirty-one of forty hexadecimal characters were correct. The remainder were fabricated. The address was plausible, was accepted without checking, and was wrong. Verification required consulting the protocol's own documentation, which required approximately thirty seconds.

2. **A leverage feature returning zero.** Its unit tests passed, having been written against the same misunderstanding that produced it. Verification required real data.

3. **A scaling convention assumed to be dollars.** The assumption was correct, was derived from documented conventions, and was nonetheless unverified until two independent derivations agreed. Had it been wrong, every figure the system produced would have been wrong by a factor of one thousand or more, silently.

4. **An endpoint assumed adequate.** It functioned under casual use and failed under the load a single scoring operation generates. Verification required measurement.

In each instance the assumption was held upon grounds that appeared sufficient. In each instance those grounds were insufficient. And in each instance the cost of verification, undertaken at the time, was minutes — whereas the cost of discovering the defect later, in the presence of a lender, would have been considerable.

The discipline this suggests is not skepticism concerning everything, which is unworkable. It is the identification of assumptions whose failure would be *silent*, and the verification of those specifically. An incorrect contract address announces itself immediately, as every call reverts. An incorrect scaling convention announces nothing at all. The second category is the dangerous one, and it is the category warranting an independent derivation before anything is constructed atop it.

## Summary

1. `getAccountLiquidity` returns remaining capacity, which is a difference. Leverage is a ratio and requires the position's components: `getAssetsIn`, `getAccountSnapshot`, and the oracle price.
2. Compound-family oracles scale prices by 10^(36 − d) so that the underlying token's decimals cancel, causing all dollar values to arrive scaled by 10^18 irrespective of asset.
3. A numerical assumption is verified when a second derivation sharing none of its premises reproduces its result. Plausibility is not verification.
4. Unit tests written by the author of a defective function, in the same session, examine internal consistency rather than correctness. Real data exposed what the tests could not.
5. Loan-to-value describes a position; capacity utilization is what the protocol enforces. The two differ by the collateral factors, and only the second reaches 1.0 at liquidation.
6. Collateral and debt held in assets of differing volatility create directional risk that no leverage measure discloses. This feature originated in observation of a live position rather than in the literature.
7. Performance work requires a failing test written beforehand and a correctness test maintained throughout. Speed obtained at the expense of accuracy is a regression.

## Exercises

1. A wallet supplies wrapped ether and borrows USD Coin, at a capacity utilization of 0.73. In which direction must the price of ether move to liquidate this position? Compare with the wallet examined in §2.7 and state which of the two a conventional leverage measure would misrepresent more severely.
2. The scaling derivation in §2.3 assumes protocol tokens carry eight decimals. Locate that assumption within the exchange-rate scaling and determine what would occur were a market to deploy with a different value.
3. Design a verification for the *collateral factor* alone, independent of the total-liquidity check performed in §2.4. What second derivation is available?
4. §2.9 distinguishes assumptions that fail loudly from assumptions that fail silently. Enumerate three further assumptions embedded in the client as described, and classify each.
5. Achutha et al. (2026) report their loss-severity model as trained upon 139 wallets. Locate the passage in which they disclose this and consider what the disclosure indicates concerning the confidence warranted by that stage of their result.

## References

Achutha, M., Hegde, B. R., & Das, B. (2026). Transaction graph-based predictive hurdle model for credit scoring in DeFi lending protocols. *International Journal of Data Science and Analytics, 22*, 124. https://doi.org/10.1007/s41060-026-01097-7

Basel Committee on Banking Supervision. (2006). *International convergence of capital measurement and capital standards: A revised framework, comprehensive version.* Bank for International Settlements.

Compound Labs. (n.d.). *Compound v2 documentation: Comptroller.* https://docs.compound.finance/v2/comptroller/

Consumer Financial Protection Bureau. (2022). *Circular 2022-03: Adverse action notification requirements in connection with credit decisions based on complex algorithms.* 87 Fed. Reg. 35864.

Moonwell. (n.d.). *Protocol information: Contracts.* https://docs.moonwell.fi/moonwell/protocol-information/contracts
