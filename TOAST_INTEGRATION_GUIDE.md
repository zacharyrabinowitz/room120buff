# Toast API Integration Guide

## Quick Start for Room 120 Portal

This guide explains how to use the safe Toast API integration to display member spending data without modifying Toast data.

---

## What Is This Integration?

**One-Way Data Flow:**
```
Toast POS (Read-Only)
    ↓
Your Room 120 App
    ↓ (Process Data)
Your Room 120 Database
    ↓
Member Portal (Display)
```

**Key Principle:** Toast data flows IN but never OUT. Your app reads from Toast, processes locally, and writes only to your own database.

---

## What You Can Do

### ✅ Allowed Operations

- **Display member spending** to members
- **Show transaction history** (what they ordered, when, how much)
- **Calculate loyalty metrics** (total spent, visit frequency, favorites)
- **Generate admin reports** (revenue, top customers, trends)
- **Send member notifications** ("You've spent $5,000! You've earned rewards...")

### ❌ Forbidden Operations

- **Create orders** in Toast from your app
- **Modify prices** in Toast from your app
- **Delete inventory** in Toast from your app
- **Change customer data** in Toast from your app
- **Update anything** in Toast from your app

**Remember:** Toast is read-only. Full stop.

---

## Member Endpoints

All member endpoints require:
1. User must be logged in
2. User must have "member" role
3. User can only access their own data (enforced on backend)

### Get Member Spending Summary

**Endpoint:**
```
GET /api/toast/member/<member_id>/spending
```

**Example:**
```bash
curl -H "Cookie: session=abc123" \
  http://localhost:5000/api/toast/member/42/spending
```

**Response:**
```json
{
  "customer_id": "42",
  "total_spent": 5432.15,
  "total_tax": 434.57,
  "total_gratuity": 1086.43,
  "transaction_count": 42,
  "last_visit": "2026-05-19T18:30:00",
  "first_visit": "2025-01-01T12:00:00",
  "orders": [
    {
      "id": "order_123",
      "timestamp": "2026-05-19T18:30:00",
      "total": 89.50,
      "subtotal": 75.00,
      "taxAmount": 7.50,
      "gratuityAmount": 7.00,
      "items": [
        {
          "name": "Grilled Branzino",
          "quantity": 1,
          "price": 32.00
        }
      ]
    }
  ]
}
```

**Use Cases:**
- Member dashboard: "You've spent $5,432 lifetime"
- Loyalty program: "Spend $10,000 for VIP status"
- Analytics: "Your favorite restaurant time is 6-7 PM"

**Security:**
- ✓ Member can only see own data
- ✓ Rate limited (100 requests/min)
- ✓ Error messages don't leak details

---

### Get Transaction History

**Endpoint:**
```
GET /api/toast/member/<member_id>/transactions?start_date=2026-05-01&end_date=2026-05-31&limit=50
```

**Parameters:**
- `start_date` (optional): ISO format `YYYY-MM-DD`
- `end_date` (optional): ISO format `YYYY-MM-DD`
- `limit` (optional): Max results (default 50, max 500)

**Example:**
```bash
# Last 30 days
curl -H "Cookie: session=abc123" \
  "http://localhost:5000/api/toast/member/42/transactions?start_date=2026-04-19&end_date=2026-05-19"

# Specific month
curl -H "Cookie: session=abc123" \
  "http://localhost:5000/api/toast/member/42/transactions?start_date=2026-05-01&end_date=2026-05-31&limit=100"
```

**Response:**
```json
{
  "member_id": "42",
  "transaction_count": 12,
  "transactions": [
    {
      "id": "order_987",
      "timestamp": "2026-05-19T18:30:00",
      "total": 89.50,
      "subtotal": 75.00,
      "taxAmount": 7.50,
      "gratuityAmount": 7.00,
      "paymentMethod": "Credit Card",
      "items": [
        {
          "name": "Branzino",
          "quantity": 1,
          "price": 32.00
        },
        {
          "name": "Wine - Vermentino",
          "quantity": 1,
          "price": 43.00
        }
      ]
    }
  ]
}
```

**Use Cases:**
- Transaction history page
- Receipt lookup
- Item ordering trends
- Date-based filtering (spending by season)

**Security:**
- ✓ Date format validated
- ✓ Limit capped at 500
- ✓ Member can only see own data

---

### Get Member Profile

**Endpoint:**
```
GET /api/toast/member/<member_id>/info
```

**Response:**
```json
{
  "id": "42",
  "name": "John Doe",
  "email": "john@example.com",
  "phone": "555-1234",
  "joinDate": "2025-01-01",
  "loyaltyStatus": "VIP"
}
```

**Security:**
- ✓ Even stricter rate limiting (50 requests/min)
- ✓ Less frequently accessed

---

## Admin Endpoints

All admin endpoints require:
1. User must be logged in
2. User must have "admin" role
3. Very strict rate limiting (5-50 requests/min)

### Get Revenue Report

