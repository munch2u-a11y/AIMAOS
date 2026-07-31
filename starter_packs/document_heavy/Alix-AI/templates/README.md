# Templates Directory

Place templates in this directory. A template can be a single `.docx` file, or a folder containing a `template.docx` and a `template.yaml`.

## Jinja2 Placeholders

Your `.docx` templates should contain placeholders in Jinja2 syntax:
- `{{ client_name }}`
- `{{ client_address }}`
- `{{ total_income }}`

## Using `template.yaml` (Recommended)

To help the agent understand which fields a template requires, you can place it inside a folder alongside a `template.yaml` metadata file.

Example structure:
```
templates/
└── tax_return_1040/
    ├── template.docx
    └── template.yaml
```

Example `template.yaml`:
```yaml
name: tax_return_1040
description: "IRS Form 1040 template for individual tax returns"
fields:
  - name: client_name
    description: "Full legal name of the taxpayer"
    required: true
  - name: ssn
    description: "Social Security Number"
    required: true
  - name: filing_status
    description: "Single, Married Filing Jointly, etc."
    required: true
  - name: total_income
    description: "Total income for the tax year"
    required: true
```
