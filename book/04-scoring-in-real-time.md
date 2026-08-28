\newpage

# Chapter 4 — Scoring in Real Time

> **Objectives**
>
> Upon completion of this chapter, the reader will be able to:
>
> 1. State precisely what a solvency-triage service may claim about a wallet, and what it may not, absent a trained model
> 2. Distinguish a compliance control from a risk feature, and explain why sanctions screening must fail closed rather than fail open
> 3. Identify a feature that reports a falsely safe default when its inputs are incomplete, and correct it to report the unknown honestly
> 4. Write a test that detects drift between a documented capability and the code actually producing it
> 5. Explain why a hardcoded test fixture is a liability that decays, using the reference wallet this project's own latency test lost

## 4.1 The service this chapter almost shipped

Before there was a `BaseRPCClient`, before there was a verified scaling constant, before a single wallet had been read from the chain, this project had an HTTP endpoint that returned a credit score.

```python
@app.route('/model-version', methods=['GET'])
def model_version():
    return jsonify({
        'model_version': '1.0.0',
        'validation_auc_roc': 0.8658
    }), 200

@app.route('/score/<wallet_address>', methods=['GET'])
def score_wallet(wallet_address: str):
    if not wallet_address.startswith('0x') or len(wallet_address) != 42:
        return jsonify({'error': 'Invalid wallet address'}), 400

    return jsonify({
        'wallet': wallet_address,
        'pd': 0.35,
        'lgd': 0.28,
        'ead': 5000.0,
        'credit_score': 0.72,
        'recommendation': 'monitor'
    }), 200
```

This is the entire scaffold the project began from, generated before Chapter 1's first line of client code existed. Every number in it is a literal constant. `pd`, `lgd`, and `ead` do not vary by wallet — every address, including one padded with zeros and never seen on any chain, receives probability of default 0.35, loss given default 0.28, exposure at default $5,000.00, and the identical recommendation: *monitor*. The `validation_auc_roc` of 0.8658, sitting beside a `model_version` of `1.0.0`, is not the output of a validation run. Nothing had been trained, on nothing had it been validated, and no version besides the number `1.0.0` had ever existed.

Nothing about the response format discloses any of this to a caller. A JSON object with the keys `pd`, `lgd`, `ead`, and `credit_score`, returned from an endpoint literally named `/score`, is indistinguishable — to a lender, a fund, or a caller building on top of it — from the output of a real model that had actually been fit to actual liquidation data. That is precisely the danger. A scaffold that returned an error, or an empty object, or a string reading "not yet implemented" would have been honest by omission. This scaffold was worse than honest by omission: it actively manufactured the appearance of a working model where none existed.

This is the concrete referent behind every abstract phrase this book has used about claims requiring sources. It is also the reason this project's `/score` endpoint no longer exists. It was not repaired, and it was not backed by a hastily-trained model to make the numbers real. It was deleted, and replaced with `/position` — an endpoint that returns only what has actually been measured, and says so in its own docstring before a single route is defined:

```python
"""
src/api/server.py - HTTP interface to SCORE.

SCOPE: this service computes point-in-time SOLVENCY features from live
on-chain position data. It does NOT estimate probability of default,
loss given default, or any modelled quantity. No model has been trained.
Endpoints report only what is measured.
"""
```

This chapter is the account of building the service around that scope statement, and of everything that scope statement turned out to require in order to remain true under load, under a stale compliance list, and under incomplete data.

## 4.2 What may be claimed, stated as a boundary

Chapter 1 closed with the Basel decomposition — Expected Loss = PD × LGD × EAD — as the spine of everything the project is working toward. It is worth restating exactly which term of that decomposition this stage actually computes, because the scaffold in §4.1 is a warning about exactly this kind of conflation.

`extract_features` computes exposure — `exposure_usd`, the outstanding debt, which is EAD — together with a set of point-in-time solvency measurements built to support it: `ltv`, `capacity_used`, `headroom`, `debt_rise_to_liquidation`, `volatility_mismatch`, `is_underwater`. None of these is probability of default. None is loss given default. `features.py`'s own module docstring states the boundary directly: these features "describe solvency: where a wallet stands right now. They say nothing about propensity — whether this borrower behaves in ways that precede liquidation — which requires event history and is a later stage."

The `/capabilities` endpoint makes that same boundary a queryable fact rather than a line of documentation a caller might never read:

