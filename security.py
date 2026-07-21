"""
Security Module for Room 120 Portal

Implements Tier 1 & 2 security measures:
- Session management and RBAC
- Input validation
- Rate limiting
- Audit logging
- Error handling with safe messages
"""

import logging
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Dict, Any
from flask import session, request, jsonify, redirect
from collections import defaultdict
import time

logger = logging.getLogger(__name__)

# =====================================================
# TIER 1: SESSION VALIDATION & RBAC
# =====================================================

def login_required(f):
    """
    TIER 1: Decorator to require user login.
    Validates session before allowing access.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "member_id" not in session or "user_id" not in session:
            logger.warning(f"Unauthorized access attempt to {request.path}")
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


def member_only(f):
    """
    TIER 1: Decorator to restrict access to members only.
    Checks role in session.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "role" not in session or session["role"] != "member":
            logger.warning(f"Non-member access attempt to {request.path} by user {session.get('user_id')}")
            return jsonify({"error": "Access denied"}), 403
        return f(*args, **kwargs)
    return decorated_function


def admin_only(f):
    """
    TIER 1: Decorator to restrict access to admins only.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "role" not in session or session["role"] != "admin":
            logger.warning(f"Unauthorized admin access by user {session.get('user_id')}")
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function


def require_member_self_data(f):
    """
    TIER 1: Backend validation - member can only see their OWN data.
    Validates that requested member_id matches logged-in user.
    
    Usage:
        @require_member_self_data
        def get_member_spending(member_id):
            ...
    """
    @wraps(f)
    def decorated_function(member_id, *args, **kwargs):
        # Backend check: logged-in member must match requested member
        if str(session.get("member_id")) != str(member_id):
            logger.warning(
                f"Member {session.get('member_id')} attempted to access "
                f"data for member {member_id}"
            )
            return jsonify({"error": "Unauthorized"}), 403
        return f(member_id, *args, **kwargs)
    return decorated_function


# =====================================================
# TIER 2: RATE LIMITING
# =====================================================

class RateLimiter:
    """
    TIER 2: Simple rate limiter to prevent API abuse.
    Tracks requests per user within time window.
    
    For production, use Redis instead of in-memory.
    """
    
    def __init__(self):
        self.requests = defaultdict(list)
    
    def is_allowed(
        self,
        identifier: str,
        max_requests: int = 100,
        time_window: int = 60
    ) -> bool:
        """
        Check if request is allowed for identifier.
        
        Args:
            identifier: User ID or IP to track
            max_requests: Max requests allowed
            time_window: Time window in seconds
        
        Returns:
            bool: True if allowed, False if rate limited
        """
        now = time.time()
        cutoff = now - time_window
        
        # Remove old requests outside time window
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if req_time > cutoff
        ]
        
        # Check if under limit
        if len(self.requests[identifier]) < max_requests:
            self.requests[identifier].append(now)
            return True
        
        logger.warning(f"Rate limit exceeded for {identifier}")
        return False


# Global rate limiter instance
rate_limiter = RateLimiter()


def rate_limit(max_requests: int = 100, time_window: int = 60):
    """
    TIER 2: Decorator for rate limiting.
    
    Usage:
        @rate_limit(max_requests=100, time_window=60)
        def api_endpoint():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Use member ID if available, otherwise use IP
            identifier = session.get("member_id") or request.remote_addr
            
            if not rate_limiter.is_allowed(identifier, max_requests, time_window):
                logger.warning(f"Rate limit exceeded for {identifier}")
                return jsonify({"error": "Too many requests"}), 429
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# =====================================================
# TIER 2: INPUT VALIDATION
# =====================================================

def validate_member_id(member_id: Any) -> bool:
    """
    TIER 2: Validate member ID format.
    Prevents injection attacks and invalid data.
    """
    if not isinstance(member_id, (str, int)):
        return False
    
    if isinstance(member_id, str):
        # Allow alphanumeric and hyphens, max 50 chars
        if not member_id.replace("-", "").replace("_", "").isalnum():
            return False
        if len(member_id) > 50:
            return False
    
    return True


def validate_date_format(date_str: str) -> bool:
    """
    TIER 2: Validate ISO format date.
    """
    try:
        datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return True
    except (ValueError, AttributeError):
        return False


