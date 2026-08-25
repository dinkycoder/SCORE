\newpage

# Chapter 3 — A Second Protocol

> **Objectives**
>
> Upon completion of this chapter, the reader will be able to:
>
> 1. Explain why an isolated-market lending protocol has no account-level solvency check spanning positions, and what identifies a "market" in place of a token
> 2. Convert a Morpho Blue borrow-shares balance to its underlying asset amount, and state which direction rounding is required to favor
> 3. Distinguish a verification claim inherited from a protocol's own on-chain check from one reconstructed by the reader itself
> 4. Recognize when a feature computed without error nonetheless fails to measure what its name promises
> 5. Conduct a one-time external cross-check against an independent source, and state plainly what it did and did not settle

## 3.1 What the portability claim was actually asking

Chapters 1 and 2 built a client against Moonwell, a fork of Compound V2. Everything in those chapters — the Comptroller, `getAccountLiquidity`, the collateral factor, the 10^(36−*d*) oracle scaling — is Compound-family vocabulary. It is also, by the middle of 2026, vocabulary describing a contracting market: Moonwell's total value locked had fallen from a mid-2026 peak near $374 million to roughly $60 million, an 84 percent drawdown, while its liquidation history over that same period remained fully banked and usable for the reasons already given. A credit-scoring method that only works on the protocol it was written against is not a method. It is a fixture.

The claim under test in this chapter, accordingly, is narrower than "SCORE works on Morpho." It is: *the features Chapter 2 verified — capacity utilization, headroom, the distance to liquidation, the volatility-mismatch flag — describe a borrower's position, not a Comptroller's bookkeeping, and should therefore survive a lending protocol built on a genuinely different accounting model.* Morpho is the protocol chosen to test that claim, for a reason stated plainly rather than left to infer: at the time of writing it was the largest lending protocol on Base and, unlike Moonwell and Aave, growing rather than contracting. A demonstration that only runs on a shrinking market is a weak one, regardless of how sound the underlying method is.

The honest framing is that this is a cost accepted for a reason, not a free upgrade. Moonwell's architecture is close enough to the reference paper's own dataset that the existing client needed only to be read correctly. Morpho's is not close. It required rebuilding the read path from the interface up, and — as this chapter reports — it required discovering, in the process, exactly which of Chapter 2's verified guarantees transfer and which quietly do not.

## 3.2 A pool without a Comptroller

Compound-family protocols share one pool per asset and one Comptroller governing every market a wallet has entered. A wallet's solvency is a single account-level question, answered by a single function call, because the protocol maintains an account-level view on purpose.

Morpho Blue maintains no such view, by design rather than by omission. It is a permissionless, isolated-market protocol: anyone may create a market, a market is identified by the tuple (loan token, collateral token, oracle, interest-rate model, liquidation loan-to-value), and a wallet's position exists per market, not per account. There is no `getAllMarkets`, because markets are not enumerated centrally — they are created, individually, by whoever wants one. There is no `getAccountLiquidity` spanning a wallet's activity, because "a wallet's activity" is not a concept the protocol tracks; a wallet supplying collateral to three different markets holds three unrelated positions, each solvent or not entirely on its own terms.

This is a genuine trade against the convenience Chapter 1 relied on. It is also the point of the architecture: isolation means a failure in one market — a bad oracle, a manipulable collateral asset, an undercollateralized parameter choice — cannot propagate into every other market sharing the same pool, the way it can under Compound's Comptroller model. Achutha et al. (2026) built and verified their method against the shared-pool case. Whether the same features carry the same meaning against the isolated case was, until this stage, untested.

The practical consequence for a reader of a market's identity: a Morpho market is not a token address, the way an mToken is on Moonwell. It is a 32-byte identifier — `marketId` — computed as a hash of the five parameters above. Two markets pairing the identical collateral and loan token but different oracles are different markets, with independently set risk parameters and no shared liquidity. Naming a market by its constituent tokens, the way one might say "the ETH market," is imprecise in a way it was not on Moonwell; precision requires the `marketId` itself.

## 3.3 Confirming a market off the chain, not off a webpage

The first task was not reading a position. It was deciding which market to read.

`app.morpho.org`'s market-listing pages are a JavaScript single-page application; a static HTTP fetch of the page returns an application shell, not market data. This project's working discipline, established in Chapter 2 by way of a fabricated contract address that was thirty-one of forty hexadecimal characters correct, was already "documentation describes intent; deployed contracts exhibit behavior." A rendered webpage sits somewhere between the two — closer to documentation than to the chain itself — and was treated accordingly: not trusted as a source for a market identifier that would be hardcoded into a client and relied upon for every subsequent read.

