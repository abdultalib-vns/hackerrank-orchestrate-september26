"""
Decision Explainer Module.
Generates concise, grounded natural language explanations justifying the financial recommendation.
Conforms directly to the stylistic precedents in sample_requests.csv.
"""

from datetime import datetime
import pandas as pd

def format_amount(amount):
    """Formats numeric amounts cleanly without trailing zeros if integer."""
    if amount is None or pd.isna(amount):
        return "0"
    val = float(amount)
    if val.is_integer():
        return f"{int(val):,}"
    # Otherwise format with up to 2 decimal places
    s = f"{val:,.2f}"
    if s.endswith(".00"):
        return s[:-3]
    return s

def format_date_natural(date_str):
    """Converts 'YYYY-MM-DD' to natural format e.g. '8 August 2025' or '15 November 2019'."""
    if not date_str or date_str == "none" or pd.isna(date_str):
        return ""
    try:
        dt = datetime.strptime(str(date_str).strip(), "%Y-%m-%d")
        day = dt.day
        month = dt.strftime("%B")
        year = dt.year
        return f"{day} {month} {year}"
    except:
        return str(date_str)

def generate_decision_explanation(
    recommendation,
    currency,
    requested_amount,
    min_balance,
    amount_safe_to_pay,
    earliest_date_for_full_payment,
    desired_completion_date,
    spending_changes_desc=None
):
    method = recommendation.get("recommended_payment_method")
    curr = str(currency).strip()
    req_amt_fmt = format_amount(requested_amount)
    min_bal_fmt = format_amount(min_balance)
    safe_amt_fmt = format_amount(amount_safe_to_pay)
    deadline_fmt = format_date_natural(desired_completion_date)
    earliest_fmt = format_date_natural(earliest_date_for_full_payment)
    
    if method == "full_payment":
        if spending_changes_desc:
            return f"{spending_changes_desc}, then pay {curr} {req_amt_fmt} today. This leaves at least {curr} {min_bal_fmt} available."
        return f"Pay {curr} {req_amt_fmt} today. This leaves at least {curr} {min_bal_fmt} available over the next 90 days."
        
    elif method == "installments":
        num_inst = recommendation.get("number_of_payments", "")
        inst_amt_fmt = format_amount(recommendation.get("payment_amount", 0.0))
        first_date_fmt = format_date_natural(recommendation.get("first_payment_date", ""))
        prefix = f"{spending_changes_desc}, then use" if spending_changes_desc else "Use"
        return f"{prefix} {num_inst} installments of {curr} {inst_amt_fmt}, starting {first_date_fmt}. This leaves at least {curr} {min_bal_fmt} available."
        
    elif method == "partial_payment":
        plan_str = recommendation.get("payment_plan", "")
        # Format: d1:p1|d2:p2
        tokens = plan_str.split("|")
        p1 = float(tokens[0].split(":")[1])
        p2 = float(tokens[1].split(":")[1])
        p2_date_fmt = format_date_natural(tokens[1].split(":")[0])
        return (
            f"Pay {curr} {format_amount(p1)} today and the remaining {curr} {format_amount(p2)} on {p2_date_fmt}. "
            f"This completes the full request and keeps the {curr} {min_bal_fmt} minimum protected."
        )
        
    elif method == "wait":
        return f"Pay {curr} {req_amt_fmt} in full on {earliest_fmt}. Paying earlier would take the balance below the {curr} {min_bal_fmt} minimum."
        
    else: # not_recommended
        if not earliest_date_for_full_payment or pd.isna(earliest_date_for_full_payment) or str(earliest_date_for_full_payment).lower() in ["nan", "none"]:
            if amount_safe_to_pay > 0:
                return f"Do not proceed with the {curr} {req_amt_fmt} request. Although {curr} {safe_amt_fmt} is available today, the full amount cannot be completed safely within 90 days."
            return f"Do not make this payment by {deadline_fmt}. None of the available options keeps the {curr} {min_bal_fmt} minimum protected."
        return f"Do not make this payment by {deadline_fmt}. None of the available options keeps the {curr} {min_bal_fmt} minimum protected."
