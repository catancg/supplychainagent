# Budget Discipline Policy

The total cost of all purchase orders in an action plan must never exceed
`budget_per_cycle`. This is a hard constraint, not a target to approach.

When total demand across SKUs would exceed the budget if fully covered:

1. Cover shortfalls first for SKUs that are below their reorder point,
   ordered by severity (largest gap between on-hand and reorder point
   first), before adding any discretionary replenishment.
2. Within a SKU, prefer the lowest total landed cost among suppliers that
   still meet the lead-time requirement from the long-lead-time policy.
3. If covering every shortfall would exceed budget, reduce order quantities
   proportionally or drop the lowest-severity shortfalls rather than
   silently overspending, and say so explicitly in the rationale.

Never round a budget check in the plan's favor. If total cost is even
marginally over budget, the plan must be revised before it is emitted.
