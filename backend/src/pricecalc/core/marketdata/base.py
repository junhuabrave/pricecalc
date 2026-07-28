"""The seam between the engine and wherever quotes come from.

Today the only implementation is a simulator. A live adapter (Polygon, Tradier,
IBKR) satisfies the same protocol, so nothing downstream of `ChainFeed` needs
to change when one lands — the arbitrage scanner already works on `Chain`, and
`Chain` says nothing about its origin.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pricecalc.core.chain import Chain


@runtime_checkable
class ChainFeed(Protocol):
    """Anything that can produce an option chain snapshot."""

    @property
    def name(self) -> str:
        """Human-readable source label, surfaced in the UI."""
        ...

    def snapshot(self) -> Chain:
        """Return the current chain. Implementations may block on I/O."""
        ...
