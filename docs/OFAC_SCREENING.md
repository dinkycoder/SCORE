# OFAC Screening

How SCORE screens wallet addresses against the OFAC Specially Designated
Nationals (SDN) list, and the limits of what that screening does.

> Not legal advice. Screening reduces one specific risk. It does not
> discharge SCORE's full legal obligations. See `COMPLIANCE.md`.

## Why

SCORE is not a money transmitter (it takes no custody, moves no value). But
OFAC sanctions apply to all US persons on a strict-liability basis regardless
of that status, and pseudonymity is not a defence — OFAC has listed specific
crypto wallet addresses on the SDN list since 2018. Because SCORE reads and
scores wallet addresses, it screens them.

## What the module does

`src/compliance/sanctions.py` exposes `SanctionsScreener` and a convenience
`is_sanctioned(address)`:

    from compliance.sanctions import SanctionsScreener

    screener = SanctionsScreener()
    result = screener.screen("0x...")
    if result.is_sanctioned:
        # handle per policy
        ...

`screen()` returns a `ScreeningResult` (`is_sanctioned`, `list_age_hours`,
`list_source`) that is truthy when sanctioned, so `if screener.screen(a): ...`
reads naturally.

## Two behaviours that matter

**It fails loud.** If no fresh list is available — stale cache past the age
ceiling, or no list at all — `screen()` raises (`StaleListError` /
`ListUnavailableError`) rather than returning `False`. A compliance check that
silently clears when it cannot verify is worse than none; it manufactures
false confidence. An empty fetched list is likewise refused, never treated as
"everyone is clear."

**It enforces freshness.** The list carries a fetch timestamp. Screening
against a cache older than `max_age_hours` (default 24) raises. Raise the
ceiling only with a documented reason.

## Data source and its limits

The authoritative source is OFAC's `sdn_advanced.xml` (~120 MB, treasury.gov).
This module does **not** parse that file directly. It fetches a derived,
maintained list: the 0xB10C `ofac-sanctioned-digital-currency-addresses`
project extracts crypto addresses from `sdn_advanced.xml` nightly (00:00 UTC)
via GitHub Actions and publishes per-asset lists. SCORE reads the ETH list.

Trade-off, stated plainly:

- **Strength:** well-maintained, correctly parsed, refreshed daily, and
  testable in ordinary CI.
- **Limit:** it is a mirror, one derivation removed from OFAC. For anything
  legally consequential, verify against OFAC directly or use a commercial
  screening provider with contractual guarantees.

A production posture would fetch OFAC's XML directly or use a screening API.
This module is a strong default, not the last word, and the code says so.

## What screening a match means

Flagging a sanctioned address for risk purposes is permissible — this is what
blockchain-analytics firms do. What is prohibited is providing a bespoke
service to a sanctioned person. SCORE transacts nothing, so it does not "deal
in" blocked property in the transactional sense; the screening step exists so
that any address SCORE reads or reports can be checked, and matches handled
per policy.

## Testing

    pytest tests/test_sanctions.py -m "not live"   # synthetic list, no network
    pytest tests/test_sanctions.py -m live          # fetches the real list

The offline tests cover matching, case-insensitivity, and the fail-loud
behaviours. The live test confirms a known-sanctioned address matches against
the real list while a clean address does not.
