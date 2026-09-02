import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "layer2_analysts"))
from pattern_scan import scan_correlations
from ledger_monthly_series import load_ledger_monthly_series

"""
cfo_synthesis.py -- the CFO role in the Senior Manager layer (Layer 3, see
repo README). Reads the financial analysts' plain JSON output, applies real
thresholds, and decides what actually needs the owner's attention this
week -- versus what's fine and doesn't need to be surfaced at all.

(Genericized/trimmed from a production script written for a real small
retail business. The full production version also reads a merchandising/
basket-attachment analyst and a Payment Integrity analyst that depend on
that business's specific POS export format -- omitted here to keep this
demo runnable standalone, noted rather than silently dropped.)

Design principles this pipeline holds to throughout (see README):
  - "Surface facts, humans decide": every item below is phrased as
    something worth considering, never a directive to execute. Nothing
    here is addressed to a role or person who doesn't actually exist at a
    small business -- it reaches the one person who reads it, and THEY
    decide what happens next.
  - Every field name read here was checked against the actual analyst JSON
    schema before being trusted -- in the real production history behind
    this demo, an earlier draft of this exact script had SEVEN silent
    schema-mismatch bugs (wrong key names that all defaulted to 0.0 on
    failure instead of erroring), which ran clean and wrote a JSON file
    every single day with every number wrong, undetected, because nothing
    downstream ever validated the values it was reading. Caught only by
    manually diffing every field this script reads against the analyst's
    actual output keys. That's why every read below uses the exact key the
    upstream analyst actually writes, not a guessed or renamed one.
  - Statistical pattern-finding (below) is kept strictly separate from
    verified facts: it's always tagged severity INFO, is filtered to
    exclude anything trivially explained by revenue scale, and never feeds
    into needsAttention. A correlation is a lead worth a second look, not
    a fact to act on.
"""

SEVERITY_ORDER = {"CRITICAL": 0, "WARNING": 1, "INFO": 2, "OPTIMAL": 3}
CORRELATION_SURFACE_THRESHOLD = 0.6
PATTERN_MIN_OVERLAP_MONTHS = 10
REVENUE_CODES = {"INC-RETAIL", "INC-ONLINE"}
MAX_PATTERNS_SURFACED = 3

DEAD_STOCK_THRESHOLD = 5000.0
GMROI_STRONG_THRESHOLD = 4.0
CONSERVATIVE_CASH_FLOOR = 20000.0


def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] Failed to load {filepath}: {e}")
    else:
        print(f"[WARN] Missing source file: {filepath}")
    return {}


