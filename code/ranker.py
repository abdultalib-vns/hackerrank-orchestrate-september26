"""
Plan Ranker Module.
Implements the challenge's strict 6-level tie-breaking hierarchy:
1. Complete the full request by desired_completion_date.
2. Require no spending changes.
3. Minimize the total amount paid.
4. Start payment earlier.
5. Use fewer payments.
6. Use the lowest payment_option_id as the final tie-breaker.
"""

from datetime import datetime

def score_plan(candidate, desired_completion_date_str):
    """
    Computes a comparable tuple for sorting candidate plans.
    Lower tuple is better.
    """
    desired_date = datetime.strptime(desired_completion_date_str, "%Y-%m-%d")
    
    # 1. Complete the full request by desired_completion_date
    # boolean: 0 if completes on/before desired_date, 1 if later
    last_payment_date = candidate.get("last_payment_date")
    if last_payment_date is None:
        completes_on_time = 1
    else:
        last_dt = datetime.strptime(last_payment_date, "%Y-%m-%d") if isinstance(last_payment_date, str) else last_payment_date
        completes_on_time = 0 if last_dt <= desired_date else 1
        
    # 2. Require no spending changes
    # 0 if no spending changes, 1 if spending changes required
    has_spending_changes = 0 if candidate.get("spending_changes_needed", "none") == "none" else 1
    
    # 3. Minimize total amount paid
    total_paid = float(candidate.get("total_amount_paid", 1e12))
    
    # 4. Start payment earlier
    first_payment_date = candidate.get("first_payment_date")
    if first_payment_date is None:
        start_date_val = datetime(2099, 1, 1)
    else:
        start_date_val = datetime.strptime(first_payment_date, "%Y-%m-%d") if isinstance(first_payment_date, str) else first_payment_date
        
    # 5. Use fewer payments
    num_payments = int(candidate.get("number_of_payments", 999))
    
    # 6. Lowest payment_option_id as final tie-breaker
    # e.g. "payment_option_05" -> 5. If none, large number
    opt_id_str = candidate.get("payment_option_id", "")
    opt_num = 999999
    if opt_id_str and "payment_option_" in opt_id_str:
        try:
            opt_num = int(opt_id_str.split("_")[-1])
        except:
            opt_num = 999999

    # Status preference: affordable_now < affordable_with_plan < affordable_later < not_affordable
    status = candidate.get("affordability_status", "not_affordable")
    status_order = {
        "affordable_now": 0,
        "affordable_with_plan": 1,
        "affordable_later": 2,
        "not_affordable": 3
    }
    status_rank = status_order.get(status, 4)

    return (
        completes_on_time,
        status_rank,
        has_spending_changes,
        round(total_paid, 2),
        start_date_val,
        num_payments,
        opt_num
    )

def rank_candidates(candidates, desired_completion_date_str):
    """
    Sorts candidate plans according to the challenge rules and returns the top plan.
    """
    if not candidates:
        return None
    return sorted(candidates, key=lambda c: score_plan(c, desired_completion_date_str))[0]
