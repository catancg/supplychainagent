"""Local MCP server exposing synthetic-but-deterministic market data.

Read-only, over stdio, a separate process from the agents (docs/feature.prd
§8) — that's the point of the exercise, not an in-app function call.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("market-data")

# Synthetic but deterministic — same inputs always return the same rate.
_FX_RATES: dict[tuple[str, str], float] = {
    ("USD", "ARS"): 130.0,
    ("ARS", "USD"): 1 / 130.0,
}


@mcp.tool()
def get_fx_rate(base: str = "USD", quote: str = "ARS") -> float:
    """Returns the exchange rate to convert 1 unit of `base` into `quote`."""
    if base == quote:
        return 1.0
    rate = _FX_RATES.get((base, quote))
    if rate is None:
        raise ValueError(f"No synthetic FX rate configured for {base}->{quote}")
    return rate


if __name__ == "__main__":
    mcp.run()