```python
"not_implemented": {
    "probability_of_default": "Requires liquidation labels over a "
                              "label period. Not yet extracted.",
    "loss_given_default": "Requires realised liquidation severity. "
                          "Not yet extracted.",
    "behavioural_history": "Requires event-log extraction (Borrow, "
                           "Repay, LiquidateBorrow). Not yet built.",
    "trained_model": "No model has been trained. No accuracy figures "
                     "are claimed.",
}
```

Each entry names *why* the capability is absent, not merely that it is. A caller who queries `/capabilities` learns not just that no PD exists, but that PD specifically requires liquidation labels over a defined label period, and that extracting those labels is a distinct, not-yet-completed piece of work — the same infrastructure constraint recorded in this project's own build log. An empty or vague reason would itself be a small version of the scaffold's failure: a claim of transparency that discloses nothing a caller could act on. A test enforces the standard directly — every reason string must be non-trivial, checked at the level of "does this string actually say something," not merely "does this key exist."

Every `/position` response repeats the boundary a third time, in the response itself rather than in a separate endpoint a caller has to think to check:

```
"disclaimer": "Point-in-time solvency only. Not a credit score. ..."
```

Three redundant statements of the same limit — module docstring, `/capabilities`, and every individual response — is not excess caution. It is the direct, structural answer to what the scaffold in §4.1 got wrong: a claim stated once, in a place a caller can miss, is a claim that will eventually be missed.

## 4.3 A test that watches for drift, not just correctness

Chapter 2 established a general principle: an assumption is verified when a second derivation, sharing none of its premises, reproduces its result. §4.2's redundancy solves the problem of a caller failing to notice a stated boundary. It does not solve a quieter version of the same problem: a boundary stated correctly today that silently stops being true as the code around it changes.

Concretely: `CreditFeatures` could grow a new field next month, and nothing prevents a developer from forgetting to add it to `/capabilities`'s `implemented` list, at which point the endpoint understates what the service actually computes — a smaller, subtler cousin of the scaffold's problem, an unearned *absence* of a claim rather than an unearned presence of one, but still documentation drifting from code. The reverse is equally possible: a field removed from `CreditFeatures` without being removed from `/capabilities`, leaving a claimed capability the code no longer produces at all.

The test written against this is a direct application of Chapter 2's maxim, at the level of an API contract rather than a numerical constant:

```python
def test_capabilities_implemented_matches_actual_feature_set(client):
    """Regression guard for the exact defect this project keeps
    re-encountering: a doc/API claim drifting from what the code actually
    computes. Every field CreditFeatures.to_dict() produces must be
    listed as implemented, and nothing listed that it doesn't produce -
    both directions of drift are checked, not just additions."""
    real_feature_keys = set(extract_features(WalletPosition(
        wallet_address="0x" + "aa" * 20, block_number=1,
    )).to_dict().keys())

    body = client.get("/capabilities").get_json()
    listed = set(body["implemented"]["point_in_time_solvency"])

    assert listed == real_feature_keys
```

Two routes to the same set of names — one derived by actually calling `extract_features` on a synthetic empty wallet and reading its output keys, the other read from the live `/capabilities` response — are compared for exact equality, in both directions. Neither route trusts the other. This is not a test that some particular capability is documented; it is a test that the *documentation and the code cannot drift apart without the test suite noticing*, which is a categorically stronger guarantee, obtained the same way Chapter 2's scaling verification was: not by inspecting one number and judging it plausible, but by deriving the same fact twice, independently, and refusing to proceed if the two derivations disagree.

## 4.4 A second boundary: compliance, not risk

`/capabilities` draws one boundary between measured solvency and unmodelled credit risk. A second, unrelated boundary runs through the same endpoint: between a risk signal and a legal control.

