# Buy or Wait? — AI Financial Decision Agent

Starter repository and complete production solution for the **HackerRank Orchestrate** 24-hour hackathon (September 2026).

---

## 1. Executive Summary & Problem Overview

When a user asks **"Can I afford this laptop?"**, an intelligent financial agent cannot rely solely on the current bank balance. The agent must account for:
- Confirmed upcoming income (payroll schedules, salary adjustments, confirmed arrears)
- Recurring essential living expenses (rent, groceries, transport, utilities, insurance)
- Pending transactions and reserved debits
- Provider financing options (installment schedules, partial payments)
- Non-obvious signals buried in contextual messages and multimodal receipts
- Personal priorities, protected spending categories, and minimum balance thresholds

For every expense request in `dataset/requests.csv`, this agent evaluates whether the user should:
1. **`full_payment`**: Pay 100% upfront today.
2. **`partial_payment`**: Pay what is safe today, and complete the remainder by the deadline.
3. **`installments`**: Spread the expense across an eligible provider financing plan.
4. **`wait`**: Defer payment to the earliest conservative date when cashflow safely allows it.
5. **`not_recommended`**: Do not proceed if the purchase risks financial distress or violates minimum balance rules.

---

## 2. Approach & System Architecture

The solution uses a hybrid architecture combining multimodal extraction, contextual NLP parsing, 90-day daily cashflow forecasting, multi-candidate constraint optimization, and grounded natural language generation.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             INPUT DATASET (dataset/)                        │
├──────────────────────┬──────────────────────┬───────────────────────────────┤
│ Financial Profiles   │ Financial Events     │ Provider Payment Options      │
│ Exchange Rates       │ Messages (NLP)       │ Receipt Images (Multimodal)   │
└──────────┬───────────┴──────────┬───────────┴───────────────┬───────────────┘
           │                      │                           │
           ▼                      ▼                           ▼
┌──────────────────────┐ ┌────────────────────┐ ┌─────────────────────────────┐
│  DATA LOADER & FX    │ │  MESSAGE PARSER    │ │  MULTIMODAL RECEIPT ENGINE  │
│  (code/data_loader)  │ │  (message_parser)  │ │  (code/multimodal.py)       │
│  Resolves dated rates│ │  Parses contracts, │ │  OCR & receipt total        │
│  and user profiles   │ │  salary shifts,    │ │  extraction for missing     │
│                      │ │  failed debits     │ │  event amounts              │
└──────────┬───────────┘ └────────┬───────────┘ └─────────────┬───────────────┘
           │                      │                           │
           └──────────────────────┼───────────────────────────┘
                                  ▼
           ┌──────────────────────────────────────────────────┐
           │          90-DAY CASHFLOW FORECASTER              │
           │             (code/forecaster.py)                 │
           │  - Conservative daily cash trajectory            │
           │  - Median-based living expense recurrence        │
           │  - Confirmed salary inflow alignment             │
           │  - Pending debit reservation                     │
           └──────────────────────┬───────────────────────────┘
                                  ▼
           ┌──────────────────────────────────────────────────┐
           │        CASHFLOW & RISK OPTIMIZER                 │
           │             (code/optimizer.py)                  │
           │  - Evaluates full, partial, installment, & wait  │
           │  - Tests permitted spending changes              │
           │  - Enforces minimum_balance_to_keep daily        │
           └──────────────────────┬───────────────────────────┘
                                  ▼
           ┌──────────────────────────────────────────────────┐
           │               DECISION RANKER                    │
           │              (code/ranker.py)                    │
           │  7-tier priority hierarchy:                      │
           │  Deadline > Status > Cuts > Cost > Start > Count │
           └──────────────────────┬───────────────────────────┘
                                  ▼
           ┌──────────────────────────────────────────────────┐
           │         NATURAL LANGUAGE EXPLAINER               │
           │             (code/explainer.py)                  │
           │  Synthesizes grounded, personalized rationales   │
           └──────────────────────┬───────────────────────────┘
                                  ▼
           ┌──────────────────────────────────────────────────┐
           │         FINAL SUBMISSION CSV (output.csv)        │
           └──────────────────────────────────────────────────┘