def validate_query_params(params: Dict[str, Any], allowed_keys: Dict[str, type]) -> Dict[str, Any]:
    """
    TIER 2: Whitelist-based query parameter validation.
    Only allows specified parameters of correct types.
    
    Args:
        params: Query parameters to validate
        allowed_keys: Dict of {key: expected_type}
    
    Returns:
        dict: Validated parameters, or empty dict if invalid
    """
    validated = {}
    
    for key, expected_type in allowed_keys.items():
        if key in params:
            value = params[key]
            
            # Type check
            if not isinstance(value, expected_type):
                logger.warning(f"Invalid type for parameter {key}: {type(value)}")
                return {}
            
            # Length check for strings
            if isinstance(value, str) and len(value) > 255:
                logger.warning(f"Parameter {key} exceeds max length")
                return {}
            
            validated[key] = value
    
    return validated


# =====================================================
# TIER 2: AUDIT LOGGING
# =====================================================

def log_api_access(action: str, resource: str, details: Optional[Dict] = None):
    """
    TIER 2: Log API access for audit trail.
    
    Args:
        action: What was done (e.g., "view_spending")
        resource: What was accessed (e.g., "member_123")
        details: Additional context
    """
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": session.get("member_id"),
        "role": session.get("role"),
        "ip_address": request.remote_addr,
        "action": action,
        "resource": resource,
        "endpoint": request.path,
        "method": request.method,
        "details": details or {}
    }
    
    logger.info(f"API_ACCESS: {log_entry}")


def log_failed_access(reason: str, resource: str):
    """
    TIER 2: Log failed access attempts for security analysis.
    """
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": session.get("member_id"),
        "ip_address": request.remote_addr,
        "reason": reason,
        "resource": resource,
        "endpoint": request.path,
        "user_agent": request.headers.get("User-Agent")
    }
    
    logger.warning(f"FAILED_ACCESS: {log_entry}")


# =====================================================
# TIER 2: SAFE ERROR MESSAGES
# =====================================================

class SafeError:
    """
    TIER 2: Return safe error messages that don't leak technical details.
    """
    
    GENERIC = "An error occurred. Please try again later."
    DATA_NOT_FOUND = "The requested data could not be found."
    UNAUTHORIZED = "You do not have permission to access this resource."
    INVALID_INPUT = "Invalid input provided. Please check your request."
    SERVICE_UNAVAILABLE = "The service is temporarily unavailable. Please try again later."
    RATE_LIMITED = "Too many requests. Please slow down."


def safe_error_response(error_type: str, status_code: int = 500):
    """
    Return safe error response without exposing sensitive details.
    """
    message = getattr(SafeError, error_type, SafeError.GENERIC)
    return jsonify({"error": message}), status_code


# =====================================================
# TIER 1 & 2: SESSION SECURITY
# =====================================================

def create_secure_session(user_id: int, member_id: Optional[str] = None, role: str = "member"):
    """
    TIER 1: Create secure session with required fields.
    """
    session["user_id"] = user_id
    session["member_id"] = member_id or user_id
    session["role"] = role
    session["created_at"] = datetime.utcnow().isoformat()
    session["csrf_token"] = secrets.token_hex(32)
    session.permanent = True  # Enable session timeout
    
    logger.info(f"Secure session created for user {user_id}, role {role}")


def validate_session_age(max_age_minutes: int = 30):
    """
    TIER 1: Validate session hasn't been open too long.
    Session timeout for inactivity.
    """
    created_at = session.get("created_at")
    if not created_at:
        return False
    
    try:
        created = datetime.fromisoformat(created_at)
        age = datetime.utcnow() - created
        
        if age > timedelta(minutes=max_age_minutes):
            logger.warning(f"Session expired for user {session.get('user_id')}")
            return False
    except (ValueError, TypeError):
        return False
    
    return True


def verify_csrf_token(token: Optional[str]) -> bool:
    """
    TIER 1: Verify CSRF token for state-changing requests.
    """
    if not token:
        return False
    
    session_token = session.get("csrf_token")
    if not session_token:
        return False
    
    # Use constant-time comparison to prevent timing attacks
    return secrets.compare_digest(token, session_token)
