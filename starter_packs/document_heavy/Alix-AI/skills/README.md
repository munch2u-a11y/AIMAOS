# Skills Directory

Skills are reusable Python scripts the agent can run to process or extract information. Each skill lives in its own subdirectory.

## Folder Structure

```
skills/
└── extract_tax_fields/
    ├── skill.yaml          # Metadata
    └── run.py              # Execution script
```

## `skill.yaml` Metadata

The `skill.yaml` file defines inputs and outputs for the agent:
```yaml
name: extract_tax_fields
description: "Extracts client name, SSN, income, and deductions from a plain text document."
input: "Plain text contents of a document"
output: "JSON with fields: client_name, ssn, income, deductions"
created: "2026-07-16"
```

## `run.py` Contract

The script must:
1. Read input data from **stdin**.
2. Perform processing.
3. Write output to **stdout**.
4. Return exit code `0` on success.
5. Write errors or warnings to **stderr**.

Example script:
```python
import sys
import json
import re

def main():
    # Read stdin
    input_text = sys.stdin.read()
    
    # Simple regex extraction logic
    name_match = re.search(r"Name:\s*([^\n]+)", input_text)
    ssn_match = re.search(r"SSN:\s*([^\n]+)", input_text)
    
    data = {
        "client_name": name_match.group(1).strip() if name_match else "Unknown",
        "ssn": ssn_match.group(1).strip() if ssn_match else "Unknown"
    }
    
    # Output to stdout
    print(json.dumps(data, indent=2))

if __name__ == "__main__":
    main()
```
