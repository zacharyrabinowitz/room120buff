# Room 120 Toast API Integration - Setup & Validation Checklist

## Pre-Deployment Setup

### Step 1: Credential Rotation (⚠️ CRITICAL)
- [ ] **Contact Toast Support:**
  - Request new OAuth 2.0 credentials
  - Specify: Read-only access only
  - Scope: `restaurants.read orders.read checks.read`
  
- [ ] **Deactivate Old Credentials:**
  - Verify old credentials in `.env` were exposed
  - Ask Toast to immediately deactivate them
  - Confirm deactivation in Toast admin panel
  
- [ ] **Store New Credentials Safely:**
  - Receive new `TOAST_CLIENT_ID` and `TOAST_CLIENT_SECRET`
  - Store temporarily in secure password manager
  - Do NOT write to any file yet

### Step 2: Environment Setup

- [ ] **Update .env file:**
  ```bash
  # Open .env and fill in:
  TOAST_CLIENT_ID=<new_id_from_support>
  TOAST_CLIENT_SECRET=<new_secret_from_support>
  TOAST_RESTAURANT_ID=<your_restaurant_id>
  TOAST_ENVIRONMENT=sandbox  # Start with sandbox
  
  # Generate new SECRET_KEY
  python -c "import secrets; print(secrets.token_hex(32))"
  # Copy output to SECRET_KEY in .env
  ```

- [ ] **Verify .env is in .gitignore:**
  ```bash
  cat .gitignore | grep "^.env"
  # Should output: .env
  ```

- [ ] **Verify .env was never committed:**
  ```bash
  git log --full-history -- .env
  # If no output, you're safe
  # If it shows .env commits, see "Git History Cleanup" section
  ```

### Step 3: Install New Dependencies

- [ ] **Install Flask-Talisman (for HTTPS enforcement):**
  ```bash
  pip install flask-talisman
  pip freeze > requirements.txt
  ```

### Step 4: Database Models

- [ ] **Run migrations to create Toast tables:**
  ```bash
  flask db upgrade
  # Or if using SQLAlchemy directly:
  python -c "from app import db, app; app.app_context().push(); db.create_all()"
  ```

- [ ] **Verify tables created:**
  ```bash
  sqlite3 room120.db ".tables"
  # Should see: toast_transactions, toast_transaction_items, toast_member_spending, etc.
  ```

---

## Testing in Sandbox

### Test 1: Environment Variables Load Correctly
```bash
python -c "
from config import TOAST_CLIENT_ID, TOAST_ENVIRONMENT, TOAST_API_BASE_URL
print(f'Client ID: {TOAST_CLIENT_ID[:10]}...')
print(f'Environment: {TOAST_ENVIRONMENT}')
print(f'API URL: {TOAST_API_BASE_URL}')
"

# Expected output:
# Client ID: your_new_id...
# Environment: sandbox
# API URL: https://sandbox.toasttab.com
```

### Test 2: Toast Authentication Works
```bash
python -c "
from toast_auth import get_toast_access_token
try:
    token = get_toast_access_token()
    if token:
        print(f'✓ Token obtained: {token[:20]}...')
    else:
        print('✗ Failed to get token')
except Exception as e:
    print(f'✗ Error: {e}')
"

# Expected: ✓ Token obtained: ...
# If error: Check credentials and Toast support response
```

### Test 3: Flask App Starts
```bash
python -m flask run
# Should output:
# * Running on http://127.0.0.1:5000
# * Press CTRL+C to quit
```

### Test 4: Logging Works
- [ ] **Check logs directory created:**
  ```bash
  ls -la logs/
  # Should show: app.log, audit.log, security.log
  ```

- [ ] **Verify logs have content:**
  ```bash
  tail logs/app.log
  tail logs/audit.log
  tail logs/security.log
  ```

### Test 5: API Endpoints Exist
```bash
# While Flask is running, test endpoints
curl http://localhost:5000/api/toast/member/1/spending
# Should return 401 (not logged in) or 404 (not found)
# NOT 404 for the route itself

curl http://localhost:5000/api/toast/admin/revenue-report
# Should return 401 (not logged in)
# NOT 404 for the route itself
```

---

## Security Validation

### Session Security
- [ ] **Session timeout is 30 minutes:**
  ```bash
  grep "PERMANENT_SESSION_LIFETIME" app.py
  # Should show: timedelta(minutes=30)
  ```

