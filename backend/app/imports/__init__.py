"""Manual statement import (CSV/Excel) for accounts Plaid can't link.

Exists because some institutions are not linkable via Plaid — RBC's in-app push
MFA is incompatible with Plaid's refresh model (see CLAUDE.md). The import path
produces the same `Transaction` rows a Plaid sync would, so everything downstream
(categories, budgets, net worth) is source-agnostic.
"""