**Endpoint:**
```
GET /api/toast/admin/revenue-report?start_date=2026-05-01&end_date=2026-05-31
```

**Parameters (Required):**
- `start_date`: ISO format `YYYY-MM-DD`
- `end_date`: ISO format `YYYY-MM-DD`
- Max range: 90 days

**Example:**
```bash
curl -H "Cookie: session=admin123" \
  "http://localhost:5000/api/toast/admin/revenue-report?start_date=2026-05-01&end_date=2026-05-31"
```

**Response:**
```json
{
  "start_date": "2026-05-01",
  "end_date": "2026-05-31",
  "total_revenue": 45230.50,
  "total_transactions": 542,
  "average_transaction": 83.47,
  "total_tax": 3618.44,
  "total_gratuity": 9046.10,
  "payment_breakdown": {
    "credit_card": 38445.12,
    "cash": 6785.38
  }
}
```

**Use Cases:**
- Monthly revenue reports for Apex Artist Management
- Trend analysis (May vs June)
- Payment method comparison

**Security:**
- ✓ Admin only
- ✓ Date range validated (max 90 days prevents huge queries)
- ✓ 5 requests/hour max

---

### Get Members Spending Leaderboard

**Endpoint:**
```
GET /api/toast/admin/members/spending-leaderboard?limit=10&order=desc
```

**Parameters:**
- `limit` (optional): Top N members (default 10, max 100)
- `order` (optional): `desc` (default) or `asc`

**Example:**
```bash
# Top 20 spenders
curl -H "Cookie: session=admin123" \
  "http://localhost:5000/api/toast/admin/members/spending-leaderboard?limit=20"
```

**Response:**
```json
{
  "count": 10,
  "leaderboard": [
    {
      "member_id": "42",
      "member_name": "John Doe",
      "total_spent": 12450.75,
      "transaction_count": 156,
      "last_transaction": "2026-05-19T18:30:00"
    },
    {
      "member_id": "15",
      "member_name": "Jane Smith",
      "total_spent": 9876.50,
      "transaction_count": 124,
      "last_transaction": "2026-05-18T19:00:00"
    }
  ]
}
```

**Use Cases:**
- VIP member identification
- Loyalty rewards ("Top 10 members this year")
- Marketing analysis

**Security:**
- ✓ Admin only
- ✓ 30 requests/min max (expensive query)

---

### Manual Sync Trigger

**Endpoint:**
```
POST /api/toast/admin/sync-member-data
Content-Type: application/json
```

**Request Body:**
```json
{
  "member_id": "optional_member_id",
  "force": false
}
```

**Example:**
```bash
curl -X POST \
  -H "Cookie: session=admin123" \
  -H "Content-Type: application/json" \
  -d '{"force": true}' \
  http://localhost:5000/api/toast/admin/sync-member-data
```

**Response:**
```json
{
  "status": "sync_queued",
  "sync_id": 123,
  "message": "Sync will complete in background"
}
```

**Use Cases:**
- Manual refresh of member data
- Periodic background syncs
- On-demand data pull before reports

