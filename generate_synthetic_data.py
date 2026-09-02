"""
generate_synthetic_data.py -- builds a fake but internally-consistent 18
months of retail business data so the rest of this pipeline can run
standalone, with no real business's financial data anywhere in this repo.

Deliberately engineers one genuine cross-domain relationship into the
synthetic ledger (staffing wages and utility costs both track the same
seasonal foot-traffic/hours pattern) so pattern_scan.py has something real
to find when cfo_synthesis.py runs it -- everything else in the synthetic
ledger is closer to noise, so the demo's "Statistical Lead" output isn't
guaranteed to always highlight the same pair, but should usually surface
this one.

Writes:
  data/synthetic_ledger.xlsx      -- 18-month categorized ledger (for pattern_scan)
  data/category_sales.csv         -- trailing-90-day sales/COGS by category (for inventory_health_analyst)
  data/category_inventory.csv     -- current inventory cost by category (for inventory_health_analyst)
  data/monthly_cash_summary.json  -- cash position + AP/financing facts (for cash_forecast_analyst)
  data/ops_metrics.json           -- operational metrics (for coo_synthesis)
"""

import csv
import json
import os
import random
from datetime import date

import openpyxl

random.seed(42)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# 18 months, Jan 2025 through Jun 2026
MONTHS = [f"{y}-{m:02d}" for y in (2025,) for m in range(1, 13)] + [f"2026-{m:02d}" for m in range(1, 7)]

# Seasonal multiplier by calendar month (tourist-town retail pattern: slow
# in deep winter, peaks in summer).
SEASONAL_MULT = {
    1: 0.55, 2: 0.55, 3: 0.70, 4: 0.85, 5: 1.05, 6: 1.35,
    7: 1.45, 8: 1.35, 9: 1.05, 10: 0.85, 11: 0.80, 12: 1.10,
}


def _season(month_str):
    return SEASONAL_MULT[int(month_str.split("-")[1])]


def _noisy(value, pct=0.06):
    return value * (1 + random.uniform(-pct, pct))


def build_ledger():
    rows_by_code = {}

    def series(base, season_weight=1.0, growth_per_month=0.0, noise=0.06):
        out = []
        for i, m in enumerate(MONTHS):
            seasonal = 1 + (season_weight * (_season(m) - 1))
            trend = 1 + growth_per_month * i
            out.append(round(_noisy(base * seasonal * trend, noise), 2))
        return out

    # Revenue -- excluded from pattern-scan surfacing (REVENUE_CODES) but
    # still drives seasonality assumptions elsewhere in the demo.
    rows_by_code["INC-RETAIL"] = ("In-Store Retail Sales", series(42000, season_weight=1.0, growth_per_month=0.006))
    rows_by_code["INC-ONLINE"] = ("Online Sales", series(6000, season_weight=0.6, growth_per_month=0.015))

    # Labor and utilities: the engineered cross-domain relationship --
    # both track the same seasonal hours/traffic pattern.
    rows_by_code["LAB-WAGES"] = ("Staff Wages", series(11000, season_weight=0.9, noise=0.05))
    rows_by_code["OCC-UTILITIES"] = ("Utilities", series(1400, season_weight=0.9, noise=0.05))

    # Rent: flat, no seasonality -- a same-domain (OCC) comparison point
    # that should NOT correlate with utilities despite sharing a domain.
    rows_by_code["OCC-RENT"] = ("Rent", series(4200, season_weight=0.0, noise=0.01))

    # Inventory purchases: loosely seasonal (restocking ahead of season)
    # but noisy enough not to cleanly correlate with anything.
    rows_by_code["INV-PURCHASES"] = ("Inventory Purchases", series(14000, season_weight=0.5, noise=0.20))

    # Opex: marketing and supplies, both mostly noise.
    rows_by_code["OPX-MARKETING"] = ("Marketing", series(1800, season_weight=0.3, noise=0.25))
    rows_by_code["OPX-SUPPLIES"] = ("Supplies", series(600, season_weight=0.1, noise=0.20))

    # Financing: a slowly-declining balance-service payment, not seasonal.
    rows_by_code["FIN-INTEREST"] = ("Financing Interest & Fees", series(300, season_weight=0.0, growth_per_month=-0.01, noise=0.03))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Monthly Summary"
    ws.append(["Synthetic 18-Month Ledger -- generated for pipeline_demo, not real business data"])
    ws.append(["Code", "Category"] + MONTHS + ["TOTAL"])
    for code, (label, values) in rows_by_code.items():
        ws.append([code, label] + values + [round(sum(values), 2)])

    os.makedirs(DATA_DIR, exist_ok=True)
    out_path = os.path.join(DATA_DIR, "synthetic_ledger.xlsx")
    wb.save(out_path)
    print(f"[generate_synthetic_data] wrote {out_path} ({len(MONTHS)} months, {len(rows_by_code)} categories)")


