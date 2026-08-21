# SCORE — Quality Process

> Written after a review surfaced four unrelated defects this project's own
> tests and docs had missed: a compliance control that stops enforcing itself
> after the first call, a feature computing the wrong side of a ratio, a
> "resolved" heading over an inference nobody counted, and a test that
> validates its fixture instead of its claim. This document is the standing
> discipline meant to make that class of failure structurally harder to ship,
> not a one-time apology.
>
> Written: 2026-08-21

---

## The common root cause

Every defect the review found had the same shape: **something asserted a
claim without a mechanism forcing the claim to stay true.** A docstring said
"refuses to screen stale data" without a test that exercised the long-lived
path where that becomes false. A heading said "resolved" over a plausibility
argument, not a count. A test asserted a value equalled itself. A status
summary was relayed from memory instead of re-derived from the repository in
front of me.

The fix is not "be more careful." It is: every claim in this project must
name the mechanism that keeps it true, and that mechanism must be exercised,
not assumed.

---

## 1. State claims are re-derived, never recalled

Any statement about repository state — commit, test count, what's
implemented, whether something is "resolved" — is re-derived from a live
command in the same turn it's made, never from a prior summary (mine or
anyone else's).

- `git log`, `git status`, `git show --stat` before describing "where we
  are." A summary from three commits ago is treated as a hypothesis to
  recheck, not a fact to repeat.
- Any number quoted (test count, latency, coverage) is re-counted or
  re-measured in that turn, not carried forward.
- This is the [verification-before-completion](https://github.com/obra/superpowers)
  iron law applied one level up: no status claims without fresh evidence,
  the same way no completion claims go out without fresh evidence.

## 2. Tests are built to exercise the claim, not to pass

Four concrete defects slipped past 28 passing tests. Each is now a standing
rule:

- **Long-lived-process bugs need long-lived-process tests.** The sanctions
  freshness check was only ever exercised against a freshly constructed
  screener; the server holds one as a singleton for its whole life. Any
  "fails loud after N hours" or "refuses stale state" claim gets a test that
  reuses the *same instance* across calls with simulated time passage — not
  a fresh instance per assertion.
- **No tautological fixtures.** A "known-sanctioned address" must come from
  a value hardcoded independently of the list being tested — never
  `sorted(list)[0]`, never anything derived from the same structure the test
  is supposed to be checking. If the fixture and the assertion can't
  disagree, the test proves nothing.
- **Default test-helper parameters must not paper over untested branches.**
  `market(symbol, cf=0.85)` meant the `collateral_factor=None` path had zero
  coverage across 11 tests. Any `Optional` field in a data model gets an
  explicit `None`-path test, not just a happy-path default.
- **A README/API claim about the deployed path needs a test of the deployed
  path.** The 173ms figure timed `get_wallet_position` + `extract_features`
  directly; it never went through Flask or sanctions screening. Any
  user-facing performance or behavior claim is tested at the boundary the
  user actually hits (the endpoint), not an internal call one layer in.
- **Direction/sign claims get a named, worked example in the docstring**,
  not just an assertion. `price_move_to_liquidation` computing the
  debt-price-rise instead of the collateral-price-drop shipped because
  nothing forced a human to state which direction was meant in words next
  to the formula.

## 3. Docs are code: they drift, so they're checked

`book/02` describes `getAssetsIn`; the shipping client calls `getAllMarkets`.
`PHASE_0.md` describes `setScorer` as a risk surface; `CreditScorer.sol` has
no such function. Both are cases of a doc describing an earlier or aspirational
version of the code and never being reconciled.

- Any commit that changes a function name, contract interface, or public
  behavior greps `book/`, `docs/`, and `README.md` for the old name before
  closing the change, and updates or flags every hit.
- Any doc that names a specific function, contract method, or endpoint is
  treated as a claim requiring the same verification as code: confirm the
  named thing still exists and does what's described, in the same session
  the doc is touched.

## 4. Status labels are calibrated: measured vs. inferred vs. assumed

"Resolved 2026-08-16" over a fee-revenue-implies-liquidation-count inference
is a measured-sounding label on an inferred conclusion. Going forward:

- A heading may claim **resolved** or **confirmed** only when backed by a
  primary artifact (a count, a test, a direct measurement) linked in the same
  section.
- Anything short of that is labeled **inferred** (state the inference chain
  and what would falsify it) or **assumed** (state what's being taken on
  faith and why). "Extraction is the work, not feasibility" is a fine
  sentence — it just doesn't belong under a heading that says the question
  is resolved.

## 5. The verification-before-completion gate applies to every claim I make on this project

Before any status claim, satisfaction expression, or "done"/"fixed"/
"resolved" statement in this repo:

1. Name the command or artifact that proves it.
2. Run it, fresh, in that turn.
3. Read the full output.
4. Only then make the claim, with the evidence attached.

No "should work now," no "looks correct," no relaying a test-suite result
from an earlier turn. This is the existing `superpowers:verification-before-completion`
discipline; it now explicitly covers state summaries and doc claims, not
just "tests pass."

## 6. Third-party and agent review intake: verify claim-by-claim before acting on or relaying it

When a review arrives — from another Claude session, a human, a linter, a
subagent — it gets checked line by line against the actual source before I
either adopt its conclusions or present them to you as fact. That means:
re-reading the exact file/line for each claim, reproducing the described
behavior where feasible, and explicitly separating what I confirmed from
what I couldn't check (e.g., no RPC key, so live-latency figures stay
"reported, not reproduced"). A review is a set of hypotheses until each one
is checked — including reviews that are largely right, like this one was.

## Pre-close checklist

Before calling any unit of work done, resolved, or ready to hand off:

- [ ] State claims in this response are re-derived from a command run this
      turn, not recalled.
- [ ] Every "fails/refuses/enforces" claim has a test that exercises the
      actual failure path (stateful/long-lived where relevant), not just the
      fresh-instance happy path.
- [ ] Every `Optional`/nullable field has an explicit edge-case test.
- [ ] No test fixture is derived from the same structure it's meant to
      validate.
- [ ] Any user-facing claim (latency, behavior, "returns X") is tested at
      the boundary the user hits.
- [ ] Docs/book references to function or contract names were grepped and
      confirmed to still exist.
- [ ] Any "resolved"/"confirmed" heading links a measured artifact, not an
      inference.
- [ ] If a review (mine or someone else's) drove this work, its claims were
      checked against source, not relayed on trust.
