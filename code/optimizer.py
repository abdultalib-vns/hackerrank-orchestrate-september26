"""
Affordability & Decision Optimizer Module.
Evaluates financial requests against daily cashflow trajectories, generates candidate plans,
applies the ranking hierarchy, and produces compliant decision outputs.
"""

from datetime import datetime, timedelta
import pandas as pd
import numpy as np

try:
    from .forecaster import project_daily_cashflow
    from .ranker import rank_candidates
    from .explainer import generate_decision_explanation
except ImportError:
    from forecaster import project_daily_cashflow
    from ranker import rank_candidates
    from explainer import generate_decision_explanation

def find_candidate_spending_changes(loader, user_id):
    """
    Identifies non-protected flexible recurring expenses eligible for reduction or cancellation.
    """
    profile = loader.get_profile(user_id)
    user_events = loader.get_user_events(user_id)
    
    stop_cats = set(str(profile["expense_categories_user_is_willing_to_stop"]).split("|")) if pd.notna(profile["expense_categories_user_is_willing_to_stop"]) else set()
    reduce_cats = set(str(profile["expense_categories_user_is_willing_to_reduce"]).split("|")) if pd.notna(profile["expense_categories_user_is_willing_to_reduce"]) else set()
    protect_cats = set(str(profile["expense_categories_to_protect"]).split("|")) if pd.notna(profile["expense_categories_to_protect"]) else set()
    
    stop_cats = stop_cats - protect_cats
    reduce_cats = reduce_cats - protect_cats
    
    candidates = []
    for (cat, desc), group in user_events[user_events["direction"] == "debit"].groupby(["category", "description"]):
        settled = group[group["status"] == "settled"]
        if len(settled) == 0:
            continue
            
        last_ev = settled.iloc[-1]
        ev_id = str(last_ev["event_id"]).strip()
        flex = str(last_ev["flexibility"]).strip()
        amt = float(last_ev["home_amount"])
        min_allowed = float(last_ev["minimum_allowed_amount"]) if pd.notna(last_ev["minimum_allowed_amount"]) else None
        
        if cat in stop_cats and flex in ["stoppable", "reducible_or_stoppable"]:
            candidates.append({
                "type": "stop",
                "event_id": ev_id,
                "category": cat,
                "description": desc,
                "new_amount": 0.0,
                "savings": amt,
                "spec": f"stop:{ev_id}",
                "text": f"Stop the {desc.lower()}"
            })
            
        if cat in reduce_cats and flex in ["reducible", "reducible_or_stoppable"] and min_allowed is not None:
            if amt > min_allowed:
                savings = amt - min_allowed
                # format new amount without decimals if int
                new_amt_str = f"{int(min_allowed)}" if min_allowed.is_integer() else f"{min_allowed:.2f}"
                candidates.append({
                    "type": "reduce_to",
                    "event_id": ev_id,
                    "category": cat,
                    "description": desc,
                    "new_amount": min_allowed,
                    "savings": savings,
                    "spec": f"reduce_to:{ev_id}:{new_amt_str}",
                    "text": f"Reduce the {desc.lower()} to {loader.user_home_currencies.get(user_id, '')} {new_amt_str}"
                })
                
    return candidates

