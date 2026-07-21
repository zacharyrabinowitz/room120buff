#!/usr/bin/env python
"""Test the member import feature with Toast invoices CSV."""

from member_import import parse_csv_file, process_import_data, validate_import_data, format_import_summary

# Read the Toast invoices CSV
print("Reading Toast invoices CSV...")
with open('the-draft-room-79-perry-street_invoices.csv', 'r', encoding='utf-8') as f:
    content = f.read()

# Parse CSV
rows = parse_csv_file(content)
print(f"✓ Parsed {len(rows)} invoice rows")
print(f"  Columns: {list(rows[0].keys())}\n")

# Process data
members = process_import_data(rows)
print(f"✓ Processed {len(members)} unique members")

# Validate
valid, errors = validate_import_data(members)
print(f"✓ Valid members: {len(valid)}")
if errors:
    print(f"⚠ Validation errors: {len(errors)}")
    for err in errors[:3]:
        print(f"  - {err}")

# Show summary
print(format_import_summary(members))

# Show sample members
print("Sample member data (first 5):")
print("-" * 70)
for i, (name, data) in enumerate(list(members.items())[:5], 1):
    print(f"{i}. {name}")
    print(f"   Email:          {data.get('email', 'N/A')}")
    print(f"   Phone:          {data.get('phone', 'N/A')}")
    print(f"   Amount Owed:    ${data.get('amount_owed', 0):.2f}")
    print(f"   Amount Spent:   ${data.get('amount_spent', 0):.2f}")
    print(f"   Invoice Count:  {data.get('invoice_count', 0)}")
    print()

print("✓ CSV import test completed successfully!")