- [ ] **Session cookies are secure:**
  ```bash
  grep -E "(SESSION_COOKIE|secure|httponly)" app.py
  # Should show all three flags set to True
  ```

### RBAC Enforcement
- [ ] **Member endpoints require login:**
  ```bash
  # Try without login
  curl -i http://localhost:5000/api/toast/member/1/spending
  # Should return 302 (redirect to login) or 401
  ```

- [ ] **Admin endpoints require admin role:**
  ```bash
  # As regular member, try to access admin endpoint
  curl -b "session=member_session" \
    http://localhost:5000/api/toast/admin/revenue-report
  # Should return 403
  ```

### Rate Limiting
- [ ] **Rate limiter initializes:**
  ```bash
  python -c "
  from security import rate_limiter
  print(f'Rate limiter: {rate_limiter}')
  print(f'Requests dict: {rate_limiter.requests}')
  "
  ```

### Error Handling
- [ ] **Safe error messages:**
  ```bash
  # Check that error messages don't leak details
  grep -r "Toast API token" app.py toast_*.py security.py
  # Should NOT appear in any responses
  
  # Check for safe error responses
  grep "SafeError" toast_routes.py
  # Should have many references
  ```

### HTTPS Enforcement (Production Only)
- [ ] **Talisman is configured:**
  ```bash
  grep -A 10 "flask_talisman import Talisman" app.py
  # Should show Talisman configuration
  ```

---

## Code Quality Checks

### No Hardcoded Credentials
```bash
# Search for any exposed credentials
grep -r "Jd4jZk55DCFsZsUACvQyR7x72EjynLsI" .
grep -r "gAdNjaQghgCd_5cv1-mwcpjr9qmMDGk5zNoYUpYHnD73Ewd" .
# Should return NO results (if found, delete them!)

# Search for other credential patterns
grep -r "TOAST_CLIENT_ID.*=" app.py config.py toast_*.py
# Should show only .getenv() calls, never plain strings
```

### No Hardcoded Secrets
```bash
# Check for generic "supersecretkey"
grep -r "supersecretkey" .
# Should return NO results
```

### GET-Only to Toast
```bash
# Check for any POST/PUT/PATCH/DELETE to Toast
grep -r "requests\.post\|requests\.put\|requests\.patch\|requests\.delete" toast_api.py
# Should return NO results in toast_api.py

# Verify only GET is used
grep "requests\.get" toast_api.py
# Should have many results
```

---

## Production Deployment

### Pre-Launch Checklist

#### Credentials & Config
- [ ] New Toast credentials installed (old ones rotated)
- [ ] `SECRET_KEY` is long random string (not default)
- [ ] `FLASK_ENV=production`
- [ ] `TOAST_ENVIRONMENT=production`
- [ ] `DATABASE_URL` points to production database
- [ ] All sensitive values in `.env`, not in code

#### HTTPS & Security
- [ ] SSL/TLS certificate installed
- [ ] HTTPS is enforced (redirect HTTP → HTTPS)
- [ ] Secure cookies enabled (already in code)
- [ ] CORS headers configured if needed

#### Database
- [ ] Production database created and migrated
- [ ] Backups automated (daily, encrypted, off-site)
- [ ] Database connection pooling configured
- [ ] Read-only replica set up for analytics

#### Logging & Monitoring
- [ ] Logs directory writable and on fast storage
- [ ] Audit logs sent to secure location
- [ ] Log rotation configured (max 10MB per file)
- [ ] Monitoring alerts set up for:
  - High error rate
  - Rate limit breaches
  - Authentication failures
  - Toast API errors

#### Performance
- [ ] Rate limiting tuned for expected traffic
- [ ] Caching configured (Redis/Memcached optional)
- [ ] Database indexes optimized
- [ ] Gunicorn/uWSGI configured with workers

#### Compliance
- [ ] GDPR data retention policies documented
- [ ] Data backup strategy documented
- [ ] Incident response plan in place
- [ ] Regular security audits scheduled

### Launch Commands

```bash
# Set environment variables
export FLASK_ENV=production
export TOAST_ENVIRONMENT=production

# Run migrations
python -m flask db upgrade

# Start application with production server
gunicorn -w 4 \
  -b 0.0.0.0:5000 \
  --timeout 30 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log \
  app:app

# Or with uWSGI
uwsgi --http :5000 --wsgi-file app.py --callable app --processes 4 --threads 2
```

