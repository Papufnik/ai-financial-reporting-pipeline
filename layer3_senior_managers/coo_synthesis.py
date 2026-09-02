import os
import json
from datetime import datetime

"""
coo_synthesis.py -- the COO role in the Senior Manager layer (Layer 3, see
repo README). Same pattern as cfo_synthesis.py, applied to operations
instead of finance: reads plain operational metrics, applies real
thresholds, and decides what needs the owner's attention this week.

(Generic demo version. The full production version this is modeled on
reads several dedicated Layer 2 analysts -- staffing-to-traffic ratio,
stockout tracking, discount/markdown rate, vendor lead-time variance. This
demo reads one consolidated ops_metrics.json produced directly by the
synthetic data generator, standing in for that fuller analyst layer, to
keep the demo runnable without a real POS/scheduling integration behind
it. The threshold logic and severity model are the real pattern.)
"""

SEVERITY_ORDER = {"CRITICAL": 0, "WARNING": 1, "INFO": 2, "OPTIMAL": 3}

STOCKOUT_RATE_WARNING = 0.04     # % of SKU-days out of stock
STOCKOUT_RATE_CRITICAL = 0.08
DISCOUNT_RATE_WARNING = 0.18     # % of revenue given back as discounts
LABOR_TO_TRAFFIC_HIGH = 1.35     # scheduled labor hours vs. a baseline traffic-implied need


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


def run_coo_synthesis():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.abspath(os.path.join(base_dir, "..", "data"))

    print(f"=== COO Synthesis [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ===")

    ops = load_json(os.path.join(data_dir, "ops_metrics.json"))
    audit_timestamp = datetime.now().strftime("%B %d, %Y %H:%M")

    # -------------------------------------------------------------------
    # 1. Inventory & Reorder (stockouts -- lost sales opportunity)
    # -------------------------------------------------------------------
    stockout_rate = ops.get("stockoutRate", 0.0) or 0.0
    stockout_skus = ops.get("stockoutSkuCount", 0) or 0

    inventory_items = []
    if stockout_rate >= STOCKOUT_RATE_CRITICAL:
        severity = "CRITICAL"
    elif stockout_rate >= STOCKOUT_RATE_WARNING:
        severity = "WARNING"
    else:
        severity = "OPTIMAL"
    inventory_items.append({
        "severity": severity,
        "title": "Stockout Rate",
        "metric": f"{stockout_rate*100:.1f}%",
        "description": f"{stockout_skus} SKUs hit zero on-hand at some point this window ({stockout_rate*100:.1f}% of tracked SKU-days).",
        "worth_considering": "Reorder points for these specific SKUs may be set below actual sell-through velocity." if severity != "OPTIMAL" else None,
    })

    # -------------------------------------------------------------------
    # 2. Pricing Health (discounting)
    # -------------------------------------------------------------------
    discount_rate = ops.get("discountRateOfRevenue", 0.0) or 0.0
    pricing_items = [{
        "severity": "WARNING" if discount_rate >= DISCOUNT_RATE_WARNING else "OPTIMAL",
        "title": "Discount Rate",
        "metric": f"{discount_rate*100:.1f}% of revenue",
        "description": f"Discounts and markdowns totaled {discount_rate*100:.1f}% of gross revenue this window.",
        "worth_considering": "Worth checking whether discounting is concentrated in a few categories (planned clearance) or spread broadly (a pricing or demand problem)." if discount_rate >= DISCOUNT_RATE_WARNING else None,
    }]

    # -------------------------------------------------------------------
    # 3. Staffing & Traffic
    # -------------------------------------------------------------------
    labor_to_traffic_ratio = ops.get("laborToTrafficRatio", 1.0) or 1.0
    staffing_items = [{
        "severity": "WARNING" if labor_to_traffic_ratio >= LABOR_TO_TRAFFIC_HIGH else "OPTIMAL",
        "title": "Scheduled Labor vs. Foot Traffic",
        "metric": f"{labor_to_traffic_ratio:.2f}x baseline",
        "description": f"Scheduled labor hours are running {labor_to_traffic_ratio:.2f}x what trailing foot-traffic patterns would suggest.",
        "worth_considering": "Worth a look at whether the schedule reflects last season's traffic rather than the current one." if labor_to_traffic_ratio >= LABOR_TO_TRAFFIC_HIGH else None,
    }]

    all_items = inventory_items + pricing_items + staffing_items
    all_items.sort(key=lambda x: SEVERITY_ORDER.get(x["severity"], 9))
    critical_or_warning = [i for i in all_items if i["severity"] in ("CRITICAL", "WARNING")]

    summary_bullets = [
        f"Stockout rate {stockout_rate*100:.1f}% ({stockout_skus} SKUs).",
        f"Discounting at {discount_rate*100:.1f}% of revenue.",
        f"Scheduled labor at {labor_to_traffic_ratio:.2f}x traffic-implied baseline.",
    ]

    payload = {
        "asOfDate": audit_timestamp,
        "audience": "owner (this reaches one person; they decide what, if anything, goes further)",
        "summary": summary_bullets,
        "needsAttention": critical_or_warning,
        "inventoryAndReorder": inventory_items,
        "pricingHealth": pricing_items,
        "staffingAndTraffic": staffing_items,
    }

    out_file = os.path.join(data_dir, "coo_synthesis.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print("\n--- COO Synthesis: what needs attention ---")
    if critical_or_warning:
        for item in critical_or_warning:
            print(f"[{item['severity']}] {item['title']}: {item['metric']}")
    else:
        print("Nothing crossed a CRITICAL/WARNING threshold this run.")
    print(f"\n[SUCCESS] COO synthesis written -> {out_file}")
    return payload


if __name__ == "__main__":
    run_coo_synthesis()
