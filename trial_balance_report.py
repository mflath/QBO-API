import urllib.request
import urllib.error
import json
import csv
import argparse
import sys
from datetime import date, timedelta
import calendar

parser = argparse.ArgumentParser(description="Monthly trial balance across a date range")
parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD) — first month end on or after this date is included")
parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD) — last month end on or before this date is included")
parser.add_argument("--email", required=False, default="mstoews@hotmail.com")
parser.add_argument("--password", required=False, default="1628888")
args = parser.parse_args()

# Login
login_url = "https://api.nobleledger.com/api/login"
payload = json.dumps({
    "Email": args.email,
    "Password": args.password,
    "returnSecureToken": True
}).encode()

try:
    req = urllib.request.Request(login_url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as response:
        login_data = json.loads(response.read().decode())
except urllib.error.HTTPError as e:
    print(f"Login failed: HTTP {e.code} {e.reason}", file=sys.stderr)
    sys.exit(1)
except urllib.error.URLError as e:
    print(f"Login failed: {e.reason}", file=sys.stderr)
    sys.exit(1)

token = login_data.get("idToken")
if not token:
    print("Login failed: no token in response", file=sys.stderr)
    sys.exit(1)

print("Login successful")

def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    })
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())

def month_end(year, month):
    return date(year, month, calendar.monthrange(year, month)[1])

def parse_account_name(raw):
    parts = raw.split(" ", 1)
    if len(parts) == 2 and parts[0].replace(".", "").isdigit():
        return parts[0], parts[1]
    return "", raw

def fetch_tb_balances(end_date_str):
    """Returns dict of account_id -> (acct_num, acct_name, net_balance).
    Positive = debit balance, negative = credit balance."""
    data = fetch_json(
        f"https://api.nobleledger.com/qbo/run_report"
        f"?report_name=TrialBalance"
        f"&end_date={end_date_str}"
        f"&accounting_method=Accrual"
    )
    result = {}
    for row in data.get("Rows", {}).get("Row", []):
        col_data = row.get("ColData")
        if not col_data:
            continue
        acct_id  = col_data[0].get("id", "")
        acct_raw = col_data[0].get("value", "")
        debit    = float(col_data[1].get("value", "") or 0)
        credit   = float(col_data[2].get("value", "") or 0)
        acct_num, acct_name = parse_account_name(acct_raw)
        result[acct_id] = (acct_num, acct_name, debit - credit)
    return result

# Generate month-end dates within the range
start = date.fromisoformat(args.start_date)
end   = date.fromisoformat(args.end_date)

month_ends = []
year, month = start.year, start.month
while True:
    me = month_end(year, month)
    if me > end:
        break
    if me >= start:
        month_ends.append(me)
    if month == 12:
        year, month = year + 1, 1
    else:
        month += 1

print(f"Generating TB for {len(month_ends)} month-end(s): {[str(m) for m in month_ends]}")

# Fetch TB for each month end
monthly_balances = {}  # date -> {acct_id -> (num, name, net)}
all_account_ids = {}   # acct_id -> (acct_num, acct_name) — last seen wins

for me in month_ends:
    print(f"  Fetching {me}...")
    try:
        balances = fetch_tb_balances(str(me))
    except urllib.error.HTTPError as e:
        print(f"  Failed for {me}: HTTP {e.code} {e.reason}", file=sys.stderr)
        sys.exit(1)
    monthly_balances[me] = balances
    for acct_id, (num, name, _) in balances.items():
        all_account_ids[acct_id] = (num, name)

# Sort accounts by account number then name
def sort_key(acct_id):
    num, name = all_account_ids[acct_id]
    return (num, name)

sorted_ids = sorted(all_account_ids.keys(), key=sort_key)

# Column headers: MMM-YY format
col_headers = [me.strftime("%b-%y") for me in month_ends]

# Write CSV
row_count = 0
with open("trial_balance_report.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["AccountNumber", "AccountName"] + col_headers)

    for acct_id in sorted_ids:
        acct_num, acct_name = all_account_ids[acct_id]
        row = [acct_num, acct_name]
        for me in month_ends:
            bal = monthly_balances[me].get(acct_id)
            row.append(f"{bal[2]:.2f}" if bal else "")
        writer.writerow(row)
        row_count += 1

print(f"Wrote {row_count} accounts x {len(month_ends)} months to trial_balance_report.csv")
