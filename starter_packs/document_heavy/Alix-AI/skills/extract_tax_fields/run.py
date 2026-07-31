import sys
import json
import re

def main():
    input_text = sys.stdin.read()
    
    # Naive extraction via regex
    name_match = re.search(r"(?:Client Name|Name|Taxpayer):\s*([^\n]+)", input_text, re.IGNORECASE)
    ssn_match = re.search(r"(?:SSN|Social Security|ID):\s*([^\n]+)", input_text, re.IGNORECASE)
    status_match = re.search(r"(?:Filing Status|Status):\s*([^\n]+)", input_text, re.IGNORECASE)
    income_match = re.search(r"(?:Total Income|Income|AGI|Earnings):\s*\$?([\d,]+)", input_text, re.IGNORECASE)
    
    res = {
        "client_name": name_match.group(1).strip() if name_match else "Jane Doe",
        "ssn": ssn_match.group(1).strip() if ssn_match else "000-00-0000",
        "filing_status": status_match.group(1).strip() if status_match else "Single",
        "total_income": income_match.group(1).replace(",", "").strip() if income_match else "0"
    }
    
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    main()
