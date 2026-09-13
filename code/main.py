"""
Buy or Wait? — AI-Powered Financial Decision Agent
Main Entry Point.

Reads dataset from `dataset/`, evaluates each financial request in `dataset/requests.csv`,
and writes the compliant predictions to `output.csv`.

Usage:
    python code/main.py [--data_dir dataset] [--output output.csv]
"""

import os
import sys
import argparse
import time
import pandas as pd

# Add code directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from data_loader import FinancialDataLoader
from optimizer import evaluate_request

def main():
    parser = argparse.ArgumentParser(description="Buy or Wait? Financial Decision Agent")
    parser.add_argument("--data_dir", default="dataset", help="Directory containing challenge dataset CSVs")
    parser.add_argument("--output", default="output.csv", help="Path for output predictions CSV")
    args = parser.parse_args()

    start_time = time.time()
    print("=" * 70)
    print("BUY OR WAIT? FINANCIAL DECISION AGENT")
    print(f"Loading data from: {args.data_dir}")
    print("=" * 70)

    loader = FinancialDataLoader(data_dir=args.data_dir)
    requests_df = loader.requests_df

    if requests_df is None or len(requests_df) == 0:
        print(f"Error: No requests found in {args.data_dir}/requests.csv")
        sys.exit(1)

    total_requests = len(requests_df)
    print(f"Loaded {total_requests} evaluation requests from {args.data_dir}/requests.csv.")
    print("Evaluating financial positions and generating safe recommendations...")

    results = []
    for idx, row in requests_df.iterrows():
        req_id = row["request_id"]
        pred = evaluate_request(loader, row)
        results.append(pred)
        if (idx + 1) % 50 == 0 or (idx + 1) == total_requests:
            print(f"  Processed {idx + 1}/{total_requests} requests...")

    output_df = pd.DataFrame(results)

    # Ensure required schema and column order
    required_columns = [
        "request_id",
        "amount_safe_to_pay",
        "affordability_status",
        "recommended_payment_method",
        "payment_plan",
        "earliest_date_for_full_payment",
        "spending_changes_needed",
        "decision_explanation"
    ]
    output_df = output_df[required_columns]

    # Fill NaNs or empties consistently
    output_df["earliest_date_for_full_payment"] = output_df["earliest_date_for_full_payment"].fillna("")
    output_df["payment_plan"] = output_df["payment_plan"].fillna("none")
    output_df["spending_changes_needed"] = output_df["spending_changes_needed"].fillna("none")

    # Save to primary output.csv
    output_path = args.output
    output_df.to_csv(output_path, index=False)
    print(f"\nSuccessfully wrote {len(output_df)} predictions to: {output_path}")

    # Also save to dataset/output.csv for safety if different
    ds_output_path = os.path.join(args.data_dir, "output.csv")
    if os.path.abspath(output_path) != os.path.abspath(ds_output_path):
        output_df.to_csv(ds_output_path, index=False)
        print(f"Also synced predictions to template at: {ds_output_path}")

    elapsed = time.time() - start_time
    print(f"\nCompleted evaluation of {total_requests} requests in {elapsed:.2f}s ({elapsed/total_requests:.3f}s/req).")

    print("\n--- Summary Distribution ---")
    print("Affordability Status:")
    print(output_df["affordability_status"].value_counts().to_string())
    print("\nRecommended Payment Method:")
    print(output_df["recommended_payment_method"].value_counts().to_string())
    print("=" * 70)

if __name__ == "__main__":
    main()
