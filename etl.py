import urllib.request
import urllib.error
import json
import argparse
import sys
import csv
import calendar
from datetime import date
import mysql.connector

parser = argparse.ArgumentParser(description="ETL: load QBO data into MySQL")
parser.add_argument("--start-date",  required=False, default="2025-04-01", help="Start date (YYYY-MM-DD)")
parser.add_argument("--end-date",    required=False, default="2026-03-31", help="End date (YYYY-MM-DD)")
parser.add_argument("--mysql-host",  required=False, default="localhost",  help="MySQL host")
parser.add_argument("--mysql-db",    required=False, default="qbo",        help="MySQL database name")
parser.add_argument("--mysql-user",  required=True,                        help="MySQL username")
parser.add_argument("--mysql-pass",  required=True,                        help="MySQL password")
parser.add_argument("--email",       required=False, default="mstoews@hotmail.com")
parser.add_argument("--password",    required=False, default="1628888")
args = parser.parse_args()

# ── Login ──────────────────────────────────────────────────────────────────────
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

# ── Connect to MySQL ───────────────────────────────────────────────────────────
print(f"Connecting to MySQL ({args.mysql_host}/{args.mysql_db})...")
try:
    con = mysql.connector.connect(
        host=args.mysql_host,
        database=args.mysql_db,
        user=args.mysql_user,
        password=args.mysql_pass
    )
except mysql.connector.Error as e:
    print(f"MySQL connection failed: {e}", file=sys.stderr)
    sys.exit(1)

cur = con.cursor()
print("Connected")

# ── Create tables ──────────────────────────────────────────────────────────────
statements = [
    "DROP VIEW  IF EXISTS gl_detail",
    "DROP TABLE IF EXISTS monthly_balances",
    "DROP TABLE IF EXISTS gl_lines",
    "DROP TABLE IF EXISTS accounts",
    """
    CREATE TABLE accounts (
        id                   VARCHAR(50)  PRIMARY KEY,
        acct_num             VARCHAR(50),
        name                 VARCHAR(255),
        fully_qualified_name VARCHAR(255),
        classification       VARCHAR(100),
        account_type         VARCHAR(100),
        account_subtype      VARCHAR(100),
        active               TINYINT(1),
        current_balance      DECIMAL(15,2)
    )
    """,
    """
    CREATE TABLE gl_lines (
        id          INT AUTO_INCREMENT PRIMARY KEY,
        account_id  VARCHAR(50),
        txn_date    DATE,
        txn_id      VARCHAR(50),
        doc_num     VARCHAR(50),
        description TEXT,
        debit       DECIMAL(15,2),
        credit      DECIMAL(15,2),
        class_name  VARCHAR(255),
        department  VARCHAR(255),
        INDEX idx_account (account_id),
        INDEX idx_date    (txn_date)
    )
    """,
    """
    CREATE TABLE monthly_balances (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        account_id VARCHAR(50),
        month_end  DATE,
        balance    DECIMAL(15,2),
        INDEX idx_account (account_id),
        INDEX idx_month   (month_end)
    )
    """,
    """
    CREATE VIEW gl_detail AS
        SELECT
            a.acct_num,
            a.name               AS account_name,
            a.fully_qualified_name,
            a.classification,
            a.account_type,
            g.txn_date,
            g.txn_id,
            g.doc_num,
            g.description,
            g.debit,
            g.credit,
            g.class_name,
            g.department
        FROM gl_lines g
        JOIN accounts a ON a.id = g.account_id
        ORDER BY a.acct_num, a.name, g.txn_date
    """
]

for stmt in statements:
    cur.execute(stmt)
con.commit()
print("Tables created")

# ── Load accounts ──────────────────────────────────────────────────────────────
print("Loading chart of accounts...")
try:
    acct_data = fetch_json("https://api.nobleledger.com/qbo/accounts")
except urllib.error.HTTPError as e:
    print(f"Failed to fetch accounts: HTTP {e.code} {e.reason}", file=sys.stderr)
    sys.exit(1)

accounts = acct_data.get("QueryResponse", {}).get("Account", [])
cur.executemany(
    "INSERT INTO accounts VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    [
        (
            a["Id"],
            a.get("AcctNum", ""),
            a.get("Name", ""),
            a.get("FullyQualifiedName", ""),
            a.get("Classification", ""),
            a.get("AccountType", ""),
            a.get("AccountSubType", ""),
            1 if a.get("Active") else 0,
            a.get("CurrentBalance", 0.0),
        )
        for a in accounts
    ]
)
con.commit()
print(f"  Loaded {len(accounts)} accounts")

# ── Load journal entries (GL lines) ───────────────────────────────────────────
print(f"Loading journal entries ({args.start_date} to {args.end_date})...")
try:
    je_data = fetch_json(
        f"https://api.nobleledger.com/qbo/journal_entries"
        f"?start_date={args.start_date}&end_date={args.end_date}"
    )
except urllib.error.HTTPError as e:
    print(f"Failed to fetch journal entries: HTTP {e.code} {e.reason}", file=sys.stderr)
    sys.exit(1)

