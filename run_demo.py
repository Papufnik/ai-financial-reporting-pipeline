"""
run_demo.py -- runs the full 4-layer pipeline end to end against synthetic
data, so anyone cloning this repo can see the whole thing work without any
real business's data, credentials, or POS connection.

Layer 1  (not included -- real ingestion/ETL is business-specific)
Layer 2  layer2_analysts/        -- single-domain analysts, plain JSON out
Layer 3  layer3_senior_managers/ -- CFO + COO synthesis, thresholds + severity
Layer 4  layer4_capstone/        -- CEO weekly memo, reads only Layer 3 output

Run: python run_demo.py
"""

import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "layer2_analysts"))
sys.path.insert(0, os.path.join(BASE, "layer3_senior_managers"))
sys.path.insert(0, os.path.join(BASE, "layer4_capstone"))

import generate_synthetic_data
from inventory_health_analyst import run_inventory_health_analyst
from cash_forecast_analyst import run_cash_forecast_analyst
from cfo_synthesis import run_cfo_synthesis
from coo_synthesis import run_coo_synthesis
from ceo_weekly_memo import run_ceo_memo


def main():
    print("############################################")
    print("# 0. Generating synthetic data (no real business data)")
    print("############################################\n")
    generate_synthetic_data.main()

    print("\n############################################")
    print("# Layer 2: Analysts")
    print("############################################\n")
    run_inventory_health_analyst()
    print()
    run_cash_forecast_analyst()

    print("\n############################################")
    print("# Layer 3: Senior Managers (CFO / COO)")
    print("############################################\n")
    run_cfo_synthesis()
    print()
    run_coo_synthesis()

    print("\n############################################")
    print("# Layer 4: CEO Capstone")
    print("############################################\n")
    run_ceo_memo()

    print("\n############################################")
    print("# Done. See data/ceo_weekly_memo.md for the final output.")
    print("############################################")


if __name__ == "__main__":
    main()