def run_cfo_synthesis():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.abspath(os.path.join(base_dir, "..", "data"))

    print(f"=== CFO Synthesis [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ===")

    inv_health = load_json(os.path.join(data_dir, "inventory_health_live.json"))
    cash_forecast = load_json(os.path.join(data_dir, "cash_forecast_live.json"))

    audit_timestamp = datetime.now().strftime("%B %d, %Y %H:%M")

    # -------------------------------------------------------------------
    # 1. Capital Efficiency
    # -------------------------------------------------------------------
    dead_stock_cost = inv_health.get("deadStockCost", 0.0) or 0.0
    dead_stock_count = inv_health.get("deadStockCount", 0) or 0
    overall_gmroi = inv_health.get("overall", 0.0) or 0.0

    capital_items = []
    if dead_stock_cost > DEAD_STOCK_THRESHOLD:
        capital_items.append({
            "severity": "CRITICAL" if dead_stock_cost > DEAD_STOCK_THRESHOLD * 2 else "WARNING",
            "title": "Trapped Capital in Dead Stock",
            "metric": f"${dead_stock_cost:,.2f}",
            "description": f"{dead_stock_count} categor{'y has' if dead_stock_count == 1 else 'ies have'} generated $0 in sales this window, holding ${dead_stock_cost:,.2f} in working capital.",
            "worth_considering": "A targeted clearance or bundling pass on these categories would free up cash currently sitting on shelves.",
        })

    if overall_gmroi >= GMROI_STRONG_THRESHOLD:
        capital_items.append({
            "severity": "OPTIMAL",
            "title": "Strong Inventory Return (GMROI)",
            "metric": f"{overall_gmroi:.2f}x",
            "description": f"Annualized Gross Margin Return on Inventory is {overall_gmroi:.2f}x.",
            "worth_considering": "Current reorder buffer sizes for top-tier categories appear to be working -- no change indicated.",
        })
    elif overall_gmroi > 0:
        capital_items.append({
            "severity": "WARNING",
            "title": "Moderate GMROI Performance",
            "metric": f"{overall_gmroi:.2f}x",
            "description": "Inventory return is moderate -- some slow-turning categories are weighing down the total.",
            "worth_considering": "Worth checking which categories are dragging the average down before the next reorder decision.",
        })

    # -------------------------------------------------------------------
    # 2. Cash, Debt & Terms
    # -------------------------------------------------------------------
    conservative_cash = cash_forecast.get("conservativeCaseSixMonthCash")
    base_cash = cash_forecast.get("baseCaseSixMonthCash")
    ordering_allowance = cash_forecast.get("recommendedAllowance", 0.0) or 0.0
    vendor_ap_total = cash_forecast.get("vendorApTotal")
    financing_balance = cash_forecast.get("financingBalance", 0.0) or 0.0
    financing_weekly_payment = cash_forecast.get("financingWeeklyPayment")

    cash_items = []
    if conservative_cash is not None:
        cash_items.append({
            "severity": "WARNING" if conservative_cash < CONSERVATIVE_CASH_FLOOR else "OPTIMAL",
            "title": "Cash Forecast (Conservative Case)",
            "metric": f"${conservative_cash:,.2f}",
            "description": f"Projected cash at the end of the 6-month forecast window, conservative case (base case: ${base_cash:,.2f}).",
            "worth_considering": f"Below ${CONSERVATIVE_CASH_FLOOR:,.0f} conservative, the weekly ordering ceiling below is worth holding to strictly." if conservative_cash < CONSERVATIVE_CASH_FLOOR else None,
        })

    cash_items.append({
        "severity": "INFO",
        "title": "Weekly Ordering Allowance",
        "metric": f"${ordering_allowance:,.2f}/wk",
        "description": f"Recommended inventory spend ceiling for this week, based on seasonal revenue weighting: ${ordering_allowance:,.2f}.",
        "worth_considering": "Applies across all vendors combined, not per-vendor.",
    })

    if vendor_ap_total is not None:
        cash_items.append({
            "severity": "INFO",
            "title": "Vendor Accounts Payable Outstanding",
            "metric": f"${vendor_ap_total:,.2f}",
            "description": "Total open balance on vendor net-terms invoices.",
            "worth_considering": None,
        })

    if financing_balance > 0:
        payment_str = f"${financing_weekly_payment:,.2f}/week" if financing_weekly_payment is not None else "an unknown weekly amount (source field missing)"
        cash_items.append({
            "severity": "INFO",
            "title": "Short-Term Financing Payoff",
            "metric": f"${financing_balance:,.2f}",
            "description": f"Remaining balance on short-term financing, servicing at {payment_str}.",
            "worth_considering": "Factor the weekly auto-debit into cash buffer before placing large open-account vendor orders.",
        })

    # -------------------------------------------------------------------
    # 3. Patterns Worth a Look -- systematic statistical search, not
    # speculative prose. pattern_scan.py runs Pearson correlation across
    # every pair of category time series, at 0/1/2-month lags, with a hard
    # minimum-sample-size guardrail, the way a chess engine checks
    # combinations no human would bother with by hand.
    # -------------------------------------------------------------------
    pattern_items = []
    ledger_path = os.path.join(data_dir, "synthetic_ledger.xlsx")
    if os.path.exists(ledger_path):
        try:
            months, ledger_series, ledger_labels = load_ledger_monthly_series(ledger_path)
            scan = scan_correlations(ledger_series, ledger_labels, min_overlap=PATTERN_MIN_OVERLAP_MONTHS, lags=(0, 1, 2))
            candidates = [
                r for r in scan["results"]
                if not r["sameDomain"]
                and r["a"] not in REVENUE_CODES and r["b"] not in REVENUE_CODES
                and abs(r["r"]) >= CORRELATION_SURFACE_THRESHOLD
            ]
            seen_pairs = set()
            deduped = []
            for res in candidates:
                pair_key = frozenset((res["a"], res["b"]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                deduped.append(res)
            for res in deduped[:MAX_PATTERNS_SURFACED]:
                pattern_items.append({
                    "severity": "INFO",
                    "title": f"Statistical Lead: {res['a']} ↔ {res['b']}",
                    "metric": f"r={res['r']:+.2f} (n={res['n']} months)",
                    "description": res["description"],
                    "worth_considering": (
                        f"Found by scanning {scan['testsRun']} category-pair/lag combinations across "
                        f"{len(months)} months of ledger history -- correlation, not proven causation, "
                        f"and a small sample besides. Worth a look if it keeps showing up on future refreshes, "
                        f"not something to act on from one run."
                    ),
                })
            if not pattern_items:
                pattern_items.append({
                    "severity": "INFO",
                    "title": "Statistical Pattern Scan",
                    "metric": f"{scan['resultsWithEnoughData']} testable, 0 above threshold",
                    "description": (
                        f"Scanned {scan['testsRun']} category-pair/lag combinations across {len(months)} months "
                        f"of ledger history; nothing non-revenue-driven cleared |r| >= {CORRELATION_SURFACE_THRESHOLD:.1f} this run."
                    ),
                    "worth_considering": None,
                })
        except Exception as e:
            print(f"[WARN] Pattern scan failed: {e}")
    else:
        print(f"[WARN] Missing source file: {ledger_path}")

    # -------------------------------------------------------------------
    # 4. Summary
    # -------------------------------------------------------------------
    all_items = capital_items + cash_items
    all_items.sort(key=lambda x: SEVERITY_ORDER.get(x["severity"], 9))
    critical_or_warning = [i for i in all_items if i["severity"] in ("CRITICAL", "WARNING")]

    summary_bullets = [f"Trailing GMROI {overall_gmroi:.2f}x; ${dead_stock_cost:,.2f} in dead stock ({dead_stock_count} categories)."]
    if conservative_cash is not None:
        summary_bullets.append(f"Conservative-case cash forecast ends the window at ${conservative_cash:,.2f}; weekly ordering ceiling ${ordering_allowance:,.2f}.")
    if vendor_ap_total is not None:
        summary_bullets.append(f"${vendor_ap_total:,.2f} outstanding on vendor terms.")
    if financing_balance > 0:
        summary_bullets.append(f"Short-term financing balance ${financing_balance:,.2f} remaining.")

    payload = {
        "asOfDate": audit_timestamp,
        "audience": "owner (this reaches one person; they decide what, if anything, goes further)",
        "summary": summary_bullets,
        "needsAttention": critical_or_warning,
        "capitalEfficiency": capital_items,
        "cashDebtAndTerms": cash_items,
        "patternsWorthALook": pattern_items,
    }

    out_file = os.path.join(data_dir, "cfo_synthesis.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print("\n--- CFO Synthesis: what needs attention ---")
    if critical_or_warning:
        for item in critical_or_warning:
            print(f"[{item['severity']}] {item['title']}: {item['metric']}")
    else:
        print("Nothing crossed a CRITICAL/WARNING threshold this run.")
    print(f"\n[SUCCESS] CFO synthesis written -> {out_file}")
    return payload


if __name__ == "__main__":
    run_cfo_synthesis()
