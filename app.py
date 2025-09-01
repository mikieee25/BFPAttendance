import os
from datetime import datetime
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    flash,
    session,
)
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import json

from models import (
    db,
    User,
    Personnel,
    Attendance,
    FaceData,
    ActivityLog,
    PendingAttendance,
    StationType,
    AttendanceStatus,
)
from face_recognition.face_service import (
    process_base64_image,
    recognize_face,
    load_face_database,
    process_attendance,
    register_face,
    cleanup_old_attendance_images,
)


def create_app():
    app = Flask(__name__)

    # Configuration
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "your-secret-key-here")
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
        app.root_path, "face_recognition", "yolov11n-face.pt"
    )
    app.config["FACE_DETECTION_CONFIDENCE"] = 0.5
    app.config["FACE_RECOGNITION_THRESHOLD"] = 0.75
    app.config["TORCH_DEVICE"] = "cpu"
    app.config["WORK_START_TIME"] = "08:00"
    app.config["ATTENDANCE_COOLDOWN"] = 60  # seconds
    app.config["ATTENDANCE_IMAGE_RETENTION_DAYS"] = 7

    # Create upload directories
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["TEMP_ATTENDANCE_FOLDER"], exist_ok=True)

    # Initialize extensions
    db.init_app(app)

    # Flask-Login setup
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Rate limiting
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://",
    )

    # Register blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.personnel import personnel_bp
    from routes.attendance import attendance_bp
    from routes.reports import reports_bp
    from routes.pending import pending_bp
    from routes.profile import profile_bp
    from routes.api import api_bp

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
        if current_user.is_authenticated:
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("auth.login"))

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    # Template filters
    @app.template_filter("datetime")
    def datetime_filter(value, format="%Y-%m-%d %H:%M:%S"):
        if value is None:
            return ""
        return value.strftime(format)

    @app.template_filter("date")
    def date_filter(value, format="%Y-%m-%d"):
        if value is None:
            return ""
        return value.strftime(format)

    @app.template_filter("time")
    def time_filter(value, format="%H:%M:%S"):
        if value is None:
            return ""
        return value.strftime(format)

    # Context processors
    @app.context_processor
    def inject_station_types():
        return dict(StationType=StationType, AttendanceStatus=AttendanceStatus)

    # Initialize database
    with app.app_context():
        db.create_all()

        # Create default admin user if not exists
        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(
                username="admin",
                email="admin@bfp.gov.ph",
                password=generate_password_hash("admin123"),
                station_type=StationType.CENTRAL,
                is_admin=True,
            )
            db.session.add(admin)
            db.session.commit()
            print("Default admin user created: admin/admin123")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)
