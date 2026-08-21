"""
src/compliance/sanctions.py - OFAC SDN screening for wallet addresses.

WHY THIS EXISTS
    SCORE takes no custody and moves no value, so it is not a money
    transmitter (see COMPLIANCE.md). But OFAC sanctions apply to all US
    persons on a strict-liability basis regardless of that status. Because
    SCORE reads and scores wallet addresses, it screens those addresses
    against OFAC's Specially Designated Nationals (SDN) list.

    Screening is NECESSARY BUT NOT SUFFICIENT. It reduces one specific,
    concrete risk. It does not discharge the full legal obligation, and it
    is not legal advice.

DATA SOURCE AND ITS LIMITS
    The authoritative source is OFAC's sdn_advanced.xml, published at
    treasury.gov (~120 MB). This module does NOT parse that file directly.
    It fetches a derived, maintained list: the 0xB10C
    "ofac-sanctioned-digital-currency-addresses" project extracts crypto
    addresses from sdn_advanced.xml nightly (00:00 UTC) via GitHub Actions
    and publishes per-asset address lists.

    This is a deliberate trade-off:
      + The list is well-maintained, correctly parsed, and refreshed daily.
      + It is reachable and testable in ordinary CI.
      - It is a MIRROR, one derivation removed from OFAC. For anything
        legally consequential, verify against OFAC directly or use a
        commercial screening provider with contractual guarantees.

    A production posture would fetch OFAC's XML directly (or use a screening
    API). This module is honest about being a strong default, not the last
    word. That distinction is stated here and in COMPLIANCE.md rather than
    hidden.

FRESHNESS IS ENFORCED
    A stale sanctions list is worse than none: it presents the appearance of
    compliance while missing new designations. This module records when the
    list was fetched and REFUSES to screen against a cache older than
    max_age_hours, raising StaleListError rather than returning a false
    "clear". Failing loud is the correct behaviour for a compliance check.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Set

import requests

logger = logging.getLogger(__name__)

# Derived, nightly-updated ETH address list (see module docstring).
DEFAULT_LIST_URL = (
    "https://raw.githubusercontent.com/0xB10C/"
    "ofac-sanctioned-digital-currency-addresses/lists/"
    "sanctioned_addresses_ETH.txt"
)

# Authoritative source, recorded for provenance and for the production path.
OFAC_AUTHORITATIVE_SOURCE = (
    "https://www.treasury.gov/ofac/downloads/sanctions/1.0/sdn_advanced.xml"
)

DEFAULT_CACHE_PATH = Path.home() / ".score" / "ofac_eth_sanctioned.txt"
DEFAULT_MAX_AGE_HOURS = 24.0


class StaleListError(RuntimeError):
    """Raised when the cached list is older than the allowed maximum and a
    fresh fetch is unavailable. Screening must not proceed against stale
    data, so this is raised rather than swallowed."""


class ListUnavailableError(RuntimeError):
    """Raised when no usable sanctions list can be obtained at all - no
    fetch and no cache. Screening cannot proceed."""


@dataclass
class ScreeningResult:
    """The outcome of screening one address."""
    address: str
    is_sanctioned: bool
    list_age_hours: float
    list_source: str

    def __bool__(self) -> bool:
        # Truthy when sanctioned, so `if screen(addr): block()` reads naturally.
        return self.is_sanctioned


class SanctionsScreener:
    """
    Screens wallet addresses against a maintained OFAC-derived SDN list.

    Typical use:
        screener = SanctionsScreener()
        if screener.screen(wallet).is_sanctioned:
            # handle per policy - do not provide a bespoke service to a
            # sanctioned person; flagging for risk is permissible
            ...
    """

    def __init__(self, list_url: str = DEFAULT_LIST_URL,
                 cache_path: Path = DEFAULT_CACHE_PATH,
                 max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
                 auto_refresh: bool = True):
        self.list_url = list_url
        self.cache_path = Path(cache_path)
        self.max_age_hours = max_age_hours
        self.auto_refresh = auto_refresh

        self._addresses: Optional[Set[str]] = None
        self._fetched_at: float = 0.0
        self._source: str = "uninitialised"

    # -- list management --------------------------------------------------

    def _fetch(self) -> Set[str]:
        """Fetch the list from the network and write it to cache."""
        logger.info("Fetching OFAC-derived SDN list from %s", self.list_url)
        resp = requests.get(self.list_url, timeout=30)
        resp.raise_for_status()

        # Normalise to lowercase: the published list is mixed-case, and
        # address comparison must be case-insensitive or matches are missed.
        addresses = {
            line.strip().lower()
            for line in resp.text.splitlines()
            if line.strip() and line.strip().startswith("0x")
        }
        if not addresses:
            raise ListUnavailableError(
                "Fetched list contained no usable addresses; refusing to "
                "treat an empty list as 'everyone is clear'."
            )

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text("\n".join(sorted(addresses)))
        self._fetched_at = time.time()
        self._source = self.list_url
        logger.info("Loaded %d sanctioned addresses", len(addresses))
        return addresses

    def _load_cache(self) -> Optional[Set[str]]:
        """Load from cache if present; set _fetched_at from the file mtime."""
        if not self.cache_path.exists():
            return None
        text = self.cache_path.read_text()
        addresses = {
            line.strip().lower()
            for line in text.splitlines()
            if line.strip()
        }
        self._fetched_at = self.cache_path.stat().st_mtime
        self._source = str(self.cache_path) + " (cache)"
        return addresses or None

    def _age_hours(self) -> float:
        if self._fetched_at == 0.0:
            return float("inf")
        return (time.time() - self._fetched_at) / 3600.0

    def ensure_list(self) -> None:
        """
        Guarantee a fresh-enough address set is loaded, or raise.

        Order: try network (if auto_refresh); fall back to cache; enforce
        the freshness ceiling on whatever is loaded. Never proceed on a
        stale or empty list.
        """
        if self.auto_refresh:
            try:
                self._addresses = self._fetch()
                return
            except (requests.RequestException, ListUnavailableError) as exc:
                logger.warning("Fetch failed (%s); falling back to cache", exc)

        if self._addresses is None:
            self._addresses = self._load_cache()

        if self._addresses is None:
            raise ListUnavailableError(
                "No sanctions list available: network fetch failed and no "
                "cache exists at " + str(self.cache_path) + ". Screening "
                "cannot proceed."
            )

        age = self._age_hours()
        if age > self.max_age_hours:
            raise StaleListError(
                "Cached sanctions list is " + format(age, ".1f") + "h old, "
                "exceeding the " + str(self.max_age_hours) + "h maximum. "
                "Refusing to screen against stale data. Refresh the list or "
                "raise max_age_hours only with a documented reason."
            )

    # -- screening --------------------------------------------------------

    def screen(self, address: str) -> ScreeningResult:
        """
        Screen a single address. Raises if no fresh list is available.

        Freshness is checked on EVERY call, not only when the list is first
        loaded. A screener is typically constructed once and reused for the
        life of a server process, so "loaded" and "fresh" are not the same
        fact once any time has passed - re-checking only at load time would
        let the ceiling stop applying after the first request.
        """
        if self._addresses is None or self._age_hours() > self.max_age_hours:
            self.ensure_list()

        normalised = address.strip().lower()
        hit = normalised in self._addresses

        if hit:
            logger.warning("SANCTIONS MATCH: %s is on the OFAC-derived SDN "
                           "list", address)

        return ScreeningResult(
            address=address,
            is_sanctioned=hit,
            list_age_hours=round(self._age_hours(), 2),
            list_source=self._source,
        )

    def screen_many(self, addresses):
        """Screen an iterable of addresses. Each call goes through screen(),
        so the freshness ceiling is enforced per-address just as it is for
        a single screen() call; the network fetch itself still only happens
        when the in-memory list is missing or stale."""
        return [self.screen(a) for a in addresses]


# Module-level convenience singleton for simple call sites.
_default: Optional[SanctionsScreener] = None


def is_sanctioned(address: str) -> bool:
    """Convenience check using a shared screener. Raises on stale/absent
    list rather than returning a misleading False."""
    global _default
    if _default is None:
        _default = SanctionsScreener()
    return _default.screen(address).is_sanctioned
