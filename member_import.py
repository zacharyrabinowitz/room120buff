import os
import requests
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Cache for OAuth token
_oauth_token = None
_token_expires_at = None

def get_oauth_token():
    """
    Get OAuth access token from Toast.
    Tokens expire after 1 hour, we cache them.
    """
    global _oauth_token, _token_expires_at
    
    # Check if we have a valid cached token
    if _oauth_token and _token_expires_at and datetime.now() < _token_expires_at:
        return _oauth_token
    
    try:
        client_id = os.getenv('TOAST_CLIENT_ID')
        client_secret = os.getenv('TOAST_CLIENT_SECRET')
        token_url = os.getenv('TOAST_OAUTH_TOKEN_URL', 'https://partner.toasttab.com/oauth/token')
        
        if not client_id or not client_secret:
            logger.error("Toast credentials not configured")
            return None
        
        # Request access token - no specific scopes, use what's configured in Toast
        data = {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret,
        }
        
        logger.info(f"Requesting OAuth token from {token_url}")
        response = requests.post(token_url, data=data, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"Token request failed: {response.status_code} - {response.text}")
            return None
        
        token_data = response.json()
        _oauth_token = token_data.get('access_token')
        expires_in = token_data.get('expires_in', 3600)
        _token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)
        
        logger.info(f"✓ Got OAuth token from Toast (expires in {expires_in}s)")
        return _oauth_token
    
    except Exception as e:
        logger.error(f"Error getting OAuth token: {str(e)}")
        return None

def get_draft_room_orders():
    """
    GET ONLY - Fetch all orders from Draft Room restaurant in Toast.
    No data is written or modified. Read-only access only.
    
    Returns:
        list: Orders from Toast, or empty list if error
    """
    try:
        # Get OAuth token first
        token = get_oauth_token()
        if not token:
            logger.error("Could not obtain OAuth token from Toast")
            return []
        
        api_url = os.getenv('TOAST_API_URL')
        restaurant_id = os.getenv('TOAST_RESTAURANT_ID')
        
        if not all([token, restaurant_id, api_url]):
            logger.warning("Toast configuration incomplete")
            return []
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # GET request only - reading orders (NO WRITES)
        url = f"{api_url}/restaurants/{restaurant_id}/orders"
        
        logger.info(f"Fetching orders from: {url}")
        
        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 401:
            logger.error("401 Unauthorized - Check your Toast Client ID and Secret")
            return []
        
        if response.status_code == 403:
            logger.error("403 Forbidden - Your credentials don't have orders:read permission")
            return []
        
        if response.status_code == 404:
            logger.error("404 Not Found - Restaurant ID is incorrect")
            return []
        
        response.raise_for_status()
        
        data = response.json()
        orders = data.get('orders', [])
        
        logger.info(f"✓ Fetched {len(orders)} orders from Toast")
        return orders
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Toast API error fetching orders: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"Error processing Toast orders: {str(e)}")
        return []