Three candidate markets were queried directly against Morpho Blue's own `idToMarketParams` function on Base, rather than read off any page:

| Market | LLTV | Supply | Borrow |
|---|---|---|---|
| **cbBTC/USDC (chosen)** | 0.86 | ~1,492,288,756 USDC | ~1,317,523,521 USDC |
| cbBTC/WETH | 0.915 | ~164 WETH | ~145.6 WETH |
| wstETH/USDC | 0.86 | ~50 USDC | ~45 USDC |

cbBTC/USDC dwarfed the other two by roughly seven orders of magnitude in this snapshot and, more to the point of §3.1, carries the same shape as Moonwell's dominant lending pattern in this project: volatile collateral against stable debt. It was chosen for both reasons — scale, and comparability to what Chapter 2 already verified.

The core contract's own address was confirmed the same way: not copied from a page, but checked with `eth_getCode` against Base mainnet, which returned 15,623 bytes of deployed bytecode at the address Morpho's documentation lists (Morpho Labs, n.d.-a). A non-empty result at the expected address is a considerably stronger claim than "a page said so." It is a claim about what is actually deployed.

The `marketId`, LLTV, and the loan/collateral/oracle/IRM addresses composing it are the only constants this stage hardcodes. Supply and borrow figures in the table above are a snapshot recorded as the evidence for the selection, not values relied upon by the client — they move, and the market's identifying tuple does not.

## 3.4 Debt is a share, not a balance

Chapter 2's scaling derivation established that Moonwell reports balances directly: an mToken balance, an exchange rate, a borrow balance already in the underlying asset's units. Morpho Blue reports something one layer more abstract. `position(marketId, wallet)` returns `supplyShares`, `borrowShares`, and `collateral` — and only the last of these is an asset amount. The first two are shares in a pool, and a share is not an asset amount until it is converted, using the market's current totals.

The conversion is Morpho Blue's own `SharesMathLib.toAssetsUp`, and it is worth working through, because the two design choices inside it — rounding *up*, and two constants called *virtual shares* and *virtual assets* — are not incidental. Both exist to close specific manipulation paths, confirmed against Morpho's own protocol documentation (Morpho Labs, n.d.-b) rather than assumed from the function's name.

```
assets = ceil( shares × (total_assets + VIRTUAL_ASSETS)
               ────────────────────────────────────────
                    total_shares + VIRTUAL_SHARES )
```

with `VIRTUAL_ASSETS = 1` and `VIRTUAL_SHARES = 10^6`.

**Why ceiling, not floor.** A borrower's debt is a liability the protocol is owed. Rounding a debt conversion *down* — the arithmetically "natural" choice, and the one Python's integer division performs by default — would understate every borrower's obligation by up to one unit of rounding error, in the borrower's favor, on every read. That is not a rounding error the protocol can absorb silently; compounded across every position on the market, it is uncollected debt. Rounding up instead guarantees the reported obligation is never smaller than what is actually owed. This mirrors a principle Chapter 1 already established for a different mechanism — the protocol delegates enforcement to whichever direction of error costs it nothing — applied here to arithmetic rather than to liquidation incentives.

**Why virtual shares and virtual assets.** Absent them, a market's very first depositor could supply a trivial amount, mint the entire share supply against it, and then donate a large balance directly to the market's holdings — inflating the assets-per-share ratio and letting that first depositor extract value from every subsequent depositor's shares. Adding a constant, non-zero floor to both the assets and shares totals before any deposit exists denies the attacker the near-zero denominator the attack requires. It is a small addition — one part in a million on `total_shares`, one whole unit on `total_assets` — and its effect vanishes once a market has any meaningful scale, which cbBTC/USDC, with over a billion dollars of USDC supplied, plainly has.

Both properties needed to be confirmed against the interface itself, not assumed by resemblance to a Moonwell-style balance — this is the same discipline Chapter 2 applied to the 10^(36−*d*) scaling constant, extended to a protocol where the object being read is one abstraction layer further from the number a reader actually wants.

