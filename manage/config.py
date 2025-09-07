"""
Base configuration for management scripts
"""

import os
import sys
from pathlib import Path

# Add parent directory to path to import models
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from models import (
    db,
    User,
    Personnel,
    Attendance,
    FaceData,
    ActivityLog,
    PendingAttendance,
    StationType,
)
from flask import Flask


def create_app():
    """Create Flask app for management scripts"""
    app = Flask(__name__)

    # Configuration
    app.config["SECRET_KEY"] = "management-key"
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "mysql+pymysql://root:@localhost/bfp_sorsogon_attendance"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Initialize database
    db.init_app(app)

    return app


def get_app_context():
    """Get app context for database operations"""
    app = create_app()
    return app.app_context()


# Color codes for terminal output
class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def print_success(message):
    """Print success message in green"""
    print(f"{Colors.OKGREEN}✓ {message}{Colors.ENDC}")


def print_error(message):
    """Print error message in red"""
    print(f"{Colors.FAIL}✗ {message}{Colors.ENDC}")


def print_warning(message):
    """Print warning message in yellow"""
    print(f"{Colors.WARNING}⚠ {message}{Colors.ENDC}")


def print_info(message):
    """Print info message in blue"""
    print(f"{Colors.OKBLUE}ℹ {message}{Colors.ENDC}")


def print_header(message):
    """Print header message"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{message.center(60)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def confirm_action(message):
    """Ask for user confirmation"""
    response = input(f"{Colors.WARNING}{message} (y/N): {Colors.ENDC}")
    return response.lower() in ["y", "yes"]
