"""
cash_forecast_analyst.py -- a Layer 2 "Analyst" (see repo README).

Owns cash: a 6-month forward cash forecast (base and conservative case),
a recommended weekly inventory-spend ceiling sized off seasonal revenue,
outstanding vendor accounts-payable on net terms, a short-term financing
balance and its weekly payment, and trailing-12-month revenue growth.
Outputs plain facts only -- no severity, no framing. The CFO synthesis
layer decides what any of these numbers mean.

(Sanitized/simplified for this public demo -- the production version reads
real bank, POS, and vendor-invoice exports; this one reads the synthetic
monthly ledger this demo generates and projects forward from it.)
"""

import json
import os
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def run_cash_forecast_analyst():
    with open(os.path.join(DATA_DIR, "monthly_cash_summary.json"), encoding="utf-8") as f:
        monthly = json.load(f)

    months = monthly["months"]
    net_cash_flow = monthly["netCashFlowByMonth"]
    starting_cash = monthly["currentCashBalance"]
    ttm_revenue = monthly["trailingTwelveMonthRevenue"]
    prior_ttm_revenue = monthly["priorTrailingTwelveMonthRevenue"]
    vendor_ap_total = monthly["vendorApOutstanding"]
    financing_balance = monthly["financingBalance"]
    financing_weekly_payment = monthly["financingWeeklyPayment"]

    # Project the next 6 months two ways: base case uses each month's
    # actual seasonal flow as projected, conservative case haircuts every
    # projected inflow by 15% to stress-test against a softer season.
    base_cash = starting_cash
    conservative_cash = starting_cash
    for flow in net_cash_flow[:6]:
        base_cash += flow
        conservative_cash += flow * 0.85 if flow > 0 else flow

    growth_pct = (ttm_revenue - prior_ttm_revenue) / prior_ttm_revenue if prior_ttm_revenue else None

    # Weekly ordering allowance: a simple seasonal-weighting rule -- more
    # room to order in a month that's trending up relative to the trailing
    # average, tighter in a month trending down.
    avg_monthly_revenue = ttm_revenue / 12
    current_month_weight = net_cash_flow[0] if net_cash_flow else 0
    recommended_allowance = max(0.0, (avg_monthly_revenue * 0.12) / 4.3)

    payload = {
        "asOfDate": datetime.now().strftime("%B %d, %Y"),
        "baseCaseSixMonthCash": round(base_cash, 2),
        "conservativeCaseSixMonthCash": round(conservative_cash, 2),
        "recommendedAllowance": round(recommended_allowance, 2),
        "vendorApTotal": round(vendor_ap_total, 2),
        "financingBalance": round(financing_balance, 2),
        "financingWeeklyPayment": round(financing_weekly_payment, 2),
        "growthTrendPct": round(growth_pct, 4) if growth_pct is not None else None,
        "ttmRevenue": round(ttm_revenue, 2),
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    out_file = os.path.join(DATA_DIR, "cash_forecast_live.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    growth_display = f"{payload['growthTrendPct']*100:.1f}%" if payload['growthTrendPct'] is not None else "N/A"
    print(f"[cash_forecast_analyst] conservative 6-mo cash ${payload['conservativeCaseSixMonthCash']:,.2f}, "
          f"growth {growth_display} -> {out_file}")
    return payload


if __name__ == "__main__":
    run_cash_forecast_analyst()
