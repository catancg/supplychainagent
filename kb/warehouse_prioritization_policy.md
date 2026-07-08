# Warehouse Prioritization Policy

When a SKU is short across more than one warehouse, prioritize replenishment
by how close each warehouse is to (or past) its reorder point, not by
warehouse size or order of listing. The warehouse with the smallest ratio of
on-hand inventory to its own reorder point is the most urgent.

Destination warehouse for a purchase order should be the single most urgent
warehouse for that SKU, unless the shortfall spans multiple warehouses and
splitting the order across them is the only way to stay within budget while
still resolving every warehouse's shortfall.