def evaluate_request(loader, request_row):
    """
    Evaluates a single financial request and returns the completed output fields.
    """
    req_id = str(request_row["request_id"]).strip()
    u_id = str(request_row["user_id"]).strip()
    req_date_str = str(request_row["request_date"]).strip()
    req_amt = float(request_row["requested_amount"])
    desired_date_str = str(request_row["desired_completion_date"]).strip()
    allows_partial = str(request_row["allows_partial_payment"]).strip().lower() in ["true", "1", "yes"]
    
    profile = loader.get_profile(u_id)
    currency = str(profile["home_currency"]).strip()
    min_bal = float(profile["minimum_balance_to_keep"])
    
    considered_methods = set(str(profile["payment_methods_user_will_consider"]).split("|"))
    max_inst_months = float(profile["max_installment_months"]) if pd.notna(profile["max_installment_months"]) else None
    
    # 1. Base 90-day cash trajectory (without spending changes)
    base_traj, _, _ = project_daily_cashflow(loader, u_id, req_date_str, spending_changes=None)
    min_buffer = min(base_traj.values()) - min_bal
    amount_safe_to_pay = max(0.0, min(req_amt, min_buffer))
    # Round amount_safe_to_pay to 2 decimal places
    amount_safe_to_pay = round(amount_safe_to_pay, 2)
    
    # If within 1.5% of req_amt, full payment today is affordable
    is_affordable_now = (amount_safe_to_pay >= req_amt - 1e-4)
    if is_affordable_now:
        amount_safe_to_pay = req_amt
    
    # 2. Earliest safe date for one full payment without spending changes
    earliest_date_for_full_payment = None
    sorted_days = sorted(base_traj.keys())
    desired_dt = datetime.strptime(desired_date_str, "%Y-%m-%d")
    for d in sorted_days:
        is_safe = True
        check_limit = min(sorted_days[-1], max(d + timedelta(days=15), desired_dt))
        for t in sorted_days:
            if d <= t <= check_limit:
                if base_traj[t] - req_amt < min_bal - 1e-4:
                    is_safe = False
                    break
        if is_safe:
            earliest_date_for_full_payment = d.strftime("%Y-%m-%d")
            break
            
    def fmt_amt(val):
        val = round(val, 2)
        if abs(val - round(val)) < 1e-4:
            return f"{int(round(val))}"
        return f"{val:.2f}"

    # 3. Generate Candidate Plans
    candidates = []
    
    # Candidate 1: Full Payment Today
    if "full_payment" in considered_methods:
        if is_affordable_now:
            candidates.append({
                "affordability_status": "affordable_now",
                "recommended_payment_method": "full_payment",
                "payment_plan": f"{req_date_str}:{fmt_amt(req_amt)}",
                "earliest_date_for_full_payment": req_date_str,
                "spending_changes_needed": "none",
                "spending_desc": None,
                "first_payment_date": req_date_str,
                "last_payment_date": req_date_str,
                "total_amount_paid": req_amt,
                "number_of_payments": 1,
                "payment_option_id": ""
            })
            
    # Candidate 2: Partial Payment
    if "partial_payment" in considered_methods and allows_partial:
        if 0 < amount_safe_to_pay < req_amt and earliest_date_for_full_payment:
            if earliest_date_for_full_payment <= desired_date_str:
                p1 = amount_safe_to_pay
                p2 = round(req_amt - p1, 2)
                plan_str = f"{req_date_str}:{fmt_amt(p1)}|{earliest_date_for_full_payment}:{fmt_amt(p2)}"
                candidates.append({
                    "affordability_status": "affordable_with_plan",
                    "recommended_payment_method": "partial_payment",
                    "payment_plan": plan_str,
                    "earliest_date_for_full_payment": earliest_date_for_full_payment,
                    "spending_changes_needed": "none",
                    "spending_desc": None,
                    "first_payment_date": req_date_str,
                    "last_payment_date": earliest_date_for_full_payment,
                    "total_amount_paid": req_amt,
                    "number_of_payments": 2,
                    "payment_option_id": ""
                })
                
    # Candidate 3: Installment Options
    options_df = loader.get_request_options(req_id)
    if "installments" in considered_methods and len(options_df) > 0:
        for _, opt in options_df.iterrows():
            if str(opt["payment_method"]).strip() != "installments":
                continue
                
            num_pmts = int(opt["number_of_payments"])
            pmt_amt = float(opt["payment_amount"])
            freq_days = float(opt["payment_frequency_days"]) if pd.notna(opt["payment_frequency_days"]) else 30.0
            first_p_str = str(opt["first_payment_date"]).strip()
            total_payable = float(opt["total_payable_amount"])
            opt_id = str(opt["payment_option_id"]).strip()
            
            # Check max installment months
            duration_months = (num_pmts * freq_days) / 30.0
            if max_inst_months is not None and duration_months > max_inst_months + 0.5:
                continue
                
            first_dt = datetime.strptime(first_p_str, "%Y-%m-%d")
            pmt_dates = [first_dt + timedelta(days=int(k * freq_days)) for k in range(num_pmts)]
            last_pmt_dt = pmt_dates[-1]
            last_pmt_str = last_pmt_dt.strftime("%Y-%m-%d")
            
            # Simulate installment schedule against base daily cashflow
            # Check if balance stays >= min_bal on every day throughout active duration
            inst_safe = True
            cum_pmt = 0.0
            p_idx = 0
            check_end_dt = max(last_pmt_dt, desired_dt)
            for d in sorted_days:
                if d > check_end_dt:
                    break
                while p_idx < len(pmt_dates) and pmt_dates[p_idx] <= d:
                    cum_pmt += pmt_amt
                    p_idx += 1
                if base_traj[d] - cum_pmt < min_bal - 1e-4:
                    inst_safe = False
                    break
                    
            if inst_safe:
                plan_str = "|".join(f"{p_dt.strftime('%Y-%m-%d')}:{fmt_amt(pmt_amt)}" for p_dt in pmt_dates)
                candidates.append({
                    "affordability_status": "affordable_with_plan",
                    "recommended_payment_method": "installments",
                    "payment_plan": plan_str,
                    "earliest_date_for_full_payment": earliest_date_for_full_payment,
                    "spending_changes_needed": "none",
                    "spending_desc": None,
                    "first_payment_date": first_p_str,
                    "last_payment_date": last_pmt_str,
                    "total_amount_paid": total_payable,
                    "number_of_payments": num_pmts,
                    "payment_option_id": opt_id,
                    "payment_amount": pmt_amt
                })

    # Candidate 4: Spending Changes (if needed to make full payment safe today)
    # Only test if full payment is not yet affordable today
    if "full_payment" in considered_methods and not is_affordable_now:
        spend_cands = find_candidate_spending_changes(loader, u_id)
        if spend_cands:
            tol = max(20.0, 0.05 * req_amt)
            valid_change_combos = []
            
            # Single
            for sc in spend_cands:
                # Test trajectory with this change
                chg_tuples = [(sc["type"], sc["event_id"], sc["new_amount"])]
                traj_c, _, _ = project_daily_cashflow(loader, u_id, req_date_str, spending_changes=chg_tuples)
                if min(traj_c.values()) - min_bal >= req_amt - tol:
                    valid_change_combos.append(([sc], sc["spec"], sc["text"]))
                    
            # Pairs (if no single change works)
            if not valid_change_combos and len(spend_cands) >= 2:
                for i in range(len(spend_cands)):
                    for j in range(i + 1, len(spend_cands)):
                        sc1 = spend_cands[i]
                        sc2 = spend_cands[j]
                        if sc1["event_id"] == sc2["event_id"]:
                            continue
                        chg_tuples = [
                            (sc1["type"], sc1["event_id"], sc1["new_amount"]),
                            (sc2["type"], sc2["event_id"], sc2["new_amount"])
                        ]
                        traj_c, _, _ = project_daily_cashflow(loader, u_id, req_date_str, spending_changes=chg_tuples)
                        if min(traj_c.values()) - min_bal >= req_amt - tol:
                            spec_str = f"{sc1['spec']}|{sc2['spec']}"
                            desc_str = f"{sc1['text']} and {sc2['text'][:1].lower() + sc2['text'][1:]}"
                            valid_change_combos.append(([sc1, sc2], spec_str, desc_str))
                            
            if valid_change_combos:
                # Pick the combination with minimal total reduction
                best_combo = valid_change_combos[0]
                spec_str = best_combo[1]
                desc_str = best_combo[2]
                candidates.append({
                    "affordability_status": "affordable_with_plan",
                    "recommended_payment_method": "full_payment",
                    "payment_plan": f"{req_date_str}:{fmt_amt(req_amt)}",
                    "earliest_date_for_full_payment": earliest_date_for_full_payment or req_date_str,
                    "spending_changes_needed": spec_str,
                    "spending_desc": desc_str,
                    "first_payment_date": req_date_str,
                    "last_payment_date": req_date_str,
                    "total_amount_paid": req_amt,
                    "number_of_payments": 1,
                    "payment_option_id": ""
                })

    # Candidate 5: Wait
    if "full_payment" in considered_methods and earliest_date_for_full_payment:
        candidates.append({
            "affordability_status": "affordable_later",
            "recommended_payment_method": "wait",
            "payment_plan": f"{earliest_date_for_full_payment}:{fmt_amt(req_amt)}",
            "earliest_date_for_full_payment": earliest_date_for_full_payment,
            "spending_changes_needed": "none",
            "spending_desc": None,
            "first_payment_date": earliest_date_for_full_payment,
            "last_payment_date": earliest_date_for_full_payment,
            "total_amount_paid": req_amt,
            "number_of_payments": 1,
            "payment_option_id": ""
        })
        
        
    # Candidate 6: Not Recommended (fallback)
    fallback = {
        "affordability_status": "not_affordable",
        "recommended_payment_method": "not_recommended",
        "payment_plan": "none",
        "earliest_date_for_full_payment": earliest_date_for_full_payment if earliest_date_for_full_payment else "",
        "spending_changes_needed": "none",
        "spending_desc": None,
        "first_payment_date": None,
        "last_payment_date": None,
        "total_amount_paid": 1e12,
        "number_of_payments": 999,
        "payment_option_id": ""
    }
    
    # 4. Select the best plan via ranking
    if candidates:
        chosen_plan = rank_candidates(candidates, desired_date_str)
        # If the chosen plan does not complete by desired date and wait was selected, check if not_recommended should apply
        if chosen_plan["recommended_payment_method"] == "wait":
            if chosen_plan["last_payment_date"] > desired_date_str:
                # Wait completes after desired date -> not affordable by deadline!
                chosen_plan = fallback
    else:
        chosen_plan = fallback

    # 5. Generate Explanation
    explanation = generate_decision_explanation(
        recommendation=chosen_plan,
        currency=currency,
        requested_amount=req_amt,
        min_balance=min_bal,
        amount_safe_to_pay=amount_safe_to_pay,
        earliest_date_for_full_payment=chosen_plan.get("earliest_date_for_full_payment", ""),
        desired_completion_date=desired_date_str,
        spending_changes_desc=chosen_plan.get("spending_desc")
    )
    
    # Output formatting
    earliest_out = chosen_plan.get("earliest_date_for_full_payment", "")
    if earliest_out is None or pd.isna(earliest_out):
        earliest_out = ""
        
    return {
        "request_id": req_id,
        "amount_safe_to_pay": amount_safe_to_pay,
        "affordability_status": chosen_plan["affordability_status"],
        "recommended_payment_method": chosen_plan["recommended_payment_method"],
        "payment_plan": chosen_plan["payment_plan"],
        "earliest_date_for_full_payment": earliest_out,
        "spending_changes_needed": chosen_plan["spending_changes_needed"],
        "decision_explanation": explanation
    }
