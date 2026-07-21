"""
Logging Configuration for Room 120 Portal

Sets up structured logging for:
- API access tracking (audit log)
- Error tracking
- Security events
- Toast API interactions
"""

import logging
import logging.handlers
import os
from datetime import datetime
from config import LOG_LEVEL

# Create logs directory if it doesn't exist
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)


def setup_logging():
    """
    Configure logging for the application.
    
    Creates three log files:
    1. app.log - General application logs
    2. audit.log - API access and user actions (TIER 2)
    3. security.log - Security events and warnings
    """
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL)
    
    # Log format with timestamp, level, logger name, and message
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # =====================================================
    # GENERAL APPLICATION LOG
    # =====================================================
    app_handler = logging.handlers.RotatingFileHandler(
        os.path.join(LOGS_DIR, "app.log"),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(formatter)
    root_logger.addHandler(app_handler)
    
    # =====================================================
    # AUDIT LOG (API Access - TIER 2)
    # =====================================================
    audit_handler = logging.handlers.RotatingFileHandler(
        os.path.join(LOGS_DIR, "audit.log"),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10  # Keep more audit logs
    )
    audit_handler.setLevel(logging.INFO)
    audit_formatter = logging.Formatter(
        '%(asctime)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    audit_handler.setFormatter(audit_formatter)
    
    # Only attach audit handler to specific loggers
    audit_logger = logging.getLogger("audit")
    audit_logger.addHandler(audit_handler)
    audit_logger.setLevel(logging.INFO)
    
    # =====================================================
    # SECURITY LOG
    # =====================================================
    security_handler = logging.handlers.RotatingFileHandler(
        os.path.join(LOGS_DIR, "security.log"),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10  # Keep more security logs
    )
    security_handler.setLevel(logging.WARNING)
    security_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    security_handler.setFormatter(security_formatter)
    
    security_logger = logging.getLogger("security")
    security_logger.addHandler(security_handler)
    security_logger.setLevel(logging.WARNING)
    
    # =====================================================
    # CONSOLE OUTPUT (for development)
    # =====================================================
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    logging.info("Logging configured successfully")
    logging.info(f"Log level: {LOG_LEVEL}")
    logging.info(f"Logs directory: {LOGS_DIR}")


def get_audit_logger():
    """Get the audit logger for recording API access."""
    return logging.getLogger("audit")


def get_security_logger():
    """Get the security logger for recording security events."""
    return logging.getLogger("security")
