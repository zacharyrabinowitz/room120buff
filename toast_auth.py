"""
Toast API Authentication Module - SAFE OAuth Token Management

This module handles OAuth token acquisition and refresh for Toast API.
All credentials come from environment variables, NEVER hardcoded.
Tokens are cached to avoid unnecessary API calls.
"""

import requests
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import os
from config import (
    TOAST_CLIENT_ID,
    TOAST_CLIENT_SECRET,
    TOAST_OAUTH_TOKEN_URL,
    TOAST_API_SCOPE,
    TOAST_API_TIMEOUT,
)

logger = logging.getLogger(__name__)

# In-memory token cache (in production, use Redis or database)
_token_cache: Dict[str, Any] = {
    "access_token": None,
    "token_type": "Bearer",
    "expires_at": None,
}


def _validate_credentials() -> bool:
    """
    Validate that Toast credentials are properly configured.
    
    Returns:
        bool: True if credentials are present, False otherwise
    """
    if not TOAST_CLIENT_ID or not TOAST_CLIENT_SECRET:
        logger.error(
            "Toast API credentials not configured. "
            "Please set TOAST_CLIENT_ID and TOAST_CLIENT_SECRET in .env"
        )
        return False
    return True


def _is_token_expired() -> bool:
    """
    Check if cached token is expired.
    
    Returns:
        bool: True if token is expired or not set
    """
    if not _token_cache["access_token"]:
        return True
    
    expires_at = _token_cache.get("expires_at")
    if not expires_at:
        return True
    
    # Refresh if expiring within 5 minutes
    buffer = datetime.utcnow() + timedelta(minutes=5)
    return expires_at < buffer


def get_toast_access_token() -> Optional[str]:
    """
    Get a valid Toast API access token.
    
    Attempts to:
    1. Use cached token if still valid
    2. Request new token from Toast OAuth endpoint
    3. Cache token for reuse
    
    Returns:
        str: Valid access token, or None if request fails
        
    Raises:
        ValueError: If credentials are not configured
    """
    # Check if cached token is still valid
    if _token_cache["access_token"] and not _is_token_expired():
        logger.debug("Using cached Toast API token")
        return _token_cache["access_token"]
    
    # Validate credentials before attempting request
    if not _validate_credentials():
        raise ValueError("Toast API credentials not configured")
    
    logger.info("Requesting new Toast API token...")
    
    try:
        # Prepare token request
        url = TOAST_OAUTH_TOKEN_URL
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "client_credentials",
            "client_id": TOAST_CLIENT_ID,
            "client_secret": TOAST_CLIENT_SECRET,
            "scope": TOAST_API_SCOPE
        }
        
        # Request token
        response = requests.post(
            url,
            headers=headers,
            data=data,
            timeout=TOAST_API_TIMEOUT
        )
        
        # Check for errors
        if response.status_code != 200:
            logger.error(
                f"Failed to get Toast API token. "
                f"Status: {response.status_code}, Response: {response.text}"
            )
            return None
        
        # Parse token response
        token_data = response.json()
        access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 3600)  # Default 1 hour
        
        if not access_token:
            logger.error("No access token in Toast API response")
            return None
        
        # Cache token with expiration time
        _token_cache["access_token"] = access_token
        _token_cache["token_type"] = token_data.get("token_type", "Bearer")
        _token_cache["expires_at"] = datetime.utcnow() + timedelta(seconds=expires_in - 60)
        
        logger.info(f"Successfully obtained Toast API token (expires in {expires_in}s)")
        return access_token
        
    except requests.exceptions.Timeout:
        logger.error("Timeout requesting Toast API token")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("Connection error requesting Toast API token")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error requesting Toast API token: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting Toast API token: {str(e)}")
        return None


def get_auth_headers() -> Dict[str, str]:
    """
    Get authorization headers for Toast API requests.
    
    Returns:
        dict: Headers with Authorization Bearer token
        
    Raises:
        ValueError: If unable to obtain valid token
    """
    token = get_toast_access_token()
    if not token:
        raise ValueError("Unable to obtain Toast API access token")
    
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def clear_token_cache():
    """Clear cached token (useful for testing or forcing refresh)."""
    _token_cache["access_token"] = None
    _token_cache["expires_at"] = None
    logger.info("Toast API token cache cleared")
