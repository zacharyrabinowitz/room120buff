# Member CSV Import Guide

## Overview

The CSV Import feature allows admins to bulk import members with their balance information from a CSV file. This is perfect for:

- Importing historical member data from Toast invoices
- Migrating from another system
- Bulk loading member lists with existing balances
- Syncing member data from external sources

---

## Getting Started

### Step 1: Access Import Page

As an admin, navigate to:
- **Dashboard** → **Manage Members** → **Import Members** button

Or direct URL:
```
/admin/import-members
```

### Step 2: Prepare Your CSV File

Choose your data source format (see formats below).

### Step 3: Upload and Import

1. Select your CSV file
2. Click "Import Members"
3. Review results
4. Members are created with default password (must change on first login)

---

## CSV Formats Supported

### Format 1: Toast Invoices (Recommended)

**When to use:** You have a CSV export from your Toast POS system

**Required columns:**
- `customer_name` - Customer full name (e.g., "John Doe")
- `email` - Email address
- `phone` - Phone number  
- `total` - Invoice total
- `amount_paid` - Amount paid toward invoice
- `status` - "OPEN" (unpaid) or "PAID"
- `created_date` - Date of invoice

**What happens:**
- Multiple invoices per customer are aggregated
- Balance = total - amount_paid for OPEN invoices
- Amounts are summed by customer
- Latest invoice date is tracked

**Example:**
```csv
customer_name,email,phone,total,amount_paid,status,created_date
Tony Lana,ajlforthedefense@gmail.com,7163103030,209.55,0.0,OPEN,8/12/25, 8:01 PM
Tim Calkins,gond97@yahoo.com,5853565563,276.13,276.13,PAID,8/12/25, 8:01 PM
Steve LoVullo,steve.lovullo@rtspecialty.com,7163140303,51.0,51.0,PAID,8/12/25, 8:00 PM
```

### Format 2: Generic Members

**When to use:** You have a simple member list with balances

**Required columns:**
- `first_name` - First name (required)
- `last_name` - Last name (required)
- `email` - Email address
- `phone` - Phone number
- `amount_owed` - Current balance (optional, defaults to 0)
- `amount_spent` - Total lifetime spending (optional, defaults to 0)

**Example:**
```csv
first_name,last_name,email,phone,amount_owed,amount_spent
John,Doe,john@example.com,555-1234,500.00,2500.00
Jane,Smith,jane@example.com,555-5678,0.00,5000.00
Bob,Johnson,bob@example.com,555-9999,1200.50,3200.00
```

---

## What Gets Imported

### Fields Created

| Field | Source | Description |
|-------|--------|-------------|
| `first_name` | CSV | Member's first name |
| `last_name` | CSV | Member's last name |
| `email` | CSV | Email address |
| `phone` | CSV | Phone number |
| `amount_owed` | Calculated | Outstanding balance |
| `amount_spent` | Summed | Total lifetime spending |
| `username` | Generated | first_name.last_name (lowercase) |
| `password` | Generated | firstname+lastname+123 (must change) |
| `role` | Fixed | "member" |
| `membership_type` | Fixed | "single" |
| `active` | Fixed | true |

### Fields NOT Imported

- Member number
- Membership type (set to "single" for all)
- Tax amounts
- Gratuity amounts
- Minimum adjustment

---

## Duplicate Handling

When a member exists, the import **updates** them instead of creating duplicates:

**Detection method:** Member is considered existing if:
- Email matches an existing member, OR
- First name + last name matches an existing member

**Update behavior:**
- `amount_owed`: Takes maximum (keeps higher balance)
- `amount_spent`: Takes maximum (keeps higher total)
- `email`: Updated if provided in CSV
- `phone`: Updated if provided in CSV
- Other fields: Not modified

---

## Default Passwords

### ⚠️ Important Security Note

New members are created with a default password format:
```
{first_name}{last_name}123
```

Examples:
- John Doe → `JohnDoe123`
- Jane Smith → `JaneSmith123`

**Members MUST change this password on first login.**

### How Members Change Password

1. Member logs in with default password
2. Navigate to profile
3. Click "Edit Info" 
4. Update password
5. Save

---

## Viewing Imported Balances

### Member View

