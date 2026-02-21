# Core Python libraries
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

# Flask core framework and utilities
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, current_user, logout_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash

# Face recognition service (imported but not used in app.py - available for blueprints)
from face_rec_module.face_service import cleanup_old_attendance_images  # noqa: F401

# Database models and enums
from models import AttendanceStatus, StationType, User, db

load_dotenv()

logger = logging.getLogger(__name__)

# Warn if interpreter differs from the project's .python-version (3.11.14)
if (sys.version_info.major, sys.version_info.minor) != (3, 11):
    logger.warning(
        "Project '.python-version' = 3.11.14 — current interpreter is %d.%d.%d. "
        "Some dependencies are tested on Python 3.11; consider using 3.11 if you encounter issues.",
        sys.version_info.major,
        sys.version_info.minor,
        sys.version_info.micro,
    )


def create_app():
    """Create and configure the Flask application instance"""
    app = Flask(__name__)

    _configure_logging()

    # Application configuration settings
    # Security: Require SECRET_KEY in production
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        if app.debug:
            logger.warning(
                "SECRET_KEY not set! Using default for development. "
                "Set SECRET_KEY environment variable for production!"
            )
            secret_key = "dev-secret-key-change-in-production"
        else:
            raise RuntimeError(
                "SECRET_KEY environment variable must be set in production. "
                "Generate a secure key with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
    app.config["SECRET_KEY"] = secret_key
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "mysql+pymysql://root:@localhost/bfp_sorsogon_attendance"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.path.join(
        app.root_path, "static", "images", "face_data"
    )
    app.config["TEMP_ATTENDANCE_FOLDER"] = os.path.join(
        app.root_path, "static", "images", "attendance_temp"
    )
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size
    app.config["WTF_CSRF_TIME_LIMIT"] = 3600

    # Face recognition settings
    app.config["YOLO_MODEL_PATH"] = os.path.join(
        app.root_path, "face_rec_module", "yolov11n-face.pt"
    )
    app.config["FACE_DETECTION_CONFIDENCE"] = 0.3  # Lowered for better detection
    app.config["FACE_RECOGNITION_THRESHOLD"] = (
        0.35  # Balanced strict security - allows legitimate users while blocking others
    )
    app.config["TORCH_DEVICE"] = "cpu"
    app.config["WORK_START_TIME"] = "08:00"
    app.config["ATTENDANCE_COOLDOWN"] = 5  # seconds
    app.config["ATTENDANCE_IMAGE_RETENTION_DAYS"] = 7
    app.config["PRELOAD_FACE_MODELS"] = (
        os.environ.get("PRELOAD_FACE_MODELS", "true").lower() == "true"
    )

    # Enhanced face detection settings (InsightFace)
    # Set to True to use InsightFace (requires: pip install insightface onnxruntime)
    # InsightFace provides better accuracy with RetinaFace detection and ArcFace embeddings
    app.config["USE_INSIGHTFACE"] = (
        os.environ.get("USE_INSIGHTFACE", "false").lower() == "true"
    )

    _validate_runtime_requirements(app)

    # Preload face recognition models to reduce first-capture delay.
    if app.config.get("PRELOAD_FACE_MODELS", True):
        try:
            with app.app_context():
                from face_rec_module.face_service import (
                    get_insightface_app,
                    get_yolo_model,
                )

                get_yolo_model()
                if app.config.get("USE_INSIGHTFACE", False):
                    get_insightface_app()
            logger.info("Face recognition models preloaded successfully.")
        except Exception as exc:
            logger.warning("Model preload failed: %s", exc)



    # Create required directories for file uploads and temporary storage
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["TEMP_ATTENDANCE_FOLDER"], exist_ok=True)

    # Initialize database extension with app context
    db.init_app(app)
    CSRFProtect(app)

    # Configure Flask-Login for user session management
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"  # Redirect unauthorized users to login page
    login_manager.login_message = "Please log in to access this page."

    @login_manager.user_loader
    def load_user(user_id):
        """Load user object from user ID stored in session"""
        return db.session.get(User, int(user_id))

    # Configure rate limiting to prevent abuse (generous limits for internal use)
    limiter = Limiter(
        key_func=get_remote_address,  # Use client IP for rate limiting
        app=app,
        default_limits=[
            "1000 per day",
            "200 per hour",
        ],  # Reasonable limits for BFP usage
        storage_uri="memory://",  # Store rate limit data in memory
    )

    # Make limiter available to all blueprints
    app.limiter = limiter

    # Register blueprints
    from routes.api import api_bp
    from routes.attendance import attendance_bp
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.kiosk import kiosk_bp
    from routes.pending import pending_bp
    from routes.personnel import personnel_bp
    from routes.profile import profile_bp
    from routes.reports import reports_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(personnel_bp, url_prefix="/personnel")
    app.register_blueprint(attendance_bp, url_prefix="/attendance")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(pending_bp, url_prefix="/pending")
    app.register_blueprint(profile_bp, url_prefix="/profile")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(kiosk_bp, url_prefix="/kiosk")

    @app.route("/")
    def index():
        """Root route - redirect authenticated users to dashboard, others to login"""
        if current_user.is_authenticated:
            if getattr(current_user, "is_kiosk", False):
                return redirect(url_for("kiosk.index"))
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("auth.login"))

    # Allowed endpoints for kiosk accounts — everything else is blocked
    _KIOSK_ALLOWED_ENDPOINTS = {
        "auth.logout",
        "auth.login",
        "kiosk.index",
        "kiosk.manual_entry",
        "kiosk.recent_json",
        "api.capture_attendance_enhanced",
        "api.capture_attendance",
        "static",
    }

    @app.before_request
    def enforce_active_session():
        """Immediately revoke sessions for deactivated users.
        Also restricts kiosk accounts to kiosk-only endpoints.
        """
        if not current_user.is_authenticated:
            return None

        # Let logout endpoint run without interruption.
        if request.endpoint == "auth.logout":
            return None

        if not getattr(current_user, "is_active", True):
            logout_user()
            flash("Your account is inactive. Please contact an administrator.", "error")
            return redirect(url_for("auth.login"))

        # Kiosk accounts may only access kiosk routes + auth + static
        if getattr(current_user, "is_kiosk", False):
            endpoint = request.endpoint or ""
            if endpoint not in _KIOSK_ALLOWED_ENDPOINTS:
                return redirect(url_for("kiosk.index"))

        return None

    # Custom error page handlers
    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 Not Found errors with custom template"""
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 Internal Server errors and rollback database changes"""
        db.session.rollback()  # Rollback any incomplete database transactions
        return render_template("errors/500.html"), 500

    # Custom Jinja2 template filters for date/time formatting
    @app.template_filter("datetime")
    def datetime_filter(value, format="%Y-%m-%d %H:%M:%S"):
        """Format datetime objects in templates"""
        if value is None:
            return ""
        return value.strftime(format)

    @app.template_filter("date")
    def date_filter(value, format="%Y-%m-%d"):
        """Format date objects in templates"""
        if value is None:
            return ""
        return value.strftime(format)

    @app.template_filter("time")
    def time_filter(value, format="%H:%M:%S"):
        """Format time objects in templates"""
        if value is None:
            return ""
        return value.strftime(format)

    # Global template context - make enums available in all templates
    @app.context_processor
    def inject_station_types():
        """Make StationType and AttendanceStatus enums available in all templates"""
        return dict(StationType=StationType, AttendanceStatus=AttendanceStatus)

    # Initialize database and optionally create bootstrap admin user
    with app.app_context():
        db.create_all()  # Create all database tables

        auto_create_admin = os.environ.get("AUTO_CREATE_ADMIN", "false").lower() == "true"
        if auto_create_admin:
            admin = User.query.filter_by(is_admin=True).first()
            if not admin:
                admin_username = os.environ.get("DEFAULT_ADMIN_USERNAME", "admin")
                admin_email = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@bfp.gov.ph")
                admin_password = os.environ.get("DEFAULT_ADMIN_PASSWORD")

                if not admin_password:
                    raise RuntimeError(
                        "AUTO_CREATE_ADMIN is enabled but DEFAULT_ADMIN_PASSWORD is not set."
                    )

                admin = User(
                    username=admin_username,
                    email=admin_email,
                    password=generate_password_hash(admin_password),
                    station_type=StationType.CENTRAL,
                    is_admin=True,
                    is_kiosk=False,
                    must_change_password=True,  # Force password change on first login
                )
                db.session.add(admin)
                db.session.commit()
                logger.warning(
                    "Bootstrap admin created from environment settings. "
                    "Change the password immediately after first login."
                )

    return app


def _configure_logging():
    """Set up app logging with file rotation to avoid unbounded log growth."""
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    file_handler = RotatingFileHandler(
        "bfp_attendance.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)


def _validate_runtime_requirements(app):
    """Log missing runtime packages and critical resource issues at startup."""
    required_modules = ["cv2", "numpy", "torch", "ultralytics", "scipy"]
    missing_modules = []

    for module_name in required_modules:
        try:
            __import__(module_name)
        except ImportError:
            missing_modules.append(module_name)

    if missing_modules:
        app.logger.error(
            "Missing required runtime modules: %s. Install dependencies from requirements.txt.",
            ", ".join(missing_modules),
        )

    yolo_model_path = os.path.join(app.root_path, "face_rec_module", "yolov11n-face.pt")
    if not os.path.exists(yolo_model_path):
        app.logger.warning("YOLO model file not found at %s", yolo_model_path)


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)
