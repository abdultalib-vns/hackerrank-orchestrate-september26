"""
Message Parser Module.
Interprets natural language messages from employers, banks, merchants, and service providers.
Extracts financial amendments such as salary updates, date shifts, contract statuses, and active failed debits.
"""

import re
import pandas as pd

def parse_all_messages(messages_csv_path="dataset/messages.csv"):
    """
    Parses messages.csv and returns a structured dictionary keyed by user_id.
    """
    user_updates = {}
    if not messages_csv_path:
        return user_updates
        
    df_msgs = pd.read_csv(messages_csv_path)
    
    for _, row in df_msgs.iterrows():
        u_id = str(row["user_id"]).strip()
        if u_id not in user_updates:
            user_updates[u_id] = {
                "salary_override": None,
                "salary_date_override": None,
                "contract_ended": False,
                "one_time_credits": [],
                "failed_debits_active": set(),
                "messages": []
            }
            
        text = str(row["message_text"]).strip()
        text_lower = text.lower()
        ev_id = str(row["related_event_id"]).strip() if pd.notna(row["related_event_id"]) else None
        
        user_updates[u_id]["messages"].append({
            "message_id": row["message_id"],
            "sent_at": row["sent_at"],
            "text": text,
            "related_event_id": ev_id
        })
        
        # 1. Failed debit retry
        if "failed" in text_lower and ("still outstanding" in text_lower or "another debit will be attempted" in text_lower or "bill is still open" in text_lower):
            if ev_id:
                user_updates[u_id]["failed_debits_active"].add(ev_id)
                
        # 2. Contract termination / seasonal end
        if "contract has ended" in text_lower or "kontrak telah berakhir" in text_lower or "no off-season income" in text_lower:
            user_updates[u_id]["contract_ended"] = True
            
        # 3. Base salary / monthly pay revision
        # Supports both English and Indonesian notices
        patterns = [
            r'(?:naik menjadi|pay is|reduced to|salary will be|salary of|dikonfirmasi adalah|gaji bulanan|regular salary for the next payroll is|resumes on \d{4}-\d{2}-\d{2}\. regular salary of)\s+(?:[A-Z]{3}\s*)?([0-9]+(?:[\.,][0-9]+)?)',
            r'regular salary of\s+(?:[A-Z]{3}\s*)?([0-9]+(?:[\.,][0-9]+)?)',
            r'salary is reduced to\s+(?:[A-Z]{3}\s*)?([0-9]+(?:[\.,][0-9]+)?)'
        ]
        for pat in patterns:
            m_amt = re.search(pat, text, re.IGNORECASE)
            if m_amt:
                try:
                    val_str = m_amt.group(1).replace(',', '')
                    user_updates[u_id]["salary_override"] = float(val_str)
                    break
                except:
                    pass
                    
        # 4. Salary date shift
        date_patterns = [
            r'(?:expected on|credit date is|resumes on|berlaku mulai)\s+(\d{4}-\d{2}-\d{2})'
        ]
        for dpat in date_patterns:
            m_date = re.search(dpat, text, re.IGNORECASE)
            if m_date:
                user_updates[u_id]["salary_date_override"] = m_date.group(1)
                break
                
        # 5. One-time arrears credit
        m_arr = re.search(r'one-time arrears adjustment of\s+(?:[A-Z]{3}\s*)?([0-9]+(?:[\.,][0-9]+)?)', text, re.IGNORECASE)
        if m_arr:
            try:
                credit_amt = float(m_arr.group(1).replace(',', ''))
                target_date = user_updates[u_id]["salary_date_override"]
                user_updates[u_id]["one_time_credits"].append((target_date, credit_amt))
            except:
                pass

    return user_updates