Members can see their balance by:
1. Logging into their account
2. Going to **Profile**
3. Clicking **Balance** tab
4. Viewing:
   - Amount Owed
   - Amount Spent
   - Tax Owed/Paid
   - Gratuity Owed/Paid
   - Membership Status

### Admin View

Admins can see all member balances:
1. Go to **Manage Members**
2. Click on member name
3. View **Balance** tab
4. See full financial summary

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| "No file uploaded" | No CSV selected | Select a CSV file |
| "File must be a CSV file" | Wrong file format | Export as CSV (not Excel) |
| "Validation error: Missing first name" | Empty first_name column | Fill in all required fields |
| "No valid members to import" | All rows had errors | Check file format matches documentation |

### Validation Rules

- First name: Required, non-empty
- Last name: Required, non-empty
- Amount owed: Must be positive (≥0)
- Amount spent: Must be positive (≥0)
- Email: Optional but recommended
- Phone: Optional but recommended

---

## Import Process Flow

```
┌─────────────────────┐
│  Select CSV File    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Auto-detect Format │ ◄─── Toast Invoices or Generic Members
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Parse CSV Rows     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Validate Data      │ ◄─── Check for errors
└──────────┬──────────┘
           │
      ┌────┴────┐
      │          │
     OK        ERRORS
      │          │
      ▼          ▼
   IMPORT    ├─ List issues
      │      └─ Cancel
      ▼
┌─────────────────────┐
│ Check Duplicates    │ ◄─── By email or name
└──────────┬──────────┘
           │
      ┌────┴────┐
      │          │
    NEW       EXISTS
      │          │
      ▼          ▼
   CREATE     UPDATE
      │          │
      └────┬─────┘
           │
           ▼
┌─────────────────────┐
│  Save to Database   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Show Summary       │
│ ✓ Imported: X      │
│ ✓ Updated: Y       │
└─────────────────────┘
```

---

## Troubleshooting

### Import Fails Silently

**Check:**
1. Browser console for JavaScript errors
2. Server logs: `tail logs/app.log`
3. Make sure file is actually CSV format

**Solution:**
- Ensure CSV is properly formatted
- Check column headers match expected format
- Verify no special characters in data

### Members Show but No Balance

**Check:**
1. Member profile → Balance tab
2. Verify balance fields are populated

**Solution:**
1. Try reimporting with correct amounts
2. Manually edit member balance in admin panel
3. Check CSV amounts are numeric (not formatted as text in Excel)

### Can't Login After Import

**Issue:** Default password not working

**Solution:**
1. Check username is correct (firstname.lastname lowercase)
2. Try password reset if available
3. Have admin reset member password

### Duplicate Members Created

**Issue:** Same person appears twice

**Solution:**
1. Check for email variations (spaces, case)
2. Manually merge if needed
3. Delete duplicate and reimport

---

## Best Practices

### Before Import

- ✓ Backup your database
- ✓ Test with small sample first
- ✓ Verify CSV format in text editor (not Excel)
- ✓ Remove duplicate rows manually
- ✓ Clean up phone numbers (consistent format)
- ✓ Verify all required columns present

### After Import

- ✓ Verify member count matches expectation
- ✓ Spot check a few member balances
- ✓ Notify members of login credentials
- ✓ Ask members to change default password
- ✓ Send password reset links if preferred
- ✓ Audit log import in admin notes

### Regular Imports

- ✓ Do not re-import entire list (use updates only)
- ✓ Export existing members to compare
- ✓ Only import new members or balance updates
- ✓ Keep records of each import for audit trail

---

## Exporting Members

To export current members (for backup or review):

1. Go to **Manage Members**
2. Click **Export Members** button
3. CSV will download with all current member data

This is useful for:
- Creating backups
- Auditing member list
- Planning next import
- Sharing data with accounting

---

## API Endpoint

For programmatic import (advanced):

```bash
POST /admin/import-members
Content-Type: multipart/form-data

File: csv_file (multipart)

Response:
200 OK - Import successful
400 Bad Request - File error
403 Forbidden - Not admin
```

---

## Support

For issues or questions:

1. Check this guide's Troubleshooting section
2. Review logs: `logs/app.log`
3. Contact system administrator

---

**Last Updated:** May 20, 2026  
**Version:** 1.0
