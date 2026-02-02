# Core Python libraries
import logging
import os
from datetime import datetime

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Flask core framework and utilities
from flask import Flask, redirect, render_template, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, current_user
from werkzeug.security import generate_password_hash

# Face recognition service (imported but not used in app.py - available for blueprints)
from face_rec_module.face_service import cleanup_old_attendance_images

# Database models and enums
from models import AttendanceStatus, StationType, User, db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("bfp_attendance.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def create_app():
    """Create and configure the Flask application instance"""
    app = Flask(__name__)

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
                "Generate a secure key with: python -c 'import secrets; print(secrets.token_hex(32))'"
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

    # Enhanced face detection settings (InsightFace)
    # Set to True to use InsightFace (requires: pip install insightface onnxruntime)
    # InsightFace provides better accuracy with RetinaFace detection and ArcFace embeddings
    app.config["USE_INSIGHTFACE"] = (
        os.environ.get("USE_INSIGHTFACE", "false").lower() == "true"
    )

    # Liveness detection settings
    app.config["LIVENESS_TEXTURE_THRESHOLD"] = (
        0.75  # Practical security - blocks most photos while allowing live faces
    )
    app.config["LIVENESS_REQUIRE_MULTI_FRAME"] = (
        True  # Require multiple frames for enhanced security
    )
    app.config["LIVENESS_MIN_FRAME_DIFFERENCE"] = (
        0.02  # Minimum change between frames to detect motion
    )
    app.config["LIVENESS_MIN_MOTION"] = 0.001  # Minimum motion for live detection
    app.config["LIVENESS_MAX_MOTION"] = 0.15  # Maximum motion (prevent video playback)

    # Create required directories for file uploads and temporary storage
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["TEMP_ATTENDANCE_FOLDER"], exist_ok=True)

    # Initialize database extension with app context
    db.init_app(app)

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

    @app.route("/")
    def index():
        """Root route - redirect authenticated users to dashboard, others to login"""
        if current_user.is_authenticated:
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("auth.login"))

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

    # Initialize database and create default admin user
    with app.app_context():
        db.create_all()  # Create all database tables

        # Create default admin user if it doesn't exist
        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(
                username="admin",
                email="admin@bfp.gov.ph",
                password=generate_password_hash("admin123"),
                station_type=StationType.CENTRAL,
                is_admin=True,
                must_change_password=True,  # Force password change on first login
            )
            db.session.add(admin)
            db.session.commit()
            logger.warning(
                "Default admin user created with username 'admin' and password 'admin123'. "
                "IMPORTANT: Change this password immediately after first login!"
            )

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)