One further limitation is stated here rather than left implicit. `market(marketId)` — the call supplying `total_borrow_assets` and `total_borrow_shares` for the conversion above — is a pure `eth_call`. Morpho Blue only runs its interest-accrual step inside state-changing calls, never on a view read. The totals returned therefore reflect whatever was last written as of that market's `lastUpdate` timestamp, not interest accrued up to the current block. On a market with cbBTC/USDC's activity, that gap is typically seconds — but it is a gap bounded by observed behavior, not guaranteed by any interface contract, and it is a second, independent source of understatement beyond the rounding direction `toAssetsUp` already corrects for. The client logs the gap on every read (`lastUpdate` against the current block's own timestamp, batched into the same call described in §3.9) precisely so the staleness is visible rather than silently absorbed into the reported figure.

## 3.5 The reuse decision

Chapter 1 and Chapter 2 built two data structures — `WalletPosition`, a wallet's full position across every market it holds, and `MarketPosition`, one market within it — and a function, `extract_features`, that turns the first into the credit-relevant figures this book has been reporting since: capacity utilization, headroom, the distance to liquidation, the volatility-mismatch flag. All three were written and verified entirely against Moonwell.

The decision made for this stage was to change none of them. `MorphoRPCClient` decodes cbBTC/USDC's raw shares and collateral, converts them by the method in §3.4, and packs the result into the *same* `WalletPosition`/`MarketPosition` shapes the Moonwell client already produces — a wallet holding one Morpho position looks, to `extract_features`, exactly like a wallet holding one Moonwell market position. `extract_features` required zero code changes to accept it.

This is not merely convenient. It is a real test of the claim in §3.1, arguably a stronger one than writing Morpho-specific feature logic would have been: if the *same, unmodified* function — the one Chapter 2 verified against Moonwell to a ratio of 1.000000 — produces sensible output from a structurally different protocol's data, the features it computes are doing what a reader would hope they do, which is describing collateral against debt in general, rather than describing a Comptroller's particular bookkeeping. Writing new feature code for Morpho would have answered a narrower and less interesting question: whether *new* code could be made to work, which nothing in Chapters 1 or 2 was ever in doubt about.

"Zero code changes" is a claim about the function's *behavior*, however, not a claim that every field it produces retains its Moonwell-era meaning. The two are different, and the next section is where they come apart.

## 3.6 Where the reuse breaks quietly

`capacity_used`, `headroom`, `debt_rise_to_liquidation`, `degraded`, and `is_underwater` reuse cleanly — each depends on weighted collateral against debt, which a single-`MarketPosition` representation with `collateral_factor` set to the market's LLTV computes correctly, for the same reason it computes correctly on Moonwell. Two fields do not, and the sharper of the two is worth sitting with.

`volatility_mismatch` is Chapter 2's own contribution — the feature built, in §2.7, from noticing that a wallet supplying a stable asset and borrowing a volatile one is liquidated by a price *rise*, which no leverage ratio alone discloses. `extract_features` detects it by comparing the set of ticker symbols carrying collateral against the set carrying debt; a mismatch between the two sets is the signal. On Moonwell this works because each market — each mToken — is its own `MarketPosition`, so collateral in one asset and debt in another naturally land under two different symbols.

Morpho Blue's cbBTC/USDC market packs collateral and debt into a *single* market, and this reader packs that single market into a *single* `MarketPosition` carrying one symbol, `"cbBTC"`. Collateral lands under `"cbBTC"`. Debt — reported, per §3.4, in the loan token, USDC — also lands under `"cbBTC"`, because there is only the one `MarketPosition` to put it in. The two sets `extract_features` compares are therefore always the same one-element set, on every Morpho position this client will ever produce, and `volatility_mismatch` reports `False` unconditionally.

State plainly what that means: cbBTC/USDC is a volatile-collateral, stable-debt market by construction — bitcoin against a dollar-pegged asset — which is the textbook case the feature exists to catch. It is caught for every Moonwell wallet holding the equivalent shape. It is caught for none of the Morpho wallets this client reads, not because the underlying risk differs, but because the representation chosen to make reuse possible in §3.5 happens to erase the one signal this particular feature depends on. A feature can compute without error and still fail to measure what its name promises, and this is that case, not a defect awaiting a patch — closing it would mean changing `extract_features` itself (out of scope; it is shared, verified, unmodified code) or splitting one Morpho position into two synthetic `MarketPosition`s to recover separate symbols, a larger design change this stage did not attempt.

`market_count` degrades more mildly, but the same way: it is 1 whenever this client finds a position and 0 otherwise, never anything a genuine concentration proxy would produce, because this client reads exactly one market by construction (§3.2's isolation, taken to its logical single-market scope here) regardless of how many other Morpho markets the same wallet might hold elsewhere.

Neither limitation was caught by the individual pieces of work that built this stage. Five separate task-level reviews passed over the code that would eventually decode into a single, symbol-collapsed `MarketPosition`, and none of them surfaced `volatility_mismatch`'s behavior, for a reason with an uncomfortable resemblance to Chapter 2 §2.5's leverage-feature defect: no test in any of those five reviews actually called `extract_features` on a Morpho-sourced `WalletPosition` and inspected the result. What finally surfaced it was a sixth pass — a whole-branch review conducted after all five tasks were nominally complete, examining the integration rather than any individual piece — writing exactly that test and reading what came back. The corrective is now a permanent, explicit assertion rather than a silent gap: `test_extract_features_on_morpho_position` calls the real function on real Morpho-shaped data and asserts `volatility_mismatch is False`, not as an oversight preserved by accident, but as the documented, intentional record of a known limitation.

## 3.7 A protocol with nothing to check against

Chapter 2's central verification — computing weighted collateral minus debt two ways and confirming the results agree to six decimal places — worked because Moonwell's Comptroller exposes `getAccountLiquidity` as a second, independently computed figure to check against. That second figure is what made independent derivation possible at all: two routes sharing no assumptions, arriving at one number.

Morpho Blue's public interface offers no equivalent. `position()` returns raw shares and collateral — the same category of unprocessed data `getAccountSnapshot` supplies on Moonwell — but nothing corresponding to the Comptroller's own health computation. Health is checked internally, inside the contract, at the moment of a borrow or a withdrawal; it is never exposed as a public view a reader can call.

`WalletPosition.reported_liquidity_usd` and `reported_shortfall_usd` are populated for Morpho positions regardless — from this client's *own* derived `weighted_collateral_usd − debt_usd`, the identical arithmetic `extract_features` performs internally. The alternative, leaving those fields at their zero default, was considered and rejected: a zeroed shortfall would make `is_underwater` report `False` unconditionally, for every wallet, healthy or not — the exact false-safety shape this project has already found and corrected twice in the Moonwell path (Chapter 2's own account of a leverage feature returning zero for every healthy wallet is one instance of the general pattern). Shipping that same shape of defect into a new protocol's very first integration would have repeated Chapter 2's lesson rather than applied it.

What results is correct behavior obtained by a strictly weaker verification claim than Moonwell's, and the distinction is not cosmetic. Moonwell's `is_underwater` is checked against a number the protocol itself computed, independently, in its own contract. Morpho's `is_underwater` is checked against a number this project computed, then duplicated into the slot where an independent check would otherwise sit. If this client's arithmetic contains an error, Moonwell's Comptroller would catch the discrepancy; Morpho's would not, because there is no second party in the comparison. This is stated here, in the module itself, and in the project's own build record, rather than left for a future reader of the source to discover unassisted — and it will remain true for as long as Morpho Blue's public interface offers no on-chain health view, which is to say it is not a gap a subsequent patch is expected to close.

## 3.8 The cross-check, and the mistake found inside it

Absent a protocol-side check, the strongest available substitute was an external one: comparing this client's output against a source that computed the same wallet's position independently, using code this project did not write.

Morpho maintains a public GraphQL API — `blue-api.morpho.org/graphql` — exposing a `marketPosition` query (Morpho Labs, n.d.-c). This client's live output was compared against that API's own figures for the same wallet, `0x04a9530da51Eb174153F150FfDF103B368c332E5`, and the same market, roughly forty seconds apart in wall time:

| Field | This client | `blue-api.morpho.org` | Difference |
|---|---|---|---|
| Collateral, raw cbBTC units | 9,257,470 | 9,257,470 | exact match |
| `collateral_usd` | $7,165.18 | $7,165.68 | 0.007% |
| `debt_usd` | $3,941.27 | $3,940.83 | 0.011% |
| Health factor (recomputed from the two rows above) | 1.563471 | 1.563753 | 0.018% |

The raw share count agreeing exactly, before any USD conversion enters the comparison, is meaningful on its own: it confirms `position()` is being decoded correctly, independent of any oracle or price arithmetic downstream.

The health-factor row required a correction worth reporting, because the correction is itself evidence of the discipline this book has argued for throughout rather than a detail to smooth over. The first draft of this table pasted `blue-api.morpho.org`'s own `healthFactor` field directly into the comparison, and that field happened to closely track this client's own weighted-collateral-over-debt ratio — producing a health-factor gap that looked like roughly 0.00002%, dramatically tighter than the collateral and debt figures sitting in the very same row. That was not a true measurement. It was an internal inconsistency: a field computed one way sitting next to figures computed another way, in a table that implied both had been derived identically. The figure shown above is recomputed directly from that same row's own `collateral_usd` and `debt_usd` columns — `collateral_usd × 0.86 ⁄ debt_usd` — for both sides, which is the comparison the table's own numbers actually support.

The sub-0.02 percent gaps that remain were investigated rather than waved past. Two candidate explanations were considered and both were ruled out, on arithmetic grounds rather than by assumption. Ordinary interest accrual across the roughly thirty-six seconds separating the two reads' timestamps — this client's own `lastUpdate` read as 1787518229, the API's state timestamp as 1787518193 — would require an implied annual percentage yield on the order of 9,800 percent to account for the 0.011 percent `debt_usd` gap on its own; no plausible rate on this market produces that. A single, uniform non-$1.00 USDC price applied by the API's oracle — this client assumes USDC is worth exactly $1.00, a documented simplification — was considered next, but the collateral gap and the debt gap move in *opposite* directions relative to this client's figures, and a single shared price factor applied uniformly to both would move them the same way. No third explanation was found and confirmed from the data available.

The gaps are accepted as within the tolerance the original design called for, and reported as unexplained rather than as resolved. This is the standard Chapter 2 set with an unfabricated address and a verified scaling constant, applied here to a case where the honest report, after genuine effort, is that a small discrepancy exists and its cause was not pinned down. It is also, deliberately, a one-time exercise rather than an automated test: no independent, automatable source exists for Morpho positions the way the Comptroller supplies one for Moonwell, so there is nothing here to wire into a CI pipeline the way Chapter 2's correctness test was.

## 3.9 Restoring the round trip

Chapter 2 established, and measured, that a single Multicall3 call — one round trip regardless of how many individual reads it batches — is the property that took Moonwell's scoring latency from a 1,683-millisecond p95 down to 173 milliseconds. `MorphoRPCClient` was built against that same discipline from the start: `getBlockNumber`, `position()`, `market()`, and the oracle's `price()` all batched into one `aggregate3` call.

A fix applied during this stage's review temporarily broke that property, in a way worth reporting precisely because of how it broke. Adding the staleness log described at the end of §3.4 — comparing `market().lastUpdate` against the current block's timestamp — required a block timestamp, and the change that added the logging fetched it with a follow-up `self.w3.eth.get_block(block_number)` call, executed *after* the batched read returned. The logging line itself was correct, and it was gated behind debug-level logging being enabled, but the fetch feeding it was not conditional on that gate — it ran unconditionally, on every call, silently reintroducing a second round trip into a client whose entire justification, established in Chapter 2, was having exactly one.

This was caught, and deliberately not fixed in the same pass that introduced it — parked, per this project's own review process, rather than looping a second immediate fix wave onto a review that had already closed. It was returned to and corrected directly afterward: the current block's timestamp is now obtained from Multicall3's own `getCurrentBlockTimestamp()` function, encoded into the *same* `aggregate3` batch as everything else, rather than a follow-up call. The staleness log now costs nothing beyond what the batch already paid for.

The fix was verified the way Chapter 2 verified its own optimization — not by re-reading the code and judging it plausible, but by instrumenting the actual HTTP traffic during a live call and counting requests. Before the fix, the call touched more raw requests than the batch alone required. After, `MorphoRPCClient`'s steady-state cost is three raw HTTP POSTs per logical `get_wallet_position` call — measured the same way, post-warmup, as `BaseRPCClient`'s own steady-state cost for its one logical call, and identical to it. The threefold multiplier is pre-existing overhead common to both clients' single-call pattern, from the `web3.py` library itself, not something this fix introduced or something either client's design controls. Morpho is, on this specific measure, at genuine parity with the already-verified Moonwell client — not a suppressed log line masquerading as one.

## 3.10 What this stage did, and did not, prove

State the result at the scope it was actually tested, no wider.

This stage confirms that `WalletPosition`, `MarketPosition`, and `extract_features` — verified in Chapters 1 and 2 against one Compound-family protocol — produce sensible, mostly-correct output when fed data from a structurally different, isolated-market protocol, without modification to any of the three. That is the portability claim from §3.1, and it held, for the specific market this stage targeted.

It also confirms, with equal weight, that "sensible, mostly-correct" is not "identical in every respect to Moonwell." `volatility_mismatch` is unconditionally `False` for every position this client will ever produce, for a structural reason rooted in how a single isolated market gets represented, not a bug awaiting correction. `is_underwater` is correct but verified only against this project's own arithmetic, not against an independent protocol-side check the way Moonwell's is. A one-time external cross-check found sub-0.02 percent gaps whose cause was investigated and not resolved.

None of what remains outstanding was in this stage's scope, and none of it is pretended to be finished. Market discovery beyond cbBTC/USDC, wiring this reader into the `/position` and `/capabilities` endpoints a live service would actually expose, and any write path carrying a Morpho-sourced position into `CreditScorer` are all untouched by the work this chapter describes — named here as what is left, not folded silently into a claim of completeness the work does not support.

## Summary

1. Morpho Blue is an isolated-market protocol: no shared pool, no Comptroller, no account-level solvency check spanning positions. A market is identified by a five-part tuple, not a token.
2. A market's identity was confirmed against the chain directly — `idToMarketParams` and `eth_getCode` — rather than trusted from a rendered webpage that does not serve market data to a static fetch.
3. Morpho reports debt as shares, not a balance. Converting requires `SharesMathLib.toAssetsUp`'s ceiling rounding, which guarantees a borrower's obligation is never understated, and virtual shares/assets, which close a first-depositor manipulation path.
4. `extract_features` required zero code changes to consume Morpho-sourced data — a stronger test of the underlying features' generality than writing Morpho-specific logic would have been.
5. `volatility_mismatch` reports `False` unconditionally for every Morpho position this client produces, a structural consequence of packing one market's collateral and debt into a single symbol, not a bug — and it defeats the feature on exactly the volatile-collateral/stable-debt shape it exists to catch.
6. Morpho Blue exposes no independent, protocol-side health check comparable to Moonwell's `getAccountLiquidity`. `is_underwater` is populated from this project's own derived arithmetic, a permanently weaker verification claim than Moonwell's, stated as such rather than left for a reader to discover.
7. A one-time cross-check against Morpho's own public API confirmed exact agreement on raw share counts and sub-0.02 percent gaps on USD figures, whose cause was investigated, partially ruled out, and not fully resolved — reported as such rather than as either a failure or a clean pass.
8. A logging change briefly reintroduced a second round trip into a client built for exactly one; it was caught, deliberately deferred rather than fixed mid-review, and corrected by batching the missing call into the same aggregate rather than removing the log.

## Exercises

1. §3.6 states that `volatility_mismatch` fails specifically because Morpho's collateral and debt share one `MarketPosition` symbol. Sketch the representation change that would let the existing comparison logic in `extract_features` detect the mismatch correctly, and identify what it would cost elsewhere in the pipeline.
2. Work the `toAssetsUp` formula in §3.4 by hand for `shares = 500`, `total_borrow_assets = 2,000,000`, `total_borrow_shares = 2,001,500`. Compute the result with and without the virtual-shares/virtual-assets offsets, and state whether the difference matters at this scale.
3. §3.7 states that Morpho's `is_underwater` carries a weaker verification claim than Moonwell's. Describe a concrete on-chain state — a specific relationship between collateral, debt, and price — that would cause this client's derived figure to disagree with the wallet's true health, undetected, given the interface Morpho Blue actually exposes.
4. §3.8 rules out two candidate explanations for the sub-0.02 percent cross-check gap using the direction each would move the collateral and debt figures. Propose a third candidate and state which direction it predicts for each figure.
5. Compare the fabricated contract address in Chapter 2 §2.9 with the corrected health-factor row in §3.8 of this chapter. Both are self-corrected errors reported in the text rather than removed from it. What does each error's *cause* reveal about the kind of mistake this project is most prone to making?

## References

Achutha, M., Hegde, B. R., & Das, B. (2026). Transaction graph-based predictive hurdle model for credit scoring in DeFi lending protocols. *International Journal of Data Science and Analytics, 22*, 124. https://doi.org/10.1007/s41060-026-01097-7

Morpho Labs. (n.d.-a). *Morpho documentation: Contract addresses.* https://docs.morpho.org/get-started/resources/addresses/

Morpho Labs. (n.d.-b). *Morpho Blue documentation.* https://docs.morpho.org

Morpho Labs. (n.d.-c). *Morpho API* [GraphQL API]. https://blue-api.morpho.org/graphql
