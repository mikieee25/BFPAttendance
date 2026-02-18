"""
Utility functions for BFP Sorsogon Attendance System
Contains security helpers, validation functions, and common utilities
"""

import logging
import re
from typing import Tuple

# Configure logging
logger = logging.getLogger(__name__)


def validate_password(password: str) -> Tuple[bool, str]:
    """
    Validate password strength according to security requirements.

    Requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit

    Args:
        password: The password string to validate

    Returns:
        Tuple of (is_valid: bool, message: str)
    """
    if not password:
        return False, "Password is required"

    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r"\d", password):
        return False, "Password must contain at least one number"

    return True, "Password is valid"


def validate_email(email: str) -> Tuple[bool, str]:
    """
    Validate email format.

    Args:
        email: The email string to validate

    Returns:
        Tuple of (is_valid: bool, message: str)
    """
    if not email:
        return False, "Email is required"

    # Basic email regex pattern
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

    if not re.match(email_pattern, email):
        return False, "Invalid email format"

    return True, "Email is valid"


def validate_username(username: str) -> Tuple[bool, str]:
    """
    Validate username format.

    Requirements:
    - Minimum 3 characters
    - Maximum 100 characters
    - Only alphanumeric characters, underscores, and hyphens

    Args:
        username: The username string to validate

    Returns:
        Tuple of (is_valid: bool, message: str)
    """
    if not username:
        return False, "Username is required"

    if len(username) < 3:
        return False, "Username must be at least 3 characters long"

    if len(username) > 100:
        return False, "Username must not exceed 100 characters"

    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        return (
            False,
            "Username can only contain letters, numbers, underscores, and hyphens",
        )

    return True, "Username is valid"


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent directory traversal and other security issues.

    Args:
        filename: The filename to sanitize

    Returns:
        Sanitized filename string
    """
    if not filename:
        return ""

    # Remove any path separators
    filename = filename.replace("/", "_").replace("\\", "_")

    # Remove any leading dots to prevent hidden files
    filename = filename.lstrip(".")

    # Keep only safe characters
    filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)

    return filename


def log_activity(user_id: int, title: str, description: str = None):
    """
    Helper function to log user activities to the database.

    Args:
        user_id: ID of the user performing the action
        title: Short title of the activity
        description: Optional detailed description
    """
    try:
        from models import ActivityLog, db

        log = ActivityLog(user_id=user_id, title=title, description=description)
        db.session.add(log)
        db.session.commit()

    except Exception as e:
        logger.error(f"Failed to log activity: {e}")
        # Don't raise - logging failures shouldn't break main functionality


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in bytes to human-readable format.

    Args:
        size_bytes: File size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def get_client_ip(request) -> str:
    """
    Get the client's IP address from the request, considering proxies.

    Args:
        request: Flask request object

    Returns:
        IP address string
    """
    # Check for proxy headers first
    if request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()
    elif request.headers.get("X-Real-IP"):
        return request.headers.get("X-Real-IP")
    else:
        return request.remote_addr or "unknown"
