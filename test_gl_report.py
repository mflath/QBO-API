import urllib.request
import urllib.error
import json
import argparse
import sys

parser = argparse.ArgumentParser(description="Test QBO GeneralLedger report via NobelLedger")
parser.add_argument("--start-date", required=False, default="2025-04-01")
parser.add_argument("--end-date",   required=False, default="2025-04-01")  # single day to keep output small
parser.add_argument("--email",      required=False, default="mstoews@hotmail.com")
parser.add_argument("--password",   required=False, default="1628888")
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

token = login_data.get("idToken")
if not token:
    print("Login failed: no token in response", file=sys.stderr)
    sys.exit(1)

print("Login successful\n")

def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    })
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())

# ── Try GeneralLedger report ───────────────────────────────────────────────────
url = (
    f"https://api.nobleledger.com/qbo/run_report"
    f"?report_name=GeneralLedger"
    f"&start_date={args.start_date}"
    f"&end_date={args.end_date}"
    f"&accounting_method=Accrual"
)

print(f"Fetching: {url}\n")

try:
    data = fetch_json(url)
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code} {e.reason}", file=sys.stderr)
    body = e.read().decode()
    print(f"Response body: {body}", file=sys.stderr)
    sys.exit(1)

# ── Print top-level keys ───────────────────────────────────────────────────────
print("Top-level keys:", list(data.keys()))
print()

# ── Print Columns if present ───────────────────────────────────────────────────
if "Columns" in data:
    cols = data["Columns"].get("Column", [])
    print(f"Columns ({len(cols)}):")
    for c in cols:
        print(f"  {c}")
    print()

# ── Print first few rows of the Rows section ──────────────────────────────────
if "Rows" in data:
    rows = data["Rows"].get("Row", [])
    print(f"Total top-level rows: {len(rows)}")
    print("\nFirst 3 rows (full structure):")
    for row in rows[:3]:
        print(json.dumps(row, indent=2))
        print("---")
else:
    print("No 'Rows' key found in response.")
    print("\nFull response (first 3000 chars):")
    print(json.dumps(data, indent=2)[:3000])
