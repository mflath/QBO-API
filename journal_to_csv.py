import urllib.request
import json
import csv

url = "https://api.nobleledger.com/qbo/journal_entries"

req = urllib.request.Request(url)
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())

entries = data["QueryResponse"]["JournalEntry"]

with open("journal_entries.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "Id", "DocNumber", "TxnDate", "Currency", "PrivateNote", "TotalAmt",
        "LineId", "Description", "Amount", "PostingType",
        "AccountId", "AccountName", "DepartmentId", "DepartmentName"
    ])

    for entry in entries:
        currency = entry.get("CurrencyRef", {}).get("value", "")
        for line in entry["Line"]:
            detail = line["JournalEntryLineDetail"]
            account = detail.get("AccountRef", {})
            dept = detail.get("DepartmentRef", {})
            writer.writerow([
                entry["Id"],
                entry.get("DocNumber", ""),
                entry.get("TxnDate", ""),
                currency,
                entry.get("PrivateNote", ""),
                entry["TotalAmt"],
                line["Id"],
                line.get("Description", ""),
                line["Amount"],
                detail["PostingType"],
                account.get("value", ""),
                account.get("name", ""),
                dept.get("value", ""),
                dept.get("name", ""),
            ])

print(f"Wrote {sum(len(e['Line']) for e in entries)} rows to journal_entries.csv")
