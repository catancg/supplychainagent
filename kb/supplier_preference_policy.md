# Supplier Preference Policy

When multiple suppliers cover the same SKU, prefer the supplier with the best
weighted balance of cost, lead time, and reliability — do not automatically
pick the cheapest option. A supplier below 0.90 reliability should only be
selected if no more reliable option is available or affordable within budget.

Domestic (ARS) suppliers are generally preferred for SKUs that are currently
below their reorder point, since their shorter lead time reduces the risk of
a prolonged stockout. Imported (USD) suppliers are usually cheaper per unit
but carry FX risk and long lead times — see the long-lead-time policy for
when that tradeoff is acceptable.

Never place an order with a supplier marked `available: false`. If the
preferred or cheapest supplier for a SKU is unavailable, fall back to the
next-best available supplier for that SKU. If no supplier is available for a
SKU that needs replenishment, do not fabricate an order — flag the gap in the
rationale instead.
