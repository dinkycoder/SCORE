"""
tests/test_sanctions.py - OFAC screening tests.

Split into offline tests (synthetic list, no network - run in CI) and one
live test (fetches the real list - marked, excluded from CI like the RPC
latency test).
"""

import sys
import time
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from compliance.sanctions import (
    SanctionsScreener,
    StaleListError,
    ListUnavailableError,
)

SANCTIONED = "0xabc0000000000000000000000000000000000001"
CLEAN = "0xAA503ae37ba4A6FCC2fD6CC3F3Dc776Ab11B7b67"


def write_list(addresses):
    """Write a synthetic sanctions list to a temp file, return its path."""
    p = Path(tempfile.mkdtemp()) / "list.txt"
    p.write_text("\n".join(addresses))
    return p


def screener_with(addresses, **kw):
    """A screener backed by a synthetic cached list, no network."""
    p = write_list(addresses)
    s = SanctionsScreener(cache_path=p, auto_refresh=False, **kw)
    return s


# -- core matching --------------------------------------------------------

def test_sanctioned_address_matches():
    s = screener_with([SANCTIONED])
    assert s.screen(SANCTIONED).is_sanctioned is True


def test_clean_address_does_not_match():
    s = screener_with([SANCTIONED])
    assert s.screen(CLEAN).is_sanctioned is False


def test_match_is_case_insensitive():
    """The published list is mixed-case; comparison must normalise."""
    s = screener_with([SANCTIONED.lower()])
    assert s.screen(SANCTIONED.upper().replace("0X", "0x")).is_sanctioned is True


def test_result_is_truthy_when_sanctioned():
    """`if screen(addr): block()` should work."""
    s = screener_with([SANCTIONED])
    assert bool(s.screen(SANCTIONED)) is True
    assert bool(s.screen(CLEAN)) is False


def test_screen_many():
    s = screener_with([SANCTIONED])
    results = s.screen_many([SANCTIONED, CLEAN])
    assert [r.is_sanctioned for r in results] == [True, False]


# -- failing loud: the compliance-critical behaviour ----------------------

def test_stale_list_refuses():
    """A list older than the ceiling must raise, not return a false clear."""
    s = screener_with([SANCTIONED], max_age_hours=0.0)
    # force the cache mtime into the past
    import os
    old = time.time() - 100_000
    os.utime(s.cache_path, (old, old))
    with pytest.raises(StaleListError):
        s.screen(CLEAN)


def test_absent_list_refuses():
    """No cache and no network must raise, not clear."""
    s = SanctionsScreener(
        cache_path=Path(tempfile.mkdtemp()) / "nope.txt",
        auto_refresh=False,
    )
    with pytest.raises(ListUnavailableError):
        s.screen(CLEAN)


def test_empty_list_is_not_treated_as_all_clear():
    """An empty fetched list must not silently clear everyone."""
    s = screener_with([])  # empty file -> _load_cache returns None
    with pytest.raises(ListUnavailableError):
        s.screen(CLEAN)


# -- metadata -------------------------------------------------------------

def test_result_reports_age_and_source():
    s = screener_with([SANCTIONED])
    r = s.screen(SANCTIONED)
    assert r.list_age_hours >= 0
    assert "cache" in r.list_source


# -- live ------------------------------------------------------------------

@pytest.mark.live
def test_live_list_fetches_and_screens():
    """Fetch the real OFAC-derived list and confirm a known-sanctioned
    address matches while a clean one does not. Network-dependent."""
    s = SanctionsScreener(cache_path=Path(tempfile.mkdtemp()) / "live.txt")
    s.ensure_list()
    assert len(s._addresses) > 0

    known = sorted(s._addresses)[0]
    assert s.screen(known).is_sanctioned is True
    assert s.screen(CLEAN).is_sanctioned is False
