"""
Interactive CLI for Buy or Wait? AI Financial Decision Agent.
Allows testing ad-hoc purchase requests for any user in dataset/.

Usage:
    python code/interactive.py
    python code/interactive.py --user user_01 --amount 15000 --date 2026-03-01 --desired 2026-03-31
"""

import sys
import os
import argparse
from datetime import datetime

# Ensure code directory in path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from data_loader import FinancialDataLoader
from optimizer import evaluate_request

def main():
    parser = argparse.ArgumentParser(description="Query Buy or Wait? AI Financial Decision Agent")
    parser.add_argument("--data_dir", default="dataset", help="Path to dataset directory")
    parser.add_argument("--user", default=None, help="User ID (e.g. user_01)")
    parser.add_argument("--amount", type=float, default=None, help="Requested expense amount")
    parser.add_argument("--date", default=None, help="Request date (YYYY-MM-DD)")
    parser.add_argument("--desired", default=None, help="Desired completion date (YYYY-MM-DD)")
    parser.add_argument("--partial", action="store_true", help="Seller allows partial payment")
    args = parser.parse_args()

    loader = FinancialDataLoader(data_dir=args.data_dir)

    print("=" * 70)
    print("BUY OR WAIT? — INTERACTIVE FINANCIAL ADVISOR")
    print("=" * 70)

    # Prompt user if arguments not provided
    user_id = args.user or input("Enter User ID [e.g. user_01]: ").strip()
    profile = loader.get_profile(user_id)
    if profile is None:
        print(f"Error: User '{user_id}' not found in {args.data_dir}/financial_profiles.csv")
        return

    currency = profile.get("home_currency", "USD")
    balance = float(profile.get("current_available_balance", 0.0))
    min_bal = float(profile.get("minimum_balance_to_keep", 0.0))

    print(f"\nUser Profile Loaded:")
    print(f"  * Home Currency:       {currency}")
    print(f"  * Available Balance:   {currency} {balance:,.2f}")
    print(f"  * Minimum Balance:     {currency} {min_bal:,.2f}")
    print(f"  * Usable Buffer:       {currency} {balance - min_bal:,.2f}")
    print(f"  * Priorities:          {profile.get('financial_priorities', 'None')}")
    print(f"  * Protected Spending:  {profile.get('expense_categories_to_protect', 'None')}")
    print(f"  * Willing to Reduce:   {profile.get('expense_categories_user_is_willing_to_reduce', 'None')}")
    print(f"  * Willing to Stop:     {profile.get('expense_categories_user_is_willing_to_stop', 'None')}")

    amt = args.amount
    if amt is None:
        amt_in = input(f"\nEnter requested expense amount in {currency}: ").strip()
        amt = float(amt_in)

    def normalize_date(d_str, default_val="2026-03-01"):
        if not d_str:
            return default_val
        d_str = d_str.strip()
        formats = [
            "%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y",
            "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(d_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
        return d_str

    raw_req = args.date or input("Enter request date (YYYY-MM-DD) [default today: 2026-03-01]: ").strip() or "2026-03-01"
    req_date = normalize_date(raw_req, "2026-03-01")

    raw_des = args.desired or input(f"Enter desired completion date (YYYY-MM-DD) [default {req_date}]: ").strip() or req_date
    desired_date = normalize_date(raw_des, req_date)

    req_dict = {
        "request_id": f"query_{user_id}_{int(datetime.now().timestamp())}",
        "user_id": user_id,
        "request_date": req_date,
        "requested_amount": amt,
        "desired_completion_date": desired_date,
        "allows_partial_payment": args.partial
    }

    print("\nAnalyzing cashflow trajectories, recurring commitments, and risk rules...")
    decision = evaluate_request(loader, req_dict)

    print("\n" + "=" * 70)
    print("FINANCIAL AGENT RECOMMENDATION")
    print("=" * 70)
    print(f"Affordability Status:       {decision['affordability_status'].upper()}")
    print(f"Recommended Payment Method: {decision['recommended_payment_method'].upper()}")
    print(f"Amount Safe to Pay Today:   {currency} {decision['amount_safe_to_pay']:,.2f}")
    print(f"Payment Schedule Plan:      {decision['payment_plan']}")
    print(f"Earliest Safe Full Payment: {decision['earliest_date_for_full_payment'] or 'N/A'}")
    print(f"Required Spending Changes:  {decision['spending_changes_needed']}")
    print(f"\nDecision Rationale:")
    print(f"  \"{decision['decision_explanation']}\"")
    print("=" * 70)

if __name__ == "__main__":
    main()
