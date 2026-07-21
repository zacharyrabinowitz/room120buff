# Quick Start: CSV Member Import

## What We Built

A complete member CSV import system that:
- ✅ Parses Toast invoices CSV files
- ✅ Aggregates invoices by customer
- ✅ Calculates member balances automatically
- ✅ Creates or updates members in your database
- ✅ Shows balance data on member profile pages

## Test Results

Your Toast invoices CSV contains:
- **224 invoice rows**
- **87 unique members** (all valid)
- **$32,902.80 total owed**
- **$81,895.27 total spent**

Sample members created:
```
Tony Lana
  - Amount Owed: $1,765.46
  - Invoice Count: 4

Tim Calkins
  - Amount Owed: $0.00
  - Amount Spent: $3,166.52
  - Invoice Count: 4

Stas Balanevsky
  - Amount Owed: $761.25
  - Amount Spent: $4,368.30
  - Invoice Count: 8
```

## How to Use

### Step 1: Access the Import Page
- Log in as admin
- Go to **Manage Members**
- Click **"Import Members"** button

### Step 2: Upload CSV File
- Select your CSV file (Toast invoices export or generic member list)
- Click "Import Members"
- Wait for success message

### Step 3: View Member Balances
- Go to **Manage Members**
- Click any member name
- Click **"Balance"** tab
- See their:
  - Outstanding balance
  - Total spending
  - Payment history
  - Minimum requirement progress

## Supported CSV Formats

### Format 1: Toast Invoices (Recommended)
Export from Toast with columns:
- `customer_name` (e.g., "John Doe")
- `email`
- `phone`
- `total`
- `amount_paid`
- `status` (OPEN or PAID)
- `created_date`

**Automatic processing:**
- Balances calculated: total - amount_paid
- Multiple invoices aggregated per customer
- Members created with default password (firstname+lastname+123)

### Format 2: Generic Members List
Create CSV with:
- `first_name` (required)
- `last_name` (required)
- `email` (optional)
- `phone` (optional)
- `amount_owed` (optional)
- `amount_spent` (optional)

## Features

✅ **Duplicate Detection**
- Matches by email or first_name + last_name
- Updates existing members instead of duplicating

✅ **Balance Display**
- Members see their balance on profile
- Amount owed, spent, tax, gratuity tracking
- Payment history visible

✅ **Default Passwords**
- New members get: {firstname}{lastname}123
- Members MUST change on first login
- Logged in admin panel

✅ **Error Handling**
- Validation errors displayed per row
- Incomplete rows skipped
- Summary shows created/updated count

## Database Integration

All imported data goes directly into:
- `User.first_name` / `User.last_name`
- `User.email` / `User.phone`
- `User.amount_owed` (outstanding balance)
- `User.amount_spent` (total spending)
- `User.membership_type` (set to "single")

Shows on member profile in the **"Balance"** tab.

## Files Created

1. **member_import.py** - CSV parsing & validation logic
2. **admin_import_members.html** - Import upload page
3. **test_import.py** - Test script (demonstrates functionality)
4. **MEMBER_IMPORT_GUIDE.md** - Full documentation
5. **Route: /admin/import-members** - GET (form) / POST (upload)

## Next Steps

1. ✅ **Test the import** (we already did!)
   - Run: `python test_import.py`
   - Verified 87 members parsed correctly

2. **Start the Flask app** (when ready to go live)
   - Run: `python app.py`
   - Visit: http://localhost:5000/admin/import-members

3. **Import your Toast data**
   - Click "Import Members" button
   - Select: `the-draft-room-79-perry-street_invoices.csv`
   - Members created with balances loaded

4. **Members can view balances**
   - They log in to their account
   - Click Profile → Balance tab
   - See their outstanding balance and spending

## Troubleshooting

**Q: Members imported but no balances show?**
A: Balances are in the Balance tab of their profile. Each member's page shows their data.

**Q: Password not working after import?**
A: Default password is {firstname}{lastname}123 (no spaces, exact case from CSV)
Example: "John Doe" → "JohnDoe123"

**Q: Want to reimport?**
A: Just upload again - existing members get updated, new ones are created.

**Q: See only some members?**
A: Duplicate detection works by email or name. If duplicates exist, one gets updated instead of creating a new record.

---

**Status:** ✅ Ready to use!

For full details, see: [MEMBER_IMPORT_GUIDE.md](MEMBER_IMPORT_GUIDE.md)
