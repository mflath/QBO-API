import urllib.request
import json
import csv

url = "https://api.nobleledger.com/qbo/trial_balance?start_date=2025-04-01&end_date=2026-03-31"

req = urllib.request.Request(url)
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())

rows = data["Rows"]["Row"]

with open("trial_balance.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Account", "Debit", "Credit"])

    for row in rows:
        if "ColData" in row:
            cols = row["ColData"]
        elif "Summary" in row:
            cols = row["Summary"]["ColData"]
        else:
            continue
        writer.writerow([
            cols[0].get("value", ""),
            cols[1].get("value", ""),
            cols[2].get("value", ""),
        ])

print(f"Wrote {len(rows)} rows to trial_balance.csv")