### Post-Launch Verification (First 24 Hours)

- [ ] **Health Check:**
  ```bash
  curl https://yourdomain.com/health
  # Should return 200 OK
  ```

- [ ] **Member Can Access Spending:**
  - Log in as test member
  - Navigate to spending dashboard
  - Verify data displays correctly

- [ ] **Admin Can Access Reports:**
  - Log in as admin
  - Access revenue report
  - Verify data is correct

- [ ] **Audit Logs Working:**
  ```bash
  tail logs/audit.log
  # Should see recent API access entries
  ```

- [ ] **Rate Limiting Works:**
  - Make 101 rapid requests
  - Verify request #101 returns 429

- [ ] **Error Handling Safe:**
  - Trigger an error intentionally
  - Verify error message is generic
  - Check detailed error is in logs, not response

- [ ] **Toast Token Refresh:**
  ```bash
  tail logs/app.log | grep "Toast API token"
  # Should see successful token refresh
  ```

---

## Git History Cleanup (If Credentials Were Committed)

⚠️ **CRITICAL IF YOUR .env WAS COMMITTED**

If `.env` with credentials was accidentally committed to Git:

```bash
# 1. Remove from all history (DESTRUCTIVE)
git filter-branch --tree-filter 'rm -f .env' HEAD

# 2. Force push (will rewrite history)
git push origin main --force-with-lease

# 3. Notify team to re-clone repository
# This removes the credentials from Git history permanently
```

**Alternative: Using BFG Repo-Cleaner (safer)**
```bash
# 1. Install BFG
brew install bfg  # macOS
# or download from https://rtyley.github.io/bfg-repo-cleaner/

# 2. Remove .env from history
bfg --delete-files .env

# 3. Reflog expire and gc
git reflog expire --expire=now --all && git gc --aggressive --prune=now

# 4. Force push
git push origin main --force-with-lease
```

---

## Monitoring Dashboard (Optional)

Set up dashboard to monitor:

```python
# dashboard.py - Admin dashboard data
@app.route('/admin/health')
def health_check():
    return {
        "status": "healthy",
        "database": check_db_connection(),
        "toast_api": check_toast_connection(),
        "logs": {
            "app_log_size": os.path.getsize("logs/app.log"),
            "audit_log_size": os.path.getsize("logs/audit.log"),
            "security_events": count_recent_security_events()
        },
        "rate_limiter": rate_limiter.requests
    }
```

---

## Support & Troubleshooting

### Toast Support
- **Email:** support@toasttab.com
- **Phone:** +1-877-TOAST-11
- **Hours:** 24/7 for emergencies

### Check Toast System Status
```bash
curl https://api.toasttab.com/health
# Should return 200 if API is healthy
```

### Common Issues

**Q: "Unable to load data" error**  
A: Check:
1. Toast API status (https://status.toast.com)
2. Credentials in .env are correct
3. Toast connection logs: `grep "Toast" logs/app.log`

**Q: "You do not have permission" when accessing admin endpoint**  
A: Check:
1. You're logged in as admin (not member)
2. Admin role is set in database: `SELECT role FROM user WHERE id=1`
3. Session has role: `grep "role" session data`

**Q: Rate limit is too strict/loose**  
A: Adjust in `security.py`:
```python
@rate_limit(max_requests=200, time_window=60)  # 200 per minute
```

---

## Success Criteria

✅ **All of the following must be true before launch:**

1. [ ] New Toast credentials obtained and old ones rotated
2. [ ] `.env` has all values filled in and is never committed
3. [ ] Flask app starts without errors
4. [ ] All three log files created and have content
5. [ ] Member endpoints return 401 (not logged in) not 404
6. [ ] Admin endpoints return 401 (not logged in) not 404
7. [ ] Rate limiting works (429 on 101st request)
8. [ ] Safe error messages (no technical details)
9. [ ] HTTPS enforced in production
10. [ ] Audit logs record all API access
11. [ ] Toast token refresh working
12. [ ] Member can access own data only
13. [ ] Admin can access reports
14. [ ] Database has Toast models
15. [ ] Monitoring/alerting configured

---

**Last Updated:** May 19, 2026  
**Status:** Ready for Deployment  
**Next Step:** Complete credential rotation and .env setup
