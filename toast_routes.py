"""
Toast API Integration Endpoints for Room 120 Portal

Flask routes for:
- Member spending display (read-only from Toast)
- Transaction history (read-only from Toast)
- Admin analytics (aggregated data)

ALL endpoints implement TIER 1 & 2 security measures.
"""

from flask import Blueprint, request, jsonify, session
from datetime import datetime, timedelta
import logging
from functools import wraps

from toast_api import (
    get_member_spending,
    get_member_orders,
    get_customer_info,
    get_revenue_report
)
from security import (
    login_required,
    member_only,
    admin_only,
    require_member_self_data,
    rate_limit,
    validate_member_id,
    validate_date_format,
    validate_query_params,
    log_api_access,
    log_failed_access,
    safe_error_response,
    SafeError
)

# Import models from app (Flask-SQLAlchemy)
from app import db, User, ToastTransaction, ToastMemberSpending, ToastSyncLog

logger = logging.getLogger(__name__)

# Create Blueprint for Toast API routes
toast_bp = Blueprint('toast', __name__, url_prefix='/api/toast')


# =====================================================
# MEMBER ENDPOINTS (WITH TIER 1 & 2 SECURITY)
# =====================================================

@toast_bp.route('/member/<member_id>/spending', methods=['GET'])
@login_required
@member_only
@rate_limit(max_requests=100, time_window=60)
@require_member_self_data
def get_spending_summary(member_id):
    """
    TIER 1 & 2: Get member spending summary from Toast.
    
    Security measures:
    - Login required
    - Member role required
    - Rate limited
    - Member can only see own data
    - No sensitive details in errors
    
    Returns:
        dict: Spending summary (total, transaction count, etc.)
    """
    try:
        # TIER 2: Log API access
        log_api_access(
            action="view_spending_summary",
            resource=f"member_{member_id}"
        )
        
        # TIER 2: Validate input
        if not validate_member_id(member_id):
            log_failed_access("Invalid member ID format", f"member_{member_id}")
            return safe_error_response("INVALID_INPUT", 400)
        
        # Fetch from Toast (read-only GET)
        spending_data = get_member_spending(member_id)
        
        if not spending_data:
            # Toast API error or member not found
            logger.warning(f"No spending data found for member {member_id}")
            return safe_error_response("DATA_NOT_FOUND", 404)
        
        # Return data
        return jsonify(spending_data), 200
        
    except Exception as e:
        logger.error(f"Error fetching spending for member {member_id}: {str(e)}")
        return safe_error_response("GENERIC", 500)


@toast_bp.route('/member/<member_id>/transactions', methods=['GET'])
@login_required
@member_only
@rate_limit(max_requests=100, time_window=60)
@require_member_self_data
def get_transaction_history(member_id):
    """
    TIER 1 & 2: Get member transaction history from Toast.
    
    Query parameters:
    - start_date: ISO format (optional, YYYY-MM-DD)
    - end_date: ISO format (optional, YYYY-MM-DD)
    - limit: Max transactions to return (optional, default 50)
    
    Security measures:
    - Login required
    - Member role required
    - Rate limited
    - Member can only see own data
    - Input validation on query params
    
    Returns:
        dict: List of transactions with details
    """
    try:
        # TIER 2: Log API access
        log_api_access(
            action="view_transactions",
            resource=f"member_{member_id}",
            details={
                "params": dict(request.args)
            }
        )
        
        # TIER 2: Validate member ID
        if not validate_member_id(member_id):
            log_failed_access("Invalid member ID format", f"member_{member_id}")
            return safe_error_response("INVALID_INPUT", 400)
        
        # TIER 2: Validate query parameters
        allowed_params = {
            "start_date": str,
            "end_date": str,
            "limit": int
        }
        params = validate_query_params(dict(request.args), allowed_params)
        
        if request.args and not params:
            log_failed_access("Invalid query parameters", f"member_{member_id}")
            return safe_error_response("INVALID_INPUT", 400)
        
        # Validate date formats
        if "start_date" in params and not validate_date_format(params["start_date"]):
            return safe_error_response("INVALID_INPUT", 400)
        if "end_date" in params and not validate_date_format(params["end_date"]):
            return safe_error_response("INVALID_INPUT", 400)
        
        # Parse dates
        start_date = None
        end_date = None
        if "start_date" in params:
            start_date = datetime.fromisoformat(params["start_date"].replace("Z", "+00:00"))
        if "end_date" in params:
            end_date = datetime.fromisoformat(params["end_date"].replace("Z", "+00:00"))
        
        # Fetch from Toast (read-only GET)
        orders = get_member_orders(member_id, start_date, end_date)
        
        if not orders:
            logger.info(f"No transactions found for member {member_id}")
            return jsonify({
                "member_id": member_id,
                "transaction_count": 0,
                "transactions": []
            }), 200
        
        # Apply limit if specified
        limit = int(params.get("limit", 50))
        if limit > 500:
            limit = 500  # Max limit to prevent abuse
        
        transactions = orders[:limit]
        
        return jsonify({
            "member_id": member_id,
            "transaction_count": len(transactions),
            "transactions": transactions
        }), 200
        
    except ValueError as e:
        logger.error(f"Invalid parameter value: {str(e)}")
        return safe_error_response("INVALID_INPUT", 400)
    except Exception as e:
        logger.error(f"Error fetching transactions for member {member_id}: {str(e)}")
        return safe_error_response("GENERIC", 500)


