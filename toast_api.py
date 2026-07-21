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
        logger.debug("Using cached OAuth token")
        return _oauth_token
    
    try:
        client_id = os.getenv('TOAST_CLIENT_ID', '').strip()
        client_secret = os.getenv('TOAST_CLIENT_SECRET', '').strip()
        token_url = os.getenv('TOAST_OAUTH_TOKEN_URL', 'https://ws-api.toasttab.com/oauth/token').strip()
        
        if not client_id or not client_secret:
            logger.error("Toast credentials not configured in .env")
            return None
        
        data = {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret,
        }
        
        logger.info(f"Requesting OAuth token from {token_url}")
        response = requests.post(token_url, data=data, timeout=15, verify=True)
        
        logger.info(f"Token response status: {response.status_code}")
        logger.debug(f"Token response: {response.text[:200]}")
        
        if response.status_code != 200:
            logger.error(f"Token request failed: {response.status_code} - {response.text}")
            return None
        
        token_data = response.json()
        _oauth_token = token_data.get('access_token')
        expires_in = token_data.get('expires_in', 3600)
        _token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)
        
        logger.info(f"✓ Got OAuth token (expires in {expires_in}s)")
        return _oauth_token
    
    except Exception as e:
        logger.error(f"Error getting OAuth token: {type(e).__name__}: {str(e)}")
        return None


def get_draft_room_orders():
    """
    GET ONLY - Fetch all orders from Draft Room restaurant in Toast.
    """
    try:
        token = get_oauth_token()
        if not token:
            logger.error("Could not obtain OAuth token")
            return []
        
        api_url = os.getenv('TOAST_API_URL', 'https://ws-api.toasttab.com').strip()
        restaurant_id = os.getenv('TOAST_RESTAURANT_ID', '').strip()
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        url = f"{api_url}/restaurants/{restaurant_id}/orders"
        logger.info(f"Fetching orders from: {url}")
        
        response = requests.get(url, headers=headers, timeout=15, verify=True)
        
        logger.info(f"Orders response status: {response.status_code}")
        logger.info(f"Orders response body: {response.text[:500]}")
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch orders: {response.status_code} - {response.text}")
            return []
        
        data = response.json()
        logger.info(f"Full response JSON: {data}")
        
        # Try different response formats
        orders = data.get('orders', [])
        if not orders:
            orders = data.get('data', [])
        if not orders and isinstance(data, list):
            orders = data
        
        logger.info(f"✓ Fetched {len(orders)} orders from Toast")
        return orders
    
    except Exception as e:
        logger.error(f"Error fetching orders: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []