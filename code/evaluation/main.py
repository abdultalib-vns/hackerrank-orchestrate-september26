"""
Evaluation Pipeline.
Evaluates agent predictions against public ground truth (dataset/sample_requests.csv).
Computes exact match and accuracy metrics across all required submission columns.
"""

import os
import sys
import pandas as pd
import numpy as np

# Ensure code root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
code_dir = os.path.dirname(current_dir)
if code_dir not in sys.path:
    sys.path.insert(0, code_dir)

from data_loader import FinancialDataLoader
from optimizer import evaluate_request

def run_evaluation(data_dir="dataset"):
    print("=" * 70)
    print("RUNNING FINANCIAL DECISION AGENT EVALUATION (Benchmark: sample_requests.csv)")
    print("=" * 70)
    
    loader = FinancialDataLoader(data_dir=data_dir)
    sample_df = loader.sample_requests_df
    
    if sample_df is None or len(sample_df) == 0:
        print("Error: No sample_requests.csv found in", data_dir)
        return
        
    predictions = []
    for idx, row in sample_df.iterrows():
        pred = evaluate_request(loader, row)
        predictions.append(pred)
        
    pred_df = pd.DataFrame(predictions)
    
    # Compare with ground truth
    total_samples = len(sample_df)
    
    # 1. Affordability Status Accuracy
    status_matches = sum(pred_df["affordability_status"] == sample_df["affordability_status"])
    status_acc = status_matches / total_samples
    
    # 2. Recommended Payment Method Accuracy
    method_matches = sum(pred_df["recommended_payment_method"] == sample_df["recommended_payment_method"])
    method_acc = method_matches / total_samples
    
    # 3. Safe to Pay MAE
    safe_diffs = np.abs(pred_df["amount_safe_to_pay"] - sample_df["amount_safe_to_pay"])
    safe_mae = np.mean(safe_diffs)
    
    # 4. Payment Plan Exact Match
    def norm_str(s):
        if pd.isna(s) or s is None or str(s).strip().lower() in ["nan", "none"]:
            return "none"
        return str(s).strip()
        
    plan_matches = sum(pred_df["payment_plan"].map(norm_str) == sample_df["payment_plan"].map(norm_str))
    plan_acc = plan_matches / total_samples
    
    # 5. Earliest Date Exact Match
    earliest_matches = sum(pred_df["earliest_date_for_full_payment"].map(norm_str) == sample_df["earliest_date_for_full_payment"].map(norm_str))
    earliest_acc = earliest_matches / total_samples
    
    # 6. Spending Changes Exact Match
    spending_matches = sum(pred_df["spending_changes_needed"].map(norm_str) == sample_df["spending_changes_needed"].map(norm_str))
    spending_acc = spending_matches / total_samples
    
    print("\n--- Summary Evaluation Metrics ---")
    print(f"Total Sample Benchmark Requests: {total_samples}")
    print(f"Affordability Status Accuracy:   {status_acc * 100:.1f}% ({status_matches}/{total_samples})")
    print(f"Payment Method Accuracy:         {method_acc * 100:.1f}% ({method_matches}/{total_samples})")
    print(f"Payment Plan Exact Match:        {plan_acc * 100:.1f}% ({plan_matches}/{total_samples})")
    print(f"Earliest Date Exact Match:       {earliest_acc * 100:.1f}% ({earliest_matches}/{total_samples})")
    print(f"Spending Changes Exact Match:    {spending_acc * 100:.1f}% ({spending_matches}/{total_samples})")
    print(f"Amount Safe to Pay MAE:          {safe_mae:.2f}")
    
    print("\n--- Detailed Per-Request Breakdown ---")
    for idx in range(total_samples):
        r_id = sample_df.iloc[idx]["request_id"]
        gt_s = sample_df.iloc[idx]["affordability_status"]
        pr_s = pred_df.iloc[idx]["affordability_status"]
        gt_m = sample_df.iloc[idx]["recommended_payment_method"]
        pr_m = pred_df.iloc[idx]["recommended_payment_method"]
        gt_p = norm_str(sample_df.iloc[idx]["payment_plan"])
        pr_p = norm_str(pred_df.iloc[idx]["payment_plan"])
        gt_safe = sample_df.iloc[idx]["amount_safe_to_pay"]
        pr_safe = pred_df.iloc[idx]["amount_safe_to_pay"]
        
        ok_flag = "PASS" if (gt_s == pr_s and gt_m == pr_m) else "FAIL"
        print(f"[{ok_flag:4}] {r_id:10} | Method: (pred={pr_m:15}, gt={gt_m:15}) | Status: (pred={pr_s:20}, gt={gt_s:20})")
        if ok_flag == "FAIL" or gt_p != pr_p:
            print(f"    GT Plan:   {gt_p}")
            print(f"    Pred Plan: {pr_p}")
            print(f"    GT Safe: {gt_safe:.2f} vs Pred Safe: {pr_safe:.2f}")
            
    print("=" * 70)
    return {
        "status_accuracy": status_acc,
        "method_accuracy": method_acc,
        "plan_accuracy": plan_acc,
        "earliest_accuracy": earliest_acc,
        "spending_accuracy": spending_acc,
        "safe_mae": safe_mae
    }

if __name__ == "__main__":
    run_evaluation()