**Security:**
- ✓ Admin only
- ✓ 5 requests/hour max (very expensive operation)
- ✓ Queued in background (doesn't block response)

---

## Implementing in Your App

### Frontend: Member Spending Dashboard

**HTML Template:**
```html
<div class="member-dashboard">
  <h2>{{ member.first_name }}'s Profile</h2>
  
  <div class="spending-summary">
    <h3>Your Spending at {{ restaurant_name }}</h3>
    <div id="spending-data">Loading...</div>
  </div>
  
  <div class="transaction-history">
    <h3>Recent Transactions</h3>
    <div id="transactions-data">Loading...</div>
  </div>
</div>

<script>
// Fetch spending summary
fetch(`/api/toast/member/{{ member.id }}/spending`)
  .then(r => r.json())
  .then(data => {
    document.getElementById('spending-data').innerHTML = `
      <p>Total Spent: $${data.total_spent.toFixed(2)}</p>
      <p>Last Visit: ${new Date(data.last_visit).toLocaleDateString()}</p>
      <p>Visits: ${data.transaction_count}</p>
    `;
  })
  .catch(e => console.error('Error loading spending:', e));

// Fetch recent transactions
fetch(`/api/toast/member/{{ member.id }}/transactions?limit=10`)
  .then(r => r.json())
  .then(data => {
    const html = data.transactions.map(tx => `
      <div class="transaction">
        <span>${new Date(tx.timestamp).toLocaleDateString()}</span>
        <span>$${tx.total.toFixed(2)}</span>
      </div>
    `).join('');
    document.getElementById('transactions-data').innerHTML = html;
  });
</script>
```

### Backend: Sync Data Periodically

**Scheduled Job (using APScheduler):**
```python
from apscheduler.schedulers.background import BackgroundScheduler
from toast_api import get_member_spending
from app import db
from models import ToastMemberSpending
from datetime import datetime

def sync_member_spending():
    """Background job to sync member spending from Toast."""
    try:
        # Get all members
        members = User.query.filter_by(active=True).all()
        
        for member in members:
            # Fetch from Toast
            spending = get_member_spending(member.member_number)
            
            if spending:
                # Update local database
                stat = ToastMemberSpending.query.filter_by(
                    member_id=member.id
                ).first() or ToastMemberSpending()
                
                stat.member_id = member.id
                stat.total_spent = spending['total_spent']
                stat.transaction_count = spending['transaction_count']
                stat.last_synced = datetime.utcnow()
                
                db.session.add(stat)
        
        db.session.commit()
        logger.info(f"Synced {len(members)} members")
        
    except Exception as e:
        logger.error(f"Sync failed: {e}")

# Setup scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(sync_member_spending, 'cron', hour=2, minute=0)  # Daily at 2 AM
scheduler.start()
```

---

## Error Handling

All endpoints return safe error messages:

### 401 Unauthorized
```json
{
  "error": "You must log in first"
}
```
*Cause:* Not logged in. Redirect to login.

### 403 Forbidden
```json
{
  "error": "You do not have permission to access this resource"
}
```
*Cause:* Wrong role (member trying to access admin endpoint) or trying to access another member's data.

### 404 Not Found
```json
{
  "error": "The requested data could not be found"
}
```
*Cause:* Member ID doesn't exist or has no transactions.

### 400 Bad Request
```json
{
  "error": "Invalid input provided. Please check your request"
}
```
*Cause:* Invalid date format, negative limit, etc.

### 429 Too Many Requests
```json
{
  "error": "Too many requests. Please slow down"
}
```
*Cause:* Rate limit exceeded. Wait before making more requests.

### 500 Internal Server Error
```json
{
  "error": "An error occurred. Please try again later"
}
```
*Cause:* Server error. Check logs. No technical details exposed.

---

## Testing the Integration

### Test 1: Member Can See Own Data

```bash
# Login as member
curl -c cookies.txt -X POST -d "username=john&password=pass" \
  http://localhost:5000/login

# Access own spending
curl -b cookies.txt \
  http://localhost:5000/api/toast/member/42/spending

# Should return: 200 OK with spending data
```

### Test 2: Member Cannot See Other's Data

```bash
# Try to access another member's data
curl -b cookies.txt \
  http://localhost:5000/api/toast/member/99/spending

# Should return: 403 Forbidden
```

### Test 3: Rate Limiting Works

```bash
# Rapid requests (100 should work, 101st fails)
for i in {1..105}; do
  curl -b cookies.txt \
    http://localhost:5000/api/toast/member/42/spending
done

# Requests 101+ should return: 429 Too Many Requests
```

### Test 4: Admin Can See Reports

```bash
# Login as admin
curl -c admin_cookies.txt -X POST -d "username=admin&password=pass" \
  http://localhost:5000/login

# Access revenue report
curl -b admin_cookies.txt \
  "http://localhost:5000/api/toast/admin/revenue-report?start_date=2026-05-01&end_date=2026-05-31"

# Should return: 200 OK with revenue data
```

---

## Monitoring & Maintenance

### Check Audit Logs

```bash
# View recent API access
tail -f logs/audit.log

# Example output:
# 2026-05-19 14:32:15 - API_ACCESS: {"user_id": 42, "action": "view_spending_summary", ...}
# 2026-05-19 14:33:22 - FAILED_ACCESS: {"reason": "member trying to access other's data", ...}
```

### Check Rate Limiting

```bash
# View security events
tail -f logs/security.log

# Look for rate limit warnings:
# WARNING - Rate limit exceeded for member_42
```

### Monitor Token Refresh

```bash
# Check if Toast token is being refreshed
grep "Toast API token" logs/app.log

# Should see:
# INFO - Successfully obtained Toast API token (expires in 3600s)
```

---

## Common Issues & Solutions

### Issue: "Unable to load data"
**Cause:** Toast API down, invalid credentials, or member has no transactions  
**Solution:** Check Toast status page, verify credentials in .env, check audit logs

### Issue: Rate limit hit too quickly
**Cause:** Frontend polling too aggressively  
**Solution:** Add caching (browser cache, server-side cache for 5 minutes)

### Issue: Transactions missing
**Cause:** Sync hasn't run yet, or member data not in Toast  
**Solution:** Manually trigger sync endpoint, verify member exists in Toast

### Issue: Wrong data for member
**Cause:** Member ID mismatch (check format - string vs int)  
**Solution:** Verify member IDs match between Room 120 DB and Toast

---

## Next Steps

1. **Get Toast credentials** from Toast support (read-only only!)
2. **Update `.env`** with your credentials
3. **Test in sandbox** before production
4. **Deploy to production** with HTTPS enabled
5. **Monitor logs** daily for first week
6. **Launch member portal** with spending features

---

**Need Help?** Check SECURITY.md for security questions or contact Toast support for API issues.
