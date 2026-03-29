import urllib.request
import urllib.error
import json
import csv
import argparse
import sys

parser = argparse.ArgumentParser(description="Fetch chart of accounts")
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

# Fetch chart of accounts
url = "https://api.nobleledger.com/qbo/accounts"

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

accounts = data.get("QueryResponse", {}).get("Account", [])
print(f"Fetched {len(accounts)} accounts")

with open("chart_of_accounts.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "Id", "AcctNum", "Name", "FullyQualifiedName",
        "Classification", "AccountType", "AccountSubType",
        "Active", "CurrentBalance"
    ])
    for acct in accounts:
        writer.writerow([
            acct.get("Id", ""),
            acct.get("AcctNum", ""),
            acct.get("Name", ""),
            acct.get("FullyQualifiedName", ""),
            acct.get("Classification", ""),
            acct.get("AccountType", ""),
            acct.get("AccountSubType", ""),
            acct.get("Active", ""),
            acct.get("CurrentBalance", ""),
        ])

print(f"Wrote {len(accounts)} rows to chart_of_accounts.csv")
