import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# =====================================================
# TOAST API CONFIGURATION (READ-ONLY ACCESS)
# =====================================================

# OAuth credentials for Toast API (from Toast support)
TOAST_CLIENT_ID = os.getenv("TOAST_CLIENT_ID", "")
TOAST_CLIENT_SECRET = os.getenv("TOAST_CLIENT_SECRET", "")
TOAST_API_SCOPE = os.getenv("TOAST_API_SCOPE", "restaurants.read orders.read checks.read")

# API Endpoints
TOAST_ENVIRONMENT = os.getenv("TOAST_ENVIRONMENT", "sandbox")
TOAST_SANDBOX_URL = os.getenv("TOAST_SANDBOX_URL", "https://sandbox.toasttab.com")
TOAST_PRODUCTION_URL = os.getenv("TOAST_PRODUCTION_URL", "https://api.toasttab.com")
TOAST_OAUTH_TOKEN_URL = os.getenv(
    "TOAST_OAUTH_TOKEN_URL", 
    "https://partner.toasttab.com/api/v1/oauth/token"
)

# Select API URL based on environment
TOAST_API_BASE_URL = (
    TOAST_SANDBOX_URL if TOAST_ENVIRONMENT == "sandbox" 
    else TOAST_PRODUCTION_URL
)

# Restaurant ID
TOAST_RESTAURANT_ID = os.getenv("TOAST_RESTAURANT_ID", "")

# =====================================================
# LOGGING
# =====================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# =====================================================
# FLASK CONFIGURATION
# =====================================================
FLASK_ENV = os.getenv("FLASK_ENV", "development")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-change-in-production")

# =====================================================
# DATABASE
# =====================================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///room120.db")

# =====================================================
# API RATE LIMITING (to prevent hammering Toast)
# =====================================================
TOAST_API_TIMEOUT = 10  # seconds
TOAST_API_RETRY_COUNT = 3
TOAST_API_RETRY_DELAY = 1  # seconds
