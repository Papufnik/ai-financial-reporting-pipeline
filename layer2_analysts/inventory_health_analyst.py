"""
inventory_health_analyst.py -- a Layer 2 "Analyst" in this pipeline (see
repo README for the full 4-layer architecture).

Analysts sit closest to the raw data. Each one owns a single domain, does
no cross-domain judgment, and outputs plain structured JSON -- no severity
labels, no "worth considering" language, no directives. That judgment
belongs to the Senior Manager layer above it, which reads this file's
output alongside other analysts' output before deciding what actually
needs attention.

This analyst answers one question: for each product category, how hard is
the inventory dollar sitting in it actually working? It computes GMROI
(Gross Margin Return on Inventory Investment) per category from sales/COGS
data plus a current inventory snapshot, and separately flags categories
with meaningful inventory but zero sales in the trailing window ("dead
stock" -- capital that's sitting on a shelf, not turning into revenue).

(Sanitized/simplified for this public demo. The production version this is
based on reads from a real point-of-sale export pipeline and a local SQL
warehouse rather than the synthetic CSV this demo generates, and carries
several more caveats specific to that business's seasonality. The
GMROI/dead-stock math itself is unchanged.)
"""

import csv
import json
import os
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

DEAD_STOCK_MIN_INVENTORY = 50.0  # ignore trivially small inventory positions when flagging dead stock


def load_category_sales(path):
    """category -> [net_sales, cogs, gross_profit]"""
    cat = defaultdict(lambda: [0.0, 0.0, 0.0])
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            net = float(row["net_sales"])
            cogs = float(row["cogs"])
            cat[row["category"]][0] += net
            cat[row["category"]][1] += cogs
            cat[row["category"]][2] += (net - cogs)
    return cat


def load_category_inventory(path):
    """category -> current inventory cost at time of snapshot"""
    inv = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            inv[row["category"]] = float(row["inventory_cost"])
    return inv


def run_inventory_health_analyst(period_days=90):
    sales_path = os.path.join(DATA_DIR, "category_sales.csv")
    inventory_path = os.path.join(DATA_DIR, "category_inventory.csv")

    cat_sales = load_category_sales(sales_path)
    cat_inventory = load_category_inventory(inventory_path)

    total_net = sum(v[0] for v in cat_sales.values())
    total_gp = sum(v[2] for v in cat_sales.values())
    total_inv_cost = sum(cat_inventory.values())
    overall_gmroi = (total_gp * (365 / period_days)) / total_inv_cost if total_inv_cost else 0.0

    categories = []
    dead_stock = []
    for name, (net, cogs, gp) in cat_sales.items():
        inv_cost = cat_inventory.get(name, 0.0)
        if inv_cost >= DEAD_STOCK_MIN_INVENTORY and net == 0:
            dead_stock.append({"category": name, "inventoryCost": round(inv_cost, 2)})
            continue
        if inv_cost <= 0:
            continue
        gmroi = (gp * (365 / period_days)) / inv_cost
        categories.append({
            "category": name,
            "netSales": round(net, 2),
            "grossProfit": round(gp, 2),
            "inventoryCost": round(inv_cost, 2),
            "gmroi": round(gmroi, 2),
        })

    categories.sort(key=lambda c: -c["gmroi"])
    dead_stock_cost = sum(d["inventoryCost"] for d in dead_stock)

    payload = {
        "asOfDate": f"trailing {period_days} days",
        "overall": round(overall_gmroi, 2),
        "totalInventoryCost": round(total_inv_cost, 2),
        "best": categories[:3],
        "worst": categories[-3:][::-1] if len(categories) > 3 else categories[::-1],
        "deadStockCost": round(dead_stock_cost, 2),
        "deadStockCount": len(dead_stock),
        "deadStockDetail": dead_stock,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    out_file = os.path.join(OUT_DIR, "inventory_health_live.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"[inventory_health_analyst] overall GMROI {payload['overall']}x, "
          f"dead stock ${payload['deadStockCost']:,.2f} across {payload['deadStockCount']} categories -> {out_file}")
    return payload


if __name__ == "__main__":
    run_inventory_health_analyst()