@toast_bp.route('/member/<member_id>/info', methods=['GET'])
@login_required
@member_only
@rate_limit(max_requests=50, time_window=60)
@require_member_self_data
def get_member_info(member_id):
    """
    TIER 1 & 2: Get member information from Toast.
    
    Security measures:
    - Login required
    - Member role required
    - Lower rate limit (less frequent access)
    - Member can only see own data
    
    Returns:
        dict: Member info from Toast
    """
    try:
        # TIER 2: Log API access
        log_api_access(
            action="view_member_info",
            resource=f"member_{member_id}"
        )
        
        # TIER 2: Validate member ID
        if not validate_member_id(member_id):
            log_failed_access("Invalid member ID format", f"member_{member_id}")
            return safe_error_response("INVALID_INPUT", 400)
        
        # Fetch from Toast (read-only GET)
        customer_info = get_customer_info(member_id)
        
        if not customer_info:
            return safe_error_response("DATA_NOT_FOUND", 404)
        
        return jsonify(customer_info), 200
        
    except Exception as e:
        logger.error(f"Error fetching member info for {member_id}: {str(e)}")
        return safe_error_response("GENERIC", 500)


# =====================================================
# ADMIN ENDPOINTS (AGGREGATED DATA ONLY)
# =====================================================

@toast_bp.route('/admin/revenue-report', methods=['GET'])
@login_required
@admin_only
@rate_limit(max_requests=50, time_window=60)
def get_revenue_summary():
    """
    TIER 1 & 2: Get revenue report for admin.
    
    Query parameters:
    - start_date: ISO format (required)
    - end_date: ISO format (required)
    
    Security measures:
    - Login required
    - Admin role required
    - Lower rate limit
    - Input validation on dates
    
    Returns:
        dict: Revenue data aggregated across all members
    """
    try:
        # TIER 2: Log API access
        log_api_access(
            action="view_revenue_report",
            resource="all_members"
        )
        
        # TIER 2: Validate query parameters
        allowed_params = {
            "start_date": str,
            "end_date": str
        }
        params = validate_query_params(dict(request.args), allowed_params)
        
        if not params or "start_date" not in params or "end_date" not in params:
            log_failed_access("Missing required parameters", "revenue_report")
            return safe_error_response("INVALID_INPUT", 400)
        
        # Validate date formats
        if not validate_date_format(params["start_date"]):
            return safe_error_response("INVALID_INPUT", 400)
        if not validate_date_format(params["end_date"]):
            return safe_error_response("INVALID_INPUT", 400)
        
        # Parse dates
        try:
            start_date = datetime.fromisoformat(params["start_date"].replace("Z", "+00:00"))
            end_date = datetime.fromisoformat(params["end_date"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return safe_error_response("INVALID_INPUT", 400)
        
        # Validate date range (max 90 days)
        if (end_date - start_date).days > 90:
            return jsonify({"error": "Date range cannot exceed 90 days"}), 400
        
        # Fetch from Toast (read-only GET)
        revenue_data = get_revenue_report(start_date, end_date)
        
        if not revenue_data:
            logger.warning(f"No revenue data found for {start_date} to {end_date}")
            return jsonify({
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "total_revenue": 0.0,
                "transaction_count": 0
            }), 200
        
        return jsonify(revenue_data), 200
        
    except Exception as e:
        logger.error(f"Error fetching revenue report: {str(e)}")
        return safe_error_response("GENERIC", 500)


@toast_bp.route('/admin/members/spending-leaderboard', methods=['GET'])
@login_required
@admin_only
@rate_limit(max_requests=30, time_window=60)
def get_members_leaderboard():
    """
    TIER 1 & 2: Get member spending leaderboard for admin analytics.
    
    Query parameters:
    - limit: Number of top members (default 10, max 100)
    - order: "desc" (default) or "asc"
    
    Security measures:
    - Admin only
    - Input validation
    - Very low rate limit (expensive operation)
    
    Returns:
        list: Top spenders across all members
    """
    try:
        # TIER 2: Log API access
        log_api_access(
            action="view_spending_leaderboard",
            resource="all_members"
        )
        
        # TIER 2: Validate query parameters
        allowed_params = {
            "limit": int,
            "order": str
        }
        params = validate_query_params(dict(request.args), allowed_params)
        
        limit = int(params.get("limit", 10))
        order = params.get("order", "desc")
        
        # Validate inputs
        if limit < 1 or limit > 100:
            limit = 10
        if order not in ["asc", "desc"]:
            order = "desc"
        
        # Query local database (cached spending data)
        query = ToastMemberSpending.query.order_by(
            ToastMemberSpending.total_spent.desc()
            if order == "desc"
            else ToastMemberSpending.total_spent.asc()
        ).limit(limit).all()
        
        leaderboard = []
        for entry in query:
            member = User.query.get(entry.member_id)
            if member:
                leaderboard.append({
                    "member_id": entry.member_id,
                    "member_name": f"{member.first_name} {member.last_name}",
                    "total_spent": entry.total_spent,
                    "transaction_count": entry.transaction_count,
                    "last_transaction": entry.last_transaction_date.isoformat() if entry.last_transaction_date else None
                })
        
        return jsonify({
            "count": len(leaderboard),
            "leaderboard": leaderboard
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching leaderboard: {str(e)}")
        return safe_error_response("GENERIC", 500)


# =====================================================
# SYNC/MAINTENANCE ENDPOINTS
# =====================================================

@toast_bp.route('/admin/sync-member-data', methods=['POST'])
@login_required
@admin_only
@rate_limit(max_requests=5, time_window=3600)  # Max 5 per hour
def manual_sync_member_data():
    """
    TIER 1 & 2: Manually trigger sync of Toast data to local database.
    
    Request body:
    {
        "member_id": "optional_member_id",
        "force": false
    }
    
    Security measures:
    - Admin only
    - Very strict rate limit (prevent abuse)
    - Audit logged
    
    Returns:
        dict: Sync status
    """
    try:
        # TIER 2: Log API access
        log_api_access(
            action="trigger_manual_sync",
            resource="toast_data"
        )
        
        data = request.get_json() or {}
        member_id = data.get("member_id")
        force = data.get("force", False)
        
        # TIER 2: Validate input
        if member_id and not validate_member_id(member_id):
            return safe_error_response("INVALID_INPUT", 400)
        
        # For now, return placeholder (actual sync logic in separate module)
        sync_log = ToastSyncLog(
            sync_type="manual",
            status="pending",
            records_synced=0,
            started_at=datetime.utcnow()
        )
        db.session.add(sync_log)
        db.session.commit()
        
        logger.info(f"Manual sync triggered by admin {session.get('user_id')}")
        
        return jsonify({
            "status": "sync_queued",
            "sync_id": sync_log.id,
            "message": "Sync will complete in background"
        }), 202
        
    except Exception as e:
        logger.error(f"Error triggering sync: {str(e)}")
        return safe_error_response("GENERIC", 500)


def register_toast_routes(app):
    """Register Toast API blueprint with Flask app."""
    app.register_blueprint(toast_bp)
    logger.info("Toast API routes registered")