```

### Module Breakdown:
1. **`code/data_loader.py`**: Unified data access layer that resolves foreign currency transactions using exact dated rates from `exchange_rates.csv`, joins user profiles, and exposes preprocessed events.
2. **`code/multimodal.py`**: Visual evidence engine extracting receipt totals for transactions with missing amounts in `financial_events.csv`, cross-referencing `images.csv` and `dataset/media/images/`.
3. **`code/message_parser.py`**: Contextual communication engine parsing unstructured emails and text messages to identify salary date shifts, contract terminations, one-time arrears, and active failed debits.
4. **`code/forecaster.py`**: Simulates daily available cash over 90 days. Uses robust median spending estimates for variable living expenses (`groceries`, `transport`, `dining`) to prevent single large purchases from distorting recurring living budgets. Aligns confirmed payroll inflows to active monthly pay dates.
5. **`code/optimizer.py`**: Evaluates all candidate payment options against the forecast. Enforces that the user's balance never drops below `minimum_balance_to_keep` on any day of the commitment period. If full payment is not immediately affordable, searches for minimal spending reductions (`stop:<id>` or `reduce_to:<id>:<amt>`) strictly in user-permitted categories.
6. **`code/ranker.py`**: Ranks viable candidate plans according to challenge rules:
   - On-time completion by `desired_completion_date`
   - Status hierarchy (`affordable_now` > `affordable_with_plan` > `affordable_later` > `not_affordable`)
   - Avoidance and minimization of spending reductions
   - Lowest total payable amount
   - Earlier start date
   - Fewer payment installments
7. **`code/explainer.py`**: Formulates mathematically grounded, concise decision explanations citing exact payment amounts, buffer margins, and spending changes.

---

## 3. Setup & Installation Instructions

### Prerequisites
- Python 3.10 or higher (tested on Python 3.12)
- Git

### Step 1: Environment Setup

#### On Windows (PowerShell / Command Prompt):
```powershell
# Create virtual environment (if not already created)
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Or run directly using the environment's Python executable:
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install pandas numpy pillow
```

#### On macOS / Linux:
```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install pandas numpy pillow
```

---

## 4. How to Run the Agent

### A. Run Predictions on All 250 Requests (Evaluation Pipeline)
To generate the final submission file `output.csv` from `dataset/requests.csv`:

```bash
# On Windows:
.\.venv\Scripts\python.exe code/main.py --data_dir dataset --output output.csv

# On macOS/Linux:
python3 code/main.py --data_dir dataset --output output.csv
```
* Processes all 250 evaluation requests.
* Enforces the required 8-column schema.
* Synchronizes both `output.csv` (root) and `dataset/output.csv`.

### B. Run Benchmark Evaluation Pipeline
To test the agent against the 25 public ground-truth test cases in `dataset/sample_requests.csv`:

```bash
# On Windows:
.\.venv\Scripts\python.exe code/evaluation/main.py

# On macOS/Linux:
python3 code/evaluation/main.py
```

### C. Interactive Purchase Advisor CLI
To query ad-hoc financial questions for any user:

```bash
# On Windows:
.\.venv\Scripts\python.exe code/interactive.py --user user_01 --amount 15000 --date 2026-03-01 --desired 2026-03-31

# Step-by-step interactive mode:
.\.venv\Scripts\python.exe code/interactive.py
```
*(Supports flexible date formats including `YYYY-MM-DD`, `DD-MM-YYYY`, and `MM-DD-YYYY`.)*

### D. Programmatic Python API
```python
from code.data_loader import FinancialDataLoader
from code.optimizer import evaluate_request

loader = FinancialDataLoader(data_dir="dataset")

custom_request = {
    "request_id": "demo_01",
    "user_id": "user_27",
    "request_date": "2026-05-05",
    "requested_amount": 99000.0,
    "desired_completion_date": "2026-06-05",
    "allows_partial_payment": True
}

decision = evaluate_request(loader, custom_request)
print(decision)
```

---

## 5. Benchmark Performance & Verification

On the official 25-request public ground-truth benchmark (`dataset/sample_requests.csv`), the agent achieves:

| Metric | Score | Matches |
|---|---|---|
| **Payment Method Accuracy** | **96.0%** | 24 / 25 |
| **Affordability Status Accuracy** | **92.0%** | 23 / 25 |
| **Payment Plan Exact Match** | **92.0%** | 23 / 25 |
| **Spending Changes Exact Match** | **88.0%** | 22 / 25 |
| **Earliest Date Exact Match** | **64.0%** | 16 / 25 |

### Full Dataset Run Distribution (250 Evaluation Requests):
* **Recommended Payment Method**:
  - `not_recommended`: 71 requests (28.4%)
  - `full_payment`: 69 requests (27.6%)
  - `wait`: 55 requests (22.0%)
  - `installments`: 45 requests (18.0%)
  - `partial_payment`: 10 requests (4.0%)
* **Affordability Status**:
  - `not_affordable`: 71 requests (28.4%)
  - `affordable_with_plan`: 67 requests (26.8%)
  - `affordable_now`: 57 requests (22.8%)
  - `affordable_later`: 55 requests (22.0%)

---

## 6. Submission Artifacts & Checklist

The three mandatory submission files are located in the repository root:

| File | Description | Verification Status |
|---|---|---|
| **`code.zip`** | Solution package containing all modules in `code/`, `code/README.md`, and `code/evaluation/usage_report.md`. Strictly excludes virtual environments, node_modules, `.pyc` caches, and dataset files. | Verified via isolated dry run |
| **`output.csv`** | Predictions for all 250 evaluation requests in `dataset/requests.csv` adhering to the exact required 8-column format. | Verified 100% schema compliant |
| **`log.txt`** | Full turn-by-turn conversation transcript adhering strictly to `AGENTS.md` §5 with ISO-8601 timestamps and `tool=Antigravity`. | Verified append-only & valid |

### Official Submission Link
Upload your submission files directly to HackerRank:

https://www.hackerrank.com/contests/hackerrank-orchestrate-september26/challenges/buy-or-wait/submission
