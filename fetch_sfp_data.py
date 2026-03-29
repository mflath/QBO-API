#!/usr/bin/env python3
"""
fetch_sfp_data.py — Fetch QBO balance sheet data for specific dates and load into MySQL.

For each --date:
  1. Fetches TrialBalance as of that date → loads all account balances into monthly_balances
  2. Fetches ProfitAndLoss for fiscal year-to-date → extracts net income → stores as
     account 125 (29905 Current Earnings) so the SFP balances

Usage:
  python3 fetch_sfp_data.py \\
    --date 2026-02-28 --date 2025-02-28 \\
    --mysql-user root --mysql-pass YOUR_PASS

  The script replaces all monthly_balances rows for each specified date with fresh
  data from QBO, leaving all other months untouched.
"""

import urllib.request
import urllib.error
import json
import argparse
import sys
from datetime import date
import mysql.connector

parser = argparse.ArgumentParser(description="Fetch SFP data from QBO for specific dates")
parser.add_argument("--date",             required=True, action="append", metavar="YYYY-MM-DD",
                    help="Date to fetch — can be specified multiple times")
parser.add_argument("--fiscal-month",     required=False, default=4, type=int,
                    help="Fiscal year start month number (default: 4 = April)")
parser.add_argument("--mysql-host",       required=False, default="localhost")
parser.add_argument("--mysql-db",         required=False, default="qbo")
parser.add_argument("--mysql-user",       required=True)
parser.add_argument("--mysql-pass",       required=True)
parser.add_argument("--email",            required=False, default="mstoews@hotmail.com")
parser.add_argument("--password",         required=False, default="1628888")
parser.add_argument("--earnings-id",      required=False, default="125",
                    help="QBO account ID for Current Earnings / net income (default: 125 = 29905)")
args = parser.parse_args()

# ── Login ──────────────────────────────────────────────────────────────────────
print("Logging in to NobelLedger...")
try:
    req = urllib.request.Request(
        "https://api.nobleledger.com/api/login",
        data=json.dumps({"Email": args.email, "Password": args.password, "returnSecureToken": True}).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        login_data = json.loads(r.read().decode())
except urllib.error.HTTPError as e:
    print(f"Login failed: HTTP {e.code} {e.reason}", file=sys.stderr); sys.exit(1)
except urllib.error.URLError as e:
    print(f"Login failed: {e.reason}", file=sys.stderr); sys.exit(1)

token = login_data.get("idToken")
if not token:
    print("Login failed: no token in response", file=sys.stderr); sys.exit(1)
print("Login successful\n")

def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    })
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())

def fiscal_year_start(d):
    """First day of the fiscal year that contains date d."""
    if d.month >= args.fiscal_month:
        return date(d.year, args.fiscal_month, 1)
    return date(d.year - 1, args.fiscal_month, 1)

# ── Fetch functions ────────────────────────────────────────────────────────────

def fetch_trial_balance(as_of):
    """Returns list of (account_id, balance) for the given date string.
       Balance convention: positive = debit, negative = credit (same as QBO TB)."""
    data = fetch_json(
        f"https://api.nobleledger.com/qbo/run_report"
        f"?report_name=TrialBalance&end_date={as_of}&accounting_method=Accrual"
    )
    results = []
    for row in data.get("Rows", {}).get("Row", []):
        col = row.get("ColData")
        if not col:
            continue
        acct_id = col[0].get("id", "")
        if not acct_id:
            continue
        debit  = float(col[1].get("value") or 0)
        credit = float(col[2].get("value") or 0)
        results.append((acct_id, round(debit - credit, 2)))
    return results

def find_net_income_in_rows(rows):
    """Recursively search P&L rows for the NetIncome group and return its value."""
    for row in rows:
        if row.get("group") == "NetIncome":
            # Summary ColData: [{value: "Net Income"}, {value: "451854.06"}]
            for cell in row.get("Summary", {}).get("ColData", []):
                try:
                    return float(cell.get("value") or "")
                except (ValueError, TypeError):
                    continue
        sub = row.get("Rows", {}).get("Row", [])
        if sub:
            result = find_net_income_in_rows(sub)
            if result is not None:
                return result
    return None

