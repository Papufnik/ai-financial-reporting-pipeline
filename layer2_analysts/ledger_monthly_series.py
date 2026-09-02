"""
ledger_monthly_series.py -- loads a categorized bank ledger's "Monthly
Summary" tab as time series keyed by category code, for use with
pattern_scan.py.

(Sanitized demo module. In production this is the ONLY place in the real
suite with genuine multi-domain historical time series already computed and
durable -- most other analyst outputs are point-in-time snapshots,
overwritten on every refresh, so there's no history to correlate against
for those domains. Extracted into its own module so every Senior Manager
role that wants to run a correlation scan reads the same parsing logic
rather than each keeping its own copy.)

Deliberately EXCLUDES pass-through categories (PT-*: sales tax, card
payoffs -- not real revenue/expense), internal transfers (IC-*), owner
draws (EQ-DRAW), one-off capex (CAPEX-*), and anything flagged
manual-review/personal/unclassified (NR-*) -- both because they're not
operationally meaningful for pattern-finding and, for anything tagged
personal, because of a hard privacy rule this pipeline follows: any
personal (non-business) transaction data must never enter analysis, even
accidentally.
"""

import openpyxl

INCLUDED_PREFIXES = ("INC-", "LAB-", "OCC-", "INV-", "OPX-", "FIN-")


def load_ledger_monthly_series(ledger_path, included_prefixes=INCLUDED_PREFIXES):
    """Returns (months, series, labels):
      months: ordered list of 'YYYY-MM' column labels
      series: dict[category_code] -> list of values (or None), aligned to months
      labels: dict[category_code] -> human-readable category name
    """
    wb = openpyxl.load_workbook(ledger_path, data_only=True, read_only=True)
    ws = wb["Monthly Summary"]
    rows = list(ws.iter_rows(values_only=True))

    header = rows[1]  # ('Code', 'Category', '2025-01', ..., 'TOTAL')
    month_cols = [(i, h) for i, h in enumerate(header) if isinstance(h, str) and h.count("-") == 1 and h[:4].isdigit()]
    months = [h for _, h in month_cols]

    series = {}
    labels = {}
    for row in rows[2:]:
        code = row[0]
        if not code or not isinstance(code, str) or not code.startswith(included_prefixes):
            continue
        values = [row[i] if isinstance(row[i], (int, float)) else None for i, _ in month_cols]
        series[code] = values
        labels[code] = row[1]
    return months, series, labels
