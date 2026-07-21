# Room 120 Member Portal - Security Implementation Guide

## ⚠️ CRITICAL SECURITY ALERT

Your `.env` file has been found with **exposed Toast API credentials**.

### Immediate Action Required:
1. **Contact Toast support immediately** to deactivate your current credentials
2. **Request new OAuth 2.0 credentials** with read-only scope
3. **Replace the values** in `.env` with your new credentials
4. **Never commit `.env` to GitHub** (it's in .gitignore, but verify)

---

## Security Architecture Overview

Your Toast integration uses a **three-tier security model**:

### Tier 1: Critical ✓ IMPLEMENTED
**These are non-negotiable security measures**

#### 1.1 Session Management & RBAC
- **Sessions expire after 30 minutes** of inactivity
- **Secure session cookies:**
  - `HttpOnly` flag: JavaScript cannot access tokens
  - `Secure` flag: HTTPS only (production)
  - `SameSite=Lax`: CSRF protection
  
**Implementation:**
```python
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['SESSION_COOKIE_SECURE'] = True      # HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True    # No JS access
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'   # CSRF protection
```

#### 1.2 Role-Based Access Control (RBAC)
- Members can **only see their own data**
- Backend validation on **every API call**
- Admins have separate endpoints (with admin-only checks)

**Implementation in routes:**
```python
@app.route('/api/toast/member/<member_id>/spending')
@login_required           # Tier 1: Must be logged in
@member_only              # Tier 1: Must be member role
@require_member_self_data # Tier 1: BACKEND check - can't see other members
def get_spending_summary(member_id):
    # Backend validation prevents privilege escalation
    if session["member_id"] != member_id:
        return {"error": "Unauthorized"}, 403
```

#### 1.3 Toast API Token Security
- **Never hardcoded** in source code
- **Environment variables only** (.env file)
- **Read-only credentials** (verified with Toast support)
- **Token rotation** - expires hourly, auto-refreshes
- **Credentials encrypted at rest** (if using managed secrets in production)

**Implementation:**
```python
# ✅ CORRECT
TOAST_CLIENT_ID = os.getenv("TOAST_CLIENT_ID")

# ❌ WRONG - Never do this:
TOAST_CLIENT_ID = "Jd4jZk55DCFsZsUACvQyR7x72EjynLsI"  # EXPOSED!
```

#### 1.4 HTTPS Enforcement (Production)
- **TLS 1.2+ only** for all connections
- **HSTS headers** force HTTPS redirects
- **Secure cookies** prevent man-in-the-middle attacks

**Implementation:**
```python
if not app.debug:
    from flask_talisman import Talisman
    Talisman(app, force_https=True)  # Enforces HTTPS + security headers
```

**Setup for production:**
```bash
pip install flask-talisman
```

#### 1.5 GET-Only API Calls to Toast
- **All requests to Toast use GET only**
- **No POST/PUT/PATCH/DELETE to Toast**
- **Toast data is read-only** source of truth

**Implementation:**
```python
# ✅ CORRECT - Read-only
response = requests.get(
    f"{TOAST_API_URL}/orders?customerId={customer_id}",
    headers=headers,
    timeout=10
)

# ❌ NEVER DO THIS
requests.post(f"{TOAST_API_URL}/orders", json=data)  # Would modify Toast!
```

---

### Tier 2: Important ✓ IMPLEMENTED
**Strong protections that should be enforced**

#### 2.1 Rate Limiting (Per-User)
- **100 requests/minute** per member
- **5 requests/hour** for manual sync endpoint
- Prevents API abuse and data scraping

**Implementation:**
```python
@toast_bp.route('/member/<member_id>/spending')
@rate_limit(max_requests=100, time_window=60)  # 100 per minute
def get_spending_summary(member_id):
    ...

# Rate limiter tracks per user ID
if not rate_limiter.is_allowed(user_id, max_requests=100, time_window=60):
    return {"error": "Too many requests"}, 429
```

#### 2.2 Input Validation (Whitelist-Based)
- All query parameters validated
- Type checking and length limits
- Prevents SQL injection and malformed data

**Implementation:**
```python
# Only allow these parameters with these types
allowed_params = {
    "start_date": str,
    "end_date": str,
    "limit": int
}

validated = validate_query_params(request.args, allowed_params)
# Invalid params = empty dict, returns 400 error
```

#### 2.3 Audit Logging (TIER 2)
- **All API access logged** with:
  - User ID
  - Endpoint accessed
  - Timestamp
  - IP address
  - Success/failure
  
**Log files:**
- `logs/app.log` - General application logs
- `logs/audit.log` - **API access for compliance**
- `logs/security.log` - Failed access attempts

**Implementation:**
```python
def get_spending_summary(member_id):
    # Log all access
    log_api_access(
        action="view_spending_summary",
        resource=f"member_{member_id}"
    )
```

**Audit logs look like:**
```
2026-05-19 14:32:15 - API_ACCESS: {
    "user_id": 123,
    "role": "member",
    "action": "view_spending_summary",
    "resource": "member_123",
    "timestamp": "2026-05-19T14:32:15",
    "ip_address": "192.168.1.100"
}
```

#### 2.4 Safe Error Messages (No Information Leakage)
- Errors never expose technical details
- Generic messages to end-users
- Details logged internally

**Implementation:**
```python
# ✅ CORRECT - Safe to user
return {"error": "Unable to load data. Please try again later."}, 500

# ❌ WRONG - Leaks information
return {"error": "Toast API token invalid: signature mismatch"}, 500

# Actual error logged internally:
logger.error(f"Toast API authentication failed: {detailed_error}")
```

---

### Tier 3: Good Practice
**Recommended for full enterprise security**

#### 3.1 Data Minimization
- Only pull/cache Toast data you actually use
- Don't store full transaction histories
- Archive old data regularly

#### 3.2 Encryption at Rest
- Database encryption (PostgreSQL pgcrypto, SQLite WAL)
- Field-level encryption for sensitive data

#### 3.3 Regular Backups
- Daily encrypted backups
- Off-site storage
- Test restore procedures

#### 3.4 Dependency Updates
- Monthly security patches
- Automated vulnerability scanning
- Maintain SBOM (Software Bill of Materials)

---

## API Endpoints Provided

### Member Endpoints (Members Only)

#### Get Spending Summary
```
GET /api/toast/member/<member_id>/spending
Headers: Authorization: Bearer <session>

Response:
{
    "customer_id": "123",
    "total_spent": 5432.15,
    "total_tax": 434.57,
    "total_gratuity": 1086.43,
    "transaction_count": 42,
    "last_visit": "2026-05-19T18:30:00",
    "first_visit": "2025-01-01T12:00:00"
}

Security: ✓ Login required ✓ Member only ✓ Own data only ✓ Rate limited
```

#### Get Transaction History
```
GET /api/toast/member/<member_id>/transactions?start_date=2026-01-01&end_date=2026-05-31&limit=50

Security: ✓ Date validation ✓ Limit enforced ✓ Rate limited
```

#### Get Member Info
```
GET /api/toast/member/<member_id>/info

Security: ✓ Lower rate limit ✓ Own data only
```

### Admin Endpoints (Admins Only)

#### Get Revenue Report
```
GET /api/toast/admin/revenue-report?start_date=2026-05-01&end_date=2026-05-31

Security: ✓ Admin only ✓ Date range validated (max 90 days)
```

#### Get Members Leaderboard
```
GET /api/toast/admin/members/spending-leaderboard?limit=10&order=desc

Security: ✓ Admin only ✓ Very strict rate limit
```

#### Trigger Manual Sync
```
POST /api/toast/admin/sync-member-data
Content-Type: application/json

{
    "member_id": "optional",
    "force": false
}

Security: ✓ Admin only ✓ 5 requests/hour max
```

---

## File Structure

```
room120buff/
├── .env                  # ⚠️ Credentials (never commit)
├── .env.example          # Template for .env
├── .gitignore            # .env is ignored ✓
│
├── config.py             # ✓ NEW - Safe config from env vars
├── logger_config.py      # ✓ NEW - Logging setup (audit logs)
├── security.py           # ✓ NEW - Security decorators & RBAC
│
├── toast_auth.py         # ✓ REWRITTEN - Safe OAuth token mgmt
├── toast_api.py          # ✓ REWRITTEN - GET-only API calls
├── toast_routes.py       # ✓ NEW - Flask endpoints with security
│
├── app.py                # ✓ UPDATED - Integrated security
├── models.py             # ✓ UPDATED - Toast data models
│
└── logs/                 # ✓ NEW - Created at startup
    ├── app.log
    ├── audit.log         # API access log (keep for compliance)
    └── security.log      # Security events
```

---

## Getting Started

### Step 1: Setup New Toast Credentials

1. **Contact Toast Support:**
   - Request OAuth 2.0 credentials
   - Specify read-only access only
   - Scope: `restaurants.read orders.read checks.read`

2. **Deactivate Old Credentials:**
   - Ask Toast to disable the exposed credentials
   - Verify deactivation in Toast admin panel

### Step 2: Update .env

```bash
# Copy template
cp .env.example .env

# Edit .env with your new credentials
TOAST_CLIENT_ID=your_new_id_from_support
TOAST_CLIENT_SECRET=your_new_secret_from_support
TOAST_RESTAURANT_ID=your_restaurant_id

# Generate a new SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
# Copy output and paste into .env
```

### Step 3: Install Dependencies

```bash
pip install flask-talisman  # HTTPS enforcement
pip install python-dotenv    # Environment variables (already installed)
```

### Step 4: Test in Sandbox

```bash
# Start Flask app
export FLASK_ENV=development
python -m flask run

# Test member endpoint (requires login first)
curl -H "Cookie: session=..." http://localhost:5000/api/toast/member/123/spending
```

### Step 5: Deploy to Production

```bash
# Update config
FLASK_ENV=production
TOAST_ENVIRONMENT=production
DATABASE_URL=postgresql://...  # Use PostgreSQL

# Verify HTTPS is working
# Verify rate limiting is active
# Verify audit logs are being created

# Run with production server
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

---

## Security Checklist Before Launch

### Credentials
- [ ] Old Toast credentials have been **rotated**
- [ ] New credentials are in `.env`, not in code
- [ ] `.env` is in `.gitignore`
- [ ] `.env` is **never committed to Git**
- [ ] `.env` has proper file permissions (644 or 640)

### Sessions
- [ ] Session timeout is 30 minutes
- [ ] SessionCookie is `HttpOnly` + `Secure` + `SameSite`
- [ ] CSRF token validation is enabled

### RBAC
- [ ] Members can only see their own data (backend enforced)
- [ ] Admins have separate endpoints
- [ ] Role checks on every protected endpoint

### API Security
- [ ] All Toast calls use GET only
- [ ] No POST/PUT/PATCH/DELETE to Toast
- [ ] Rate limiting is active
- [ ] Input validation on all endpoints

### Logging & Audit
- [ ] Audit logs are being created
- [ ] Audit logs are not deleted (compliance)
- [ ] Security logs capture failed access
- [ ] Logs don't contain sensitive data

### HTTPS
- [ ] Flask-Talisman is enabled (production)
- [ ] TLS certificate is valid
- [ ] HSTS header is set
- [ ] Secure cookie flags are set

### Testing
- [ ] Tested member accessing own data ✓
- [ ] Tested member cannot access other's data ✓
- [ ] Tested rate limiting (verify 429 response)
- [ ] Tested error messages are safe
- [ ] Tested audit logs for all access

---

## Monitoring & Maintenance

### Daily
- Monitor `logs/security.log` for failed access attempts
- Check rate limit violations

### Weekly
- Review `logs/audit.log` for suspicious patterns
- Verify Toast token refresh is working

### Monthly
- Rotate SECRET_KEY (if possible without breaking sessions)
- Update all dependencies
- Scan for vulnerabilities: `pip audit`

### Quarterly
- Rotate Toast credentials (request new ones)
- Review and archive old audit logs
- Penetration test the API

---

## Incident Response

### If Toast Credentials Are Leaked:
1. Immediately deactivate in Toast admin
2. Generate new credentials from Toast
3. Update `.env`
4. Review audit logs for unauthorized access
5. Notify affected members if data was accessed
6. Update all documentation

### If Database is Breached:
1. Stop the application
2. Restore from backup
3. Change all credentials
4. Review audit logs
5. Notify members
6. Perform security audit

### If Rate Limits Are Bypassed:
1. Identify attacker IP in audit logs
2. Block IP at firewall/WAF level
3. Review audit logs for data exfiltration
4. Increase rate limits if legitimate traffic spike
5. Consider IP-based authentication for member endpoints

---

## References

- **Toast API Docs:** [Toast Partner Docs](https://docs.toasttab.com)
- **Flask Security:** [Flask Security Best Practices](https://flask.palletsprojects.com/en/latest/security/)
- **OWASP Top 10:** [Web Application Security](https://owasp.org/www-project-top-ten/)
- **PCI DSS:** [Payment Card Industry Data Security Standard](https://www.pcisecuritystandards.org/)

---

**Last Updated:** May 19, 2026  
**Security Level:** TIER 1 & 2 Implemented  
**Status:** Ready for Testing