def fetch_net_income(start_date, end_date):
    """Fetch P&L and return net income as a float (positive = surplus, negative = deficit)."""
    print(f"    Fetching P&L {start_date} → {end_date}...")
    data = fetch_json(
        f"https://api.nobleledger.com/qbo/run_report"
        f"?report_name=ProfitAndLoss&start_date={start_date}&end_date={end_date}&accounting_method=Accrual"
    )
    net = find_net_income_in_rows(data.get("Rows", {}).get("Row", []))
    if net is None:
        print("    WARNING: Net income not found in P&L response — storing 0")
        # Dump structure for debugging
        print("    P&L top-level keys:", list(data.keys()))
        rows = data.get("Rows", {}).get("Row", [])
        print(f"    Row count: {len(rows)}")
        for i, r in enumerate(rows[:3]):
            print(f"    Row {i}: group={r.get('group','?')} type={r.get('type','?')}")
        return 0.0
    return net

# ── Connect to MySQL ───────────────────────────────────────────────────────────
print(f"Connecting to MySQL {args.mysql_host}/{args.mysql_db}...")
try:
    con = mysql.connector.connect(
        host=args.mysql_host, database=args.mysql_db,
        user=args.mysql_user, password=args.mysql_pass
    )
except mysql.connector.Error as e:
    print(f"MySQL connection failed: {e}", file=sys.stderr); sys.exit(1)
cur = con.cursor()
print("Connected\n")

# ── Process each date ──────────────────────────────────────────────────────────
for date_str in args.date:
    as_of    = date.fromisoformat(date_str)
    fy_start = fiscal_year_start(as_of)

    print(f"── {date_str}  (fiscal year starts {fy_start}) ──────────────────")

    # 1. Trial balance
    print(f"  Fetching TrialBalance as of {date_str}...")
    try:
        tb_rows = fetch_trial_balance(date_str)
    except urllib.error.HTTPError as e:
        print(f"  FAILED: HTTP {e.code} {e.reason}", file=sys.stderr); sys.exit(1)
    print(f"  Got {len(tb_rows)} account balances from trial balance")

    # 2. Net income from P&L
    try:
        net_income = fetch_net_income(str(fy_start), date_str)
    except urllib.error.HTTPError as e:
        print(f"  P&L fetch failed: HTTP {e.code} {e.reason} — net income set to 0")
        net_income = 0.0
    print(f"  Net income (fiscal YTD): {net_income:>12,.2f}")

    # 3. Replace monthly_balances for this date
    cur.execute("DELETE FROM monthly_balances WHERE month_end = %s", (date_str,))
    print(f"  Cleared {cur.rowcount} existing rows for {date_str}")

    # Insert TB rows (exclude Current Earnings — we control that via P&L)
    tb_insert = [(aid, date_str, bal) for aid, bal in tb_rows if aid != args.earnings_id]
    cur.executemany(
        "INSERT INTO monthly_balances (account_id, month_end, balance) VALUES (%s, %s, %s)",
        tb_insert
    )

    # Insert Current Earnings as negative (credit balance convention matches other equity accounts)
    # P&L net income is positive for surplus → stored negative → displayed positive (sign=-1 in sfp_lines)
    cur.execute(
        "INSERT INTO monthly_balances (account_id, month_end, balance) VALUES (%s, %s, %s)",
        (args.earnings_id, date_str, round(-net_income, 2))
    )

    con.commit()
    print(f"  Saved {len(tb_insert)} TB rows + Current Earnings ({-net_income:,.2f}) for {date_str}")
    print()

con.close()
print("Done.")
print()
print("Next steps:")
print(f"  1. Restart the API server:  cd api && DB_PASS=... node server.js")
print(f"  2. Open SFP_Report.rdlx-json in ARJS and preview with your loaded dates")
