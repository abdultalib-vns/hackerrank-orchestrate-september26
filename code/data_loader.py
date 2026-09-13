"""
Data Loader Module.
Loads all challenge CSVs, applies image amount extractions, resolves foreign exchange rates,
and provides unified, normalized data access for the decision engine.
"""

import os
import pandas as pd
from datetime import datetime

# Local imports
try:
    from .multimodal import load_image_amount_map
    from .message_parser import parse_all_messages
except ImportError:
    from multimodal import load_image_amount_map
    from message_parser import parse_all_messages

class FinancialDataLoader:
    def __init__(self, data_dir="dataset"):
        self.data_dir = data_dir
        
        # Paths
        self.profiles_path = os.path.join(data_dir, "financial_profiles.csv")
        self.events_path = os.path.join(data_dir, "financial_events.csv")
        self.rates_path = os.path.join(data_dir, "exchange_rates.csv")
        self.options_path = os.path.join(data_dir, "request_payment_options.csv")
        self.requests_path = os.path.join(data_dir, "requests.csv")
        self.sample_requests_path = os.path.join(data_dir, "sample_requests.csv")
        self.messages_path = os.path.join(data_dir, "messages.csv")
        self.images_path = os.path.join(data_dir, "images.csv")
        
        self.load_all()

    def load_all(self):
        # 1. Load profiles
        self.profiles_df = pd.read_csv(self.profiles_path)
        self.profiles_by_user = {r["user_id"]: r for _, r in self.profiles_df.iterrows()}
        self.user_home_currencies = {r["user_id"]: str(r["home_currency"]).strip() for _, r in self.profiles_df.iterrows()}
        
        # 2. Load exchange rates
        self.rates_df = pd.read_csv(self.rates_path)
        self.rate_dict = {}
        for _, r in self.rates_df.iterrows():
            key = (str(r["rate_date"]).strip(), str(r["from_currency"]).strip(), str(r["to_currency"]).strip())
            self.rate_dict[key] = float(r["rate"])
            
        # 3. Load financial events and fill missing amounts via multimodal extraction
        self.events_df = pd.read_csv(self.events_path)
        image_amounts = load_image_amount_map(self.images_path, os.path.join(self.data_dir, "media", "images"))
        for ev_id, amt in image_amounts.items():
            self.events_df.loc[self.events_df["event_id"] == ev_id, "amount"] = amt
            
        # 4. Normalize event currency to user's home currency
        self.events_df["home_currency"] = self.events_df["user_id"].map(self.user_home_currencies)
        self.events_df["home_amount"] = [self._convert_to_home(row) for _, row in self.events_df.iterrows()]
        
        # Group events by user_id for fast lookup
        self.events_by_user = {}
        for u_id, group in self.events_df.groupby("user_id"):
            self.events_by_user[u_id] = group
            
        # 5. Load payment options
        self.options_df = pd.read_csv(self.options_path)
        self.options_by_req = {}
        for req_id, group in self.options_df.groupby("request_id"):
            self.options_by_req[req_id] = group
            
        # 6. Parse messages
        self.user_message_updates = parse_all_messages(self.messages_path)
        
        # 7. Requests
        self.requests_df = pd.read_csv(self.requests_path) if os.path.exists(self.requests_path) else None
        self.sample_requests_df = pd.read_csv(self.sample_requests_path) if os.path.exists(self.sample_requests_path) else None

    def _convert_to_home(self, row):
        curr = str(row["currency"]).strip()
        home_curr = str(row["home_currency"]).strip()
        amt = float(row["amount"]) if pd.notna(row["amount"]) else 0.0
        if curr == home_curr:
            return amt
            
        s_date = str(row["settlement_date"]).strip()
        if s_date == "nan" or not s_date:
            s_date = str(row["event_date"]).strip()
            
        pair_key = (s_date, curr, home_curr)
        if pair_key in self.rate_dict:
            return amt * self.rate_dict[pair_key]
            
        # Fallback to closest matching currency pair rate
        matches = self.rates_df[(self.rates_df["from_currency"] == curr) & (self.rates_df["to_currency"] == home_curr)]
        if len(matches) > 0:
            return amt * float(matches.iloc[0]["rate"])
            
        return amt

    def get_profile(self, user_id):
        return self.profiles_by_user.get(user_id)

    def get_user_events(self, user_id):
        return self.events_by_user.get(user_id, pd.DataFrame())

    def get_request_options(self, request_id):
        return self.options_by_req.get(request_id, pd.DataFrame())

    def get_user_message_info(self, user_id):
        return self.user_message_updates.get(user_id, {
            "salary_override": None,
            "salary_date_override": None,
            "contract_ended": False,
            "one_time_credits": [],
            "failed_debits_active": set()
        })
