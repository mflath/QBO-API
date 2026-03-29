import urllib.request
import urllib.error
import json
import csv
import argparse
import sys
from collections import defaultdict

parser = argparse.ArgumentParser(description="Build a custom General Ledger from journal entries")
parser.add_argument("--start-date", required=False, default="2025-04-01", help="Start date (YYYY-MM-DD)")
parser.add_argument("--end-date", required=False, default="2026-03-31", help="End date (YYYY-MM-DD)")
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

# Fetch journal entries
url = f"https://api.nobleledger.com/qbo/journal_entries?start_date={args.start_date}&end_date={args.end_date}"

try:
    req = urllib.request.Request(url, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    })
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
except urllib.error.HTTPError as e:
    print(f"Fetch failed: HTTP {e.code} {e.reason}", file=sys.stderr)
    sys.exit(1)
except urllib.error.URLError as e:
    print(f"Fetch failed: {e.reason}", file=sys.stderr)
    sys.exit(1)

entries = data.get("journal_entries", [])
print(f"Fetched {len(entries)} journal entries")

# Build GL lines grouped by account
# Each line: (date, txn_id, doc_num, description, private_note, debit, credit, class, department)
account_lines = defaultdict(list)

for entry in entries:
    txn_date = entry.get("TxnDate", "")
    txn_id = entry.get("Id", "")
    doc_num = entry.get("DocNumber", "")
    private_note = entry.get("PrivateNote", "")

    for line in entry.get("Line", []):
        detail = line.get("JournalEntryLineDetail", {})
        account = detail.get("AccountRef", {})
        class_ref = detail.get("ClassRef", {})
        dept = detail.get("DepartmentRef", {})

        full_name = account.get("name", "")
        parts = full_name.split(" ", 1)
        if len(parts) == 2 and parts[0].isdigit():
            acct_num, acct_name = parts[0], parts[1]
        else:
            acct_num, acct_name = "", full_name
        acct_key = (acct_num, acct_name)

        amount = float(line.get("Amount", 0))
        posting_type = detail.get("PostingType", "")

        if posting_type == "Debit":
            debit = amount
            credit = 0.0
        else:
            debit = 0.0
            credit = amount

        account_lines[acct_key].append({
            "date": txn_date,
            "txn_id": txn_id,
            "doc_num": doc_num,
            "description": line.get("Description", "") or private_note,
            "debit": debit,
            "credit": credit,
            "class": class_ref.get("name", ""),
            "department": dept.get("name", ""),
        })

# Sort accounts by account number, then lines by date
row_count = 0

with open("custom_gl.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "AccountNumber", "AccountName",
        "Date", "TxnId", "DocNumber", "Description",
        "Debit", "Credit", "Balance",
        "Class", "Department",
    ])

    for acct_key in sorted(account_lines.keys()):
        acct_num, acct_name = acct_key
        lines = sorted(account_lines[acct_key], key=lambda r: r["date"])

        running_balance = 0.0
        for row in lines:
            running_balance += row["debit"] - row["credit"]
            writer.writerow([
                acct_num,
                acct_name,
                row["date"],
                row["txn_id"],
                row["doc_num"],
                row["description"],
                f"{row['debit']:.2f}" if row["debit"] else "",
                f"{row['credit']:.2f}" if row["credit"] else "",
                f"{running_balance:.2f}",
                row["class"],
                row["department"],
            ])
            row_count += 1

print(f"Wrote {row_count} rows to custom_gl.csv  ({args.start_date} → {args.end_date})")