def build_category_sales_and_inventory():
    # Trailing-90-day category performance, engineered so:
    #  - a couple of categories have strong GMROI (healthy turn)
    #  - one or two are moderate
    #  - one category ("Seasonal Closeout") has real inventory cost but
    #    ZERO sales this window -- the dead-stock case
    categories = [
        {"category": "Apparel",            "net_sales": 38500, "cogs": 19200, "inventory_cost": 9800},
        {"category": "Jewelry",             "net_sales": 21400, "cogs": 8600,  "inventory_cost": 4100},
        {"category": "Home Goods",          "net_sales": 16200, "cogs": 9700,  "inventory_cost": 12300},
        {"category": "Candles & Gifts",     "net_sales": 12800, "cogs": 6100,  "inventory_cost": 5200},
        {"category": "Wine Accessories",    "net_sales": 7400,  "cogs": 4300,  "inventory_cost": 6900},
        {"category": "Seasonal Closeout",   "net_sales": 0,     "cogs": 0,     "inventory_cost": 7600},
    ]

    with open(os.path.join(DATA_DIR, "category_sales.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["category", "net_sales", "cogs"])
        writer.writeheader()
        for c in categories:
            writer.writerow({"category": c["category"], "net_sales": c["net_sales"], "cogs": c["cogs"]})

    with open(os.path.join(DATA_DIR, "category_inventory.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["category", "inventory_cost"])
        writer.writeheader()
        for c in categories:
            writer.writerow({"category": c["category"], "inventory_cost": c["inventory_cost"]})

    print("[generate_synthetic_data] wrote category_sales.csv and category_inventory.csv")


def build_monthly_cash_summary():
    # Net cash flow for the NEXT 6 months (index 0 = next month), seasonal.
    upcoming_months = ["2026-07", "2026-08", "2026-09", "2026-10", "2026-11", "2026-12"]
    net_cash_flow = [round(_noisy(9000 * (1 + 0.9 * (_season(m) - 1)), 0.10) - 6000, 2) for m in upcoming_months]

    payload = {
        "months": upcoming_months,
        "netCashFlowByMonth": net_cash_flow,
        "currentCashBalance": 41250.00,
        "trailingTwelveMonthRevenue": 612000.00,
        "priorTrailingTwelveMonthRevenue": 571000.00,
        "vendorApOutstanding": 18420.35,
        "financingBalance": 9200.00,
        "financingWeeklyPayment": 385.50,
    }
    with open(os.path.join(DATA_DIR, "monthly_cash_summary.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print("[generate_synthetic_data] wrote monthly_cash_summary.json")


def build_ops_metrics():
    payload = {
        "stockoutRate": 0.052,
        "stockoutSkuCount": 34,
        "discountRateOfRevenue": 0.11,
        "laborToTrafficRatio": 1.41,
    }
    with open(os.path.join(DATA_DIR, "ops_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print("[generate_synthetic_data] wrote ops_metrics.json")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    build_ledger()
    build_category_sales_and_inventory()
    build_monthly_cash_summary()
    build_ops_metrics()
    print("\n[SUCCESS] Synthetic data generated -- none of it is real business data.")


if __name__ == "__main__":
    main()
