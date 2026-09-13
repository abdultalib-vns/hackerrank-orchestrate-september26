"""
Forecaster Module.
Constructs daily cashflow forecasts over the 90-day evaluation horizon.
Accurately detects recurring income and expenses, accounts for pending/failed debits,
applies natural language amendments from messages, and calculates minimum balance buffers.
"""

import calendar
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

def project_daily_cashflow(loader, user_id, req_date_str, spending_changes=None):
    """
    Simulates the 90-day daily cashflow trajectory for a user starting on req_date_str.
    Returns:
        balances: dict of date -> running balance
        min_bal_to_keep: float minimum required reserve
        daily_delta: dict of date -> net cashflow change on that day
    """
    if spending_changes is None:
        spending_changes = []
        
    stop_ids = {item[1] for item in spending_changes if item[0] == "stop"}
    reduce_map = {item[1]: float(item[2]) for item in spending_changes if item[0] == "reduce_to"}
    
    profile = loader.get_profile(user_id)
    initial_balance = float(profile["current_available_balance"])
    min_bal_to_keep = float(profile["minimum_balance_to_keep"])
    
    req_date = datetime.strptime(req_date_str, "%Y-%m-%d")
    end_date = req_date + timedelta(days=90)
    
    user_events = loader.get_user_events(user_id)
    msg_info = loader.get_user_message_info(user_id)
    
    # Initialize daily flow dictionary for 0 to 90 days
    daily_delta = {req_date + timedelta(days=i): 0.0 for i in range(91)}
    
    # 1. Pending & Scheduled debits / one-off events
    for _, ev in user_events.iterrows():
        ev_id = str(ev["event_id"]).strip()
        s_date_str = str(ev["settlement_date"]).strip()
        if s_date_str == "nan" or not s_date_str:
            s_date_str = str(ev["event_date"]).strip()
        try:
            s_date = datetime.strptime(s_date_str, "%Y-%m-%d")
        except:
            continue
            
        direction = str(ev["direction"]).strip()
        status = str(ev["status"]).strip()
        event_type = str(ev["event_type"]).strip()
        category = str(ev["category"]).strip()
        desc = str(ev["description"]).strip().lower()
        
        is_pending_debit = (direction == "debit" and status == "pending")
        is_failed_active = (ev_id in msg_info["failed_debits_active"])
        is_scheduled_debit = (direction == "debit" and status == "scheduled")
        
        if is_pending_debit or is_failed_active or is_scheduled_debit:
            if req_date <= s_date <= end_date:
                amt = float(ev["home_amount"])
                if ev_id in stop_ids:
                    amt = 0.0
                elif ev_id in reduce_map:
                    amt = reduce_map[ev_id]
                daily_delta[s_date] -= amt
                
        # Confirmed scheduled salary
        if status == "scheduled" and direction == "credit" and category == "salary":
            if req_date <= s_date <= end_date and not msg_info["contract_ended"]:
                amt = float(ev["home_amount"])
                if msg_info["salary_override"] is not None:
                    amt = float(msg_info["salary_override"])
                daily_delta[s_date] += amt

    # 2. Confirmed Recurring Salary Schedule
    # Only regular employer salary recurs; gig/platform earnings or unconfirmed credits do not
    settled_salary = user_events[
        (user_events["category"] == "salary") & 
        (user_events["status"] == "settled") &
        (~user_events["description"].str.lower().str.contains("final")) &
        (~user_events["description"].str.lower().str.contains("bonus")) &
        (~user_events["description"].str.lower().str.contains("arrears"))
    ].sort_values("settlement_date")
    
    # Check if final payroll occurred
    has_final_payroll = any(
        "final" in str(d).lower() for d in user_events[user_events["category"] == "salary"]["description"]
    )
    
    # Check if this user is a delivery/gig driver with non-confirmed regular salary (e.g. user_10)
    is_gig_worker = any(
        any(k in str(d).lower() for k in ["delivery platform", "marketplace payout", "driver platform", "weekly app earnings"])
        for d in user_events[user_events["category"] == "salary"]["description"]
    )
    
    if not msg_info["contract_ended"] and not has_final_payroll and not is_gig_worker and len(settled_salary) > 0:
        sal_days = [datetime.strptime(d, "%Y-%m-%d").day for d in settled_salary["settlement_date"]]
        vals, counts = np.unique(sal_days, return_counts=True)
        primary_day = vals[np.argmax(counts)]
        
        # Determine active regular salary days (only days present in the most recent salary month)
        latest_sal_date = datetime.strptime(settled_salary.iloc[-1]["settlement_date"], "%Y-%m-%d")
        latest_sal_month_rows = settled_salary[
            settled_salary["settlement_date"].str.startswith(latest_sal_date.strftime("%Y-%m"))
        ]
        latest_month_days = set(datetime.strptime(d, "%Y-%m-%d").day for d in latest_sal_month_rows["settlement_date"])
        
        distinct_frequent_days = [v for v, c in zip(vals, counts) if c >= 2 and v in latest_month_days]
        if len(distinct_frequent_days) >= 2:
            target_days = sorted(distinct_frequent_days)
        else:
            target_days = [primary_day]
            
        if msg_info["salary_date_override"]:
            target_days = [datetime.strptime(msg_info["salary_date_override"], "%Y-%m-%d").day]
            
        last_salary_row = settled_salary.iloc[-1]
        base_sal_amt = float(last_salary_row["home_amount"])
        if msg_info["salary_override"] is not None:
            base_sal_amt = float(msg_info["salary_override"])
            
        # Project monthly salary events forward across the 90 days
        cur = req_date
        while cur <= end_date:
            max_d = calendar.monthrange(cur.year, cur.month)[1]
            for td in target_days:
                sal_dt = datetime(cur.year, cur.month, min(td, max_d))
                if req_date <= sal_dt <= end_date:
                    # Check if scheduled salary already accounted for this date
                    already_scheduled = any(
                        se["settlement_date"] == sal_dt.strftime("%Y-%m-%d") and se["status"] == "scheduled"
                        for _, se in user_events[user_events["category"] == "salary"].iterrows()
                    )
                    if not already_scheduled:
                        daily_delta[sal_dt] += base_sal_amt
            if cur.month == 12:
                cur = datetime(cur.year + 1, 1, 1)
            else:
                cur = datetime(cur.year, cur.month + 1, 1)
                
    # One-time confirmed arrears adjustments
    for arr_dt_str, arr_amt in msg_info["one_time_credits"]:
        if arr_dt_str:
            arr_dt = datetime.strptime(arr_dt_str, "%Y-%m-%d")
            if req_date <= arr_dt <= end_date:
                daily_delta[arr_dt] += arr_amt

    # 3. Recurring Expenses: group variable living categories by category, others by (category, description)
    var_cats = {"groceries", "transport", "dining"}
    groups = []
    for cat, g in user_events[user_events["direction"] == "debit"].groupby("category"):
        if cat in var_cats:
            groups.append((cat, g))
        else:
            for desc, sub_g in g.groupby("description"):
                groups.append((cat, sub_g))

    for cat, group in groups:
        settled = group[group["status"] == "settled"].sort_values("settlement_date")
        if len(settled) < 2:
            continue
            
        dates = [datetime.strptime(d, "%Y-%m-%d") for d in settled["settlement_date"]]
        diffs = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
        avg_diff = sum(diffs) / len(diffs)
        
        is_monthly = 27 <= avg_diff <= 33
        
        last_ev = settled.iloc[-1]
        last_dt = dates[-1]
        ev_id = str(last_ev["event_id"]).strip()
        if cat in var_cats:
            amt = float(settled["home_amount"].median())
        else:
            amt = float(last_ev["home_amount"])
        
        # Check if spending changes apply to this event or series
        has_stop = (ev_id in stop_ids) or any(str(g_ev).strip() in stop_ids for g_ev in settled["event_id"])
        if has_stop:
            continue
            
        has_reduce = ev_id in reduce_map
        if has_reduce:
            amt = reduce_map[ev_id]
        else:
            for g_ev in settled["event_id"]:
                gid = str(g_ev).strip()
                if gid in reduce_map:
                    amt = reduce_map[gid]
                    break
                    
        # Project forward across 90 days
        if is_monthly:
            dom = last_dt.day
            cur = req_date
            while cur <= end_date:
                max_d = calendar.monthrange(cur.year, cur.month)[1]
                target_dt = datetime(cur.year, cur.month, min(dom, max_d))
                if req_date <= target_dt <= end_date:
                    daily_delta[target_dt] -= amt
                if cur.month == 12:
                    cur = datetime(cur.year + 1, 1, 1)
                else:
                    cur = datetime(cur.year, cur.month + 1, 1)
        else:
            step = int(round(avg_diff))
            if step < 1:
                step = 7
            cur = last_dt + timedelta(days=step)
            while cur <= end_date:
                if cur >= req_date:
                    daily_delta[cur] -= amt
                cur += timedelta(days=step)
                
    # 4. Running Balances
    balances = {}
    running_bal = initial_balance
    for d in sorted(daily_delta.keys()):
        running_bal += daily_delta[d]
        balances[d] = running_bal
        
    return balances, min_bal_to_keep, daily_delta