entries = je_data.get("journal_entries", [])
rows = []
for entry in entries:
    txn_date     = entry.get("TxnDate") or None
    txn_id       = entry.get("Id", "")
    doc_num      = entry.get("DocNumber", "")
    private_note = entry.get("PrivateNote", "")
    for line in entry.get("Line", []):
        detail      = line.get("JournalEntryLineDetail", {})
        account_id  = detail.get("AccountRef", {}).get("value", "")
        class_name  = detail.get("ClassRef", {}).get("name", "")
        dept_name   = detail.get("DepartmentRef", {}).get("name", "")
        amount      = float(line.get("Amount", 0))
        posting     = detail.get("PostingType", "")
        description = line.get("Description", "") or private_note
        debit  = amount if posting == "Debit"  else 0.0
        credit = amount if posting == "Credit" else 0.0
        rows.append((account_id, txn_date, txn_id, doc_num, description, debit, credit, class_name, dept_name))

cur.executemany(
    "INSERT INTO gl_lines (account_id,txn_date,txn_id,doc_num,description,debit,credit,class_name,department) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    rows
)
con.commit()
print(f"  Loaded {len(rows)} GL lines from {len(entries)} journal entries")

# ── Load monthly trial balances ────────────────────────────────────────────────
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

print(f"Loading monthly trial balances ({len(month_ends)} months)...")
tb_rows = []
for me in month_ends:
    print(f"  Fetching TB for {me}...")
    try:
        tb_data = fetch_json(
            f"https://api.nobleledger.com/qbo/run_report"
            f"?report_name=TrialBalance"
            f"&end_date={me}"
            f"&accounting_method=Accrual"
        )
    except urllib.error.HTTPError as e:
        print(f"  Failed for {me}: HTTP {e.code} {e.reason}", file=sys.stderr)
        sys.exit(1)

    for row in tb_data.get("Rows", {}).get("Row", []):
        col_data = row.get("ColData")
        if not col_data:
            continue
        acct_id = col_data[0].get("id", "")
        debit   = float(col_data[1].get("value", "") or 0)
        credit  = float(col_data[2].get("value", "") or 0)
        tb_rows.append((acct_id, str(me), debit - credit))

cur.executemany(
    "INSERT INTO monthly_balances (account_id, month_end, balance) VALUES (%s,%s,%s)",
    tb_rows
)
con.commit()
print(f"  Loaded {len(tb_rows)} monthly balance rows")

# ── Export CSVs ────────────────────────────────────────────────────────────────

# 1. GL detail
print("\nExporting gl_detail.csv...")
cur.execute("""
    SELECT
        a.acct_num          AS AccountNumber,
        a.name              AS AccountName,
        a.classification    AS Classification,
        a.account_type      AS AccountType,
        g.txn_date          AS Date,
        g.txn_id            AS TxnId,
        g.doc_num           AS DocNumber,
        g.description       AS Description,
        g.debit             AS Debit,
        g.credit            AS Credit,
        g.class_name        AS Class,
        g.department        AS Department
    FROM gl_lines g
    JOIN accounts a ON a.id = g.account_id
    ORDER BY a.acct_num, a.name, g.txn_date
""")
rows = cur.fetchall()
with open("gl_detail.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([d[0] for d in cur.description])
    writer.writerows(rows)
print(f"  Wrote {len(rows)} rows to gl_detail.csv")

# 2. Monthly trial balance — wide format
print("Exporting monthly_trial_balance.csv...")
cur.execute("SELECT DISTINCT month_end FROM monthly_balances ORDER BY month_end")
months = [str(r[0]) for r in cur.fetchall()]

cur.execute("""
    SELECT DISTINCT a.id, a.acct_num, a.name, a.fully_qualified_name, a.classification, a.account_type
    FROM monthly_balances mb
    JOIN accounts a ON a.id = mb.account_id
    ORDER BY a.acct_num, a.name
""")
account_rows = cur.fetchall()

cur.execute("SELECT account_id, CAST(month_end AS CHAR), balance FROM monthly_balances")
balance_lookup = {(r[0], r[1]): r[2] for r in cur.fetchall()}

month_labels = [date.fromisoformat(m).strftime("%b-%y") for m in months]

with open("monthly_trial_balance.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["AccountNumber", "AccountName", "FullyQualifiedName", "Classification", "AccountType"] + month_labels)
    for acct_id, acct_num, name, fqn, classification, acct_type in account_rows:
        row = [acct_num, name, fqn, classification, acct_type]
        for m in months:
            bal = balance_lookup.get((acct_id, m), "")
            row.append(f"{float(bal):.2f}" if bal != "" else "")
        writer.writerow(row)
print(f"  Wrote {len(account_rows)} accounts x {len(months)} months to monthly_trial_balance.csv")

# 3. Accounts
print("Exporting accounts.csv...")
cur.execute("SELECT id, acct_num, name, fully_qualified_name, classification, account_type, account_subtype, active, current_balance FROM accounts ORDER BY acct_num, name")
rows = cur.fetchall()
with open("accounts.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([d[0] for d in cur.description])
    writer.writerows(rows)
print(f"  Wrote {len(rows)} rows to accounts.csv")

# ── Done ───────────────────────────────────────────────────────────────────────
con.close()
print(f"\nDone.")
print(f"MySQL database: {args.mysql_db} on {args.mysql_host}")
print(f"CSVs: gl_detail.csv, monthly_trial_balance.csv, accounts.csv")