SCORE screens every address `/position` is asked about against the U.S. Treasury's Office of Foreign Assets Control Specially Designated Nationals list, because OFAC sanctions apply to U.S. persons on a strict-liability basis regardless of a service's regulatory classification (see `COMPLIANCE.md`; the money-transmitter analysis there turns on 31 C.F.R. § 1010.100(ff)(5), which SCORE's read-only, non-custodial design is built to fall outside of — a separate question from sanctions exposure, which attaches independently). `/capabilities` lists this screening under its own `compliance` category, deliberately kept apart from `point_in_time_solvency`, with a test enforcing the separation directly: a feature describes risk; a sanctions match is not a risk signal to be weighed against other risk signals, and folding the two lists together would imply otherwise.

The list itself is a documented compromise rather than the authoritative source. OFAC's own `sdn_advanced.xml` runs to roughly 120 megabytes and is not parsed directly; this project instead fetches a maintained mirror — the 0xB10C `ofac-sanctioned-digital-currency-addresses` project, which extracts cryptocurrency addresses from OFAC's XML nightly via GitHub Actions (0xB10C, n.d.). The trade explicitly accepted: a well-maintained, testable, dependency-light source, one derivation removed from the government's own file, disclosed as such in the module's own docstring — "a strong default, not the last word" — rather than presented with more authority than it has earned.

**Screening fails closed.** If the mirrored list cannot be freshly verified, `/position` returns 503 rather than a result:

```python
except StaleListError as exc:
    return jsonify({
        "error": "Sanctions screening unavailable",
        "detail": "The OFAC list could not be freshly verified, so this "
                  "request cannot be completed. This is a deliberate "
                  "fail-closed behaviour.",
    }), 503
```

The alternative — proceeding without screening and silently returning a position — would produce a response *indistinguishable from a genuinely clean screening result*. A caller cannot tell "verified clean" from "not actually checked" by looking at a 200 response alone; the only way to make the distinction visible is to refuse to produce the 200 at all when verification failed. This is the same reasoning Chapter 1 applied to `getAccountLiquidity`'s mutual exclusivity and Chapter 2 applied to a scaling assumption: a failure that announces itself loudly is vastly preferable to one that looks identical to success.

**A sanctioned match is surfaced, not hidden.** A sanctioned address is still read and returned — `is_sanctioned: true` sits alongside the position, rather than the request being silently blocked. The distinction matters: flagging an address for risk purposes is permitted; SCORE does not adjudicate what a caller does with the flag. What is not permitted is a screening gap masquerading as a clean result, which is the one failure mode the fail-closed design exists specifically to prevent.

## 4.5 The freshness check that only ran once

The fail-closed design in §4.4 contained an assumption that held on first inspection and failed under the exact condition it was built for.

`SanctionsScreener` is constructed once and held as a module-level singleton for the life of the server process — the ordinary, sensible pattern for a component that fetches a list over the network and should not refetch it on every request. The freshness check, however, was originally written to run only inside `ensure_list()`, the method responsible for loading the list in the first place:

```python
def screen(self, address: str) -> ScreeningResult:
    if self._addresses is None:
        self.ensure_list()
    ...
```

The defect is not visible in this fragment by inspection alone, which is precisely the category of defect Chapter 2 §2.9 flagged as the dangerous one. `self._addresses is None` is true exactly once — at the first request a freshly started server handles. Every subsequent request finds `self._addresses` already populated and skips `ensure_list()` entirely, which means it skips the freshness check entirely. A list fetched at server startup, verified fresh at that moment, is treated as permanently fresh for the remaining lifetime of the process — hours, days, however long the server runs — with no further check ever performed. The `max_age_hours` ceiling this module exists to enforce would stop applying after the very first request, silently, with nothing in the response format ever indicating that screening had quietly stopped being real screening.

The corrective, confirmed in the current source, checks freshness on every call rather than only at load time:

```python
def screen(self, address: str) -> ScreeningResult:
    """
    Freshness is checked on EVERY call, not only when the list is first
    loaded. A screener is typically constructed once and reused for the
    life of a server process, so "loaded" and "fresh" are not the same
    fact once any time has passed - re-checking only at load time would
    let the ceiling stop applying after the first request.
    """
    if self._addresses is None or self._age_hours() > self.max_age_hours:
        self.ensure_list()
    ...
```

The regression test for this reuses a single `SanctionsScreener` instance and ages it artificially past the freshness ceiling between calls — the specific shape a long-lived Flask process singleton takes, rather than a fresh instance per test, which would never have exercised the bug at all. This is worth sitting with as its own instance of Chapter 2's general lesson: the assumption "freshness is checked" was not false when written. It was true at exactly one moment in the object's lifetime and silently stopped being true at every moment after, and nothing about the code's shape announced the difference.

## 4.6 Reporting "unknown" instead of a falsely safe number

A related failure mode surfaced in `extract_features` itself, and it concerns what a feature should report when its inputs are incomplete rather than merely absent.

Two circumstances can leave `extract_features` without a trustworthy weighted-collateral figure. First, a market can hold real, nonzero collateral while its `collateral_factor` fails to decode — a reverted `markets()` call, tolerated because the client's batched read allows individual calls within the batch to fail without aborting the whole request. Second, a wallet can supply collateral to a market without having called `enterMarkets` on it, in which case Moonwell itself does not count that collateral toward borrowing capacity, regardless of how much sits there.

The original formula treated both cases the same way an absent value is conventionally treated in arithmetic — as zero:

```python
capacity_used = debt / weighted if weighted > 0 else 0.0
```

Read that default in context. `weighted <= 0` here does not mean the wallet holds no collateral; the wallet's raw collateral may be substantial. It means *this client could not establish how much of that collateral counts*. Reporting `capacity_used = 0.0` in that state does not report "unknown" — it reports "fully safe, zero leverage," which is the most reassuring value the field can take, applied precisely when the underlying data is least trustworthy. A heavily leveraged wallet with one undecoded market would appear, through this formula, indistinguishable from a wallet holding no debt at all.

The fix does not attempt to compute a better number. It reports that no number can currently be trusted:

```python
degraded = any(m.collateral_usd > 0 and m.collateral_factor is None
               for m in position.markets)

if degraded or (debt > 0 and weighted <= 0):
    capacity_used = None
    headroom = None
```

`capacity_used`, `headroom`, and `debt_rise_to_liquidation` all report `None` under these conditions, and `CreditFeatures.degraded` is set so a caller can see *why* — rather than silently receiving 0.0 and never learning that the figure meant "safe" only because the client had given up trying to compute it honestly. Note what remains unaffected: `is_underwater` is untouched by this change, because on Moonwell it is read directly from the Comptroller's own `getAccountLiquidity` call rather than derived from this client's weighting — the one figure in `CreditFeatures` still carrying the independent-verification strength Chapter 2 established, and the one Chapter 3 flagged as *not* carrying that same strength once the same field is populated for a Morpho-sourced position instead.

The through-line connecting this section, §4.5, and Chapter 2's leverage-feature defect is the same in each case: the dangerous default is never the value that is obviously wrong. It is the value that looks like a normal, safe answer, in the specific circumstance where the honest answer is that the system does not currently know.

## 4.7 The same latency discipline, now live, and a fixture that decayed

`/position` inherits Chapter 2's batching discipline directly — one Multicall3 round trip per request, the same client, the same guarantee that every value in a response originates from a single block. What changes at this stage is that the guarantee is now enforced against a running service under a live-gated test, rather than checked once during development:

```
p50:    156 ms
p95:    173 ms
target: 500 ms
```

A detail in that test's own history is worth reporting on its own terms, because it is a lesson about test maintenance rather than about the client. The latency test's reference wallet — a real address confirmed to hold an open Moonwell position, hardcoded so the test has something live to measure against — was originally `0xAA503ae3...`, the same wallet Chapter 2 §2.4 used for its independent-derivation verification. By the time this stage of work began, that wallet had closed its position out entirely. The test did not fail loudly; it degraded quietly, into a comparison against a wallet with nothing left to compare, and a live correctness check against an empty position is not a check of anything.

The replacement wallet's own code comment states the lesson plainly rather than merely fixing the symptom:

```python
# A wallet with an active Moonwell position, confirmed 2026-08-22.
# ...The previous reference wallet (0xAA503ae3...) closed its position
# entirely since it was chosen on 2026-08-15, which is exactly why this
# comment carries a confirmation date: a hardcoded wallet is a liability
# that decays, not a one-time fix. If this one closes out too, use
# scripts/find_borrowers.py to find a live replacement, then verify with
# `pytest tests/test_latency.py -m live -s` before trusting the new one.
```

A hardcoded address confirmed once is a fact about the chain at the moment it was confirmed, not a permanent fact about the chain. This is a smaller-scale version of a pattern this book has now reported at three different scales: Chapter 3's staleness log guarding against un-accrued interest, §4.5's freshness check guarding against a stale sanctions list, and here, a dated code comment guarding against a test fixture whose truth quietly expires. Each is the same discipline — state *when* a fact was confirmed, not only *that* it was — applied to whatever kind of decay the specific fact is subject to.

## 4.8 What this stage did, and did not, prove

State the result at the scope it actually covers.

This stage built a live HTTP service that reports measured, point-in-time solvency features for any wallet on Moonwell, within the latency target Phase 0 set, screened against a sanctions list that fails closed rather than silently passing a gap through as a clean result, and that states its own limits — three times, redundantly, on purpose — rather than once in documentation a caller might not read. Every one of those properties is backed by a test that does not merely assert current behavior, but would fail if that property quietly stopped holding: drift between `/capabilities` and the actual feature set, a freshness check that stops running, a falsely safe default reappearing, a fixture that decays unnoticed.

It did not produce a credit score, and nothing in this chapter should be read as implying it came close. The `/score` endpoint this project began with is gone, not repaired. No probability of default exists. No loss given default exists. No behavioral history has been extracted. Building the machinery that reports honestly on those absences turned out to require as much deliberate engineering as reading the chain did in Chapter 1 — arguably more, since the machinery in this chapter exists entirely to prevent a specific, tempting shortcut: returning something that looks like an answer before the work required to earn one has actually been done.

## Summary

1. This project's original scaffold returned a fabricated `validation_auc_roc` and a fabricated `pd`/`lgd`/`ead`/`credit_score` for every wallet, indistinguishable in format from real model output. It was deleted, not repaired, and replaced with an endpoint reporting only measured features.
2. `/capabilities` states what is and is not implemented, with a required, non-trivial reason for every absence — a queryable fact, not a line of documentation a caller might miss.
3. A test comparing `/capabilities`'s claimed feature list against `extract_features`'s actual output keys, in both directions, catches documentation drifting from code before a caller ever notices — Chapter 2's independent-derivation principle applied to an API contract.
4. Sanctions screening is a legal control, not a risk feature, and is listed separately from both. It fails closed: an unverifiable list yields 503, never a silently ungated result. A sanctioned address is still returned, flagged rather than hidden.
5. A freshness check written to run only at first load silently stopped applying after a server's first request, because the "list is loaded" condition it depended on stayed true forever after. It now re-checks on every call.
6. A collateral factor that fails to decode, or collateral supplied but never entered into a market, previously defaulted `capacity_used` to 0.0 — the most reassuring value available, reported exactly when the underlying data was least trustworthy. It now reports `None`, with `degraded` stating why.
7. A hardcoded reference wallet used by the live latency test closed its position between when it was chosen and when it was next relied upon. The fix carries a confirmation date and an explicit procedure for finding the next replacement, because a live fact confirmed once is not a permanent fact.

## Exercises

1. §4.1 argues that a scaffold returning a plausible-looking fabricated score is worse than one returning an explicit error. Construct the counter-argument a reasonable engineer might have made for keeping the scaffold's shape (same keys, placeholder values) during early development, and state what would have to be true for that argument to be safe.
2. §4.3's drift test compares two independently derived sets of feature names. Design an equivalent test for `/capabilities`'s `not_implemented` section: what would "drift" mean there, and how would you detect it without hardcoding the current list of gaps?
3. §4.5's freshness bug required a test that reused one `SanctionsScreener` instance and aged it artificially. Explain why a test constructing a fresh instance per assertion — the more common testing pattern — would never have caught this defect, even if it checked the exact same assertions.
4. §4.6 distinguishes an *absent* value from an *unknown* one, and argues `None` is the honest report where 0.0 was not. Identify one other field in `CreditFeatures` where a similar ambiguity could arise, and state what circumstance would force it.
5. Compare the sanctions freshness bug (§4.5) and the reference-wallet decay (§4.7). Both are facts that were true when first established and became false silently over time. What distinguishes a fact whose staleness a system can detect and refuse to act on, from a fact whose staleness only a dated comment and human judgment can catch?

## References

0xB10C. (n.d.). *ofac-sanctioned-digital-currency-addresses* [GitHub repository]. https://github.com/0xB10C/ofac-sanctioned-digital-currency-addresses

Consumer Financial Protection Bureau. (2022). *Circular 2022-03: Adverse action notification requirements in connection with credit decisions based on complex algorithms.* 87 Fed. Reg. 35864.

U.S. Department of the Treasury, Financial Crimes Enforcement Network. *Definition of money services business.* 31 C.F.R. § 1010.100(ff)(5).
