import os
import subprocess
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from models import ActivityLog, Attendance, PendingAttendance, Personnel, StationType, User, db
from sqlalchemy import or_
from utils import admin_required, handle_api_exception, json_error, validate_password

profile_bp = Blueprint("profile", __name__)


def _database_config_from_url(db_url: str):
    parsed = urlparse(db_url.replace("mysql+pymysql://", "mysql://", 1))
    if not parsed.scheme.startswith("mysql"):
        return None
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 3306,
        "user": parsed.username or "root",
        "password": parsed.password or "",
        "database": (parsed.path or "").lstrip("/"),
    }


def _cleanup_attendance_images() -> int:
    """Delete temporary attendance images used for face capture demos."""
    temp_root = Path(current_app.static_folder) / "images" / "attendance_temp"
    legacy_root = (
        Path(current_app.static_folder) / "images" / "attendance_images_temp"
    )

    deleted_items = 0
    for root in [temp_root, legacy_root]:
        if not root.exists():
            continue
        for item in root.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
                deleted_items += 1
            except Exception as exc:
                current_app.logger.warning("Failed deleting %s: %s", item, exc)

    return deleted_items


def _run_database_backup():
    db_url = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    db_config = _database_config_from_url(db_url)
    if not db_config or not db_config.get("database"):
        raise RuntimeError("Unsupported DATABASE_URL format for backup.")

    backup_dir = Path(current_app.root_path) / "manage" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"bfp_attendance_backup_{timestamp}.sql"
    backup_path = backup_dir / backup_filename

    cmd = [
        "mysqldump",
        f"--host={db_config['host']}",
        f"--port={db_config['port']}",
        f"--user={db_config['user']}",
    ]
    if db_config["password"]:
        cmd.append(f"--password={db_config['password']}")
    cmd.extend(
        [
            "--single-transaction",
            "--routines",
            "--triggers",
            "--add-drop-table",
            "--complete-insert",
            db_config["database"],
        ]
    )

    with backup_path.open("w", encoding="utf-8") as backup_file:
        result = subprocess.run(
            cmd,
            stdout=backup_file,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    if result.returncode != 0:
        if backup_path.exists():
            backup_path.unlink()
        raise RuntimeError(result.stderr.strip() or "mysqldump failed")
    if not backup_path.exists() or backup_path.stat().st_size == 0:
        raise RuntimeError("Backup file was not generated.")

    return backup_filename


@profile_bp.route("/")
@login_required
def index():
    # Get recent activity logs for current user
    recent_activities = (
        ActivityLog.query.filter_by(user_id=current_user.id)
        .order_by(ActivityLog.timestamp.desc())
        .limit(10)
        .all()
    )

    # Get recent attendance records for current user
    recent_attendance = []
    if hasattr(current_user, "personnel_id") and current_user.personnel_id:
        recent_attendance = (
            Attendance.query.filter_by(personnel_id=current_user.personnel_id)
            .order_by(Attendance.date.desc())
            .limit(5)
            .all()
        )

    # Calculate attendance statistics for current user
    current_month = datetime.now().replace(day=1)
    next_month = (current_month + timedelta(days=32)).replace(day=1)

    # Get this month's attendance records
    this_month_attendance = []
    if hasattr(current_user, "personnel_id") and current_user.personnel_id:
        this_month_attendance = (
            Attendance.query.filter_by(personnel_id=current_user.personnel_id)
            .filter(
                Attendance.date >= current_month.date(),
                Attendance.date < next_month.date(),
            )
            .all()
        )

    # Calculate stats
    total_days = len(this_month_attendance)
    days_present = len([a for a in this_month_attendance if a.status.name == "PRESENT"])
    days_late = len([a for a in this_month_attendance if a.status.name == "LATE"])
    days_absent = len([a for a in this_month_attendance if a.status.name == "ABSENT"])

    # Calculate attendance rate
    working_days = (datetime.now().date() - current_month.date()).days + 1
    this_month_rate = (
        int((days_present / working_days * 100)) if working_days > 0 else 0
    )

    attendance_stats = {
        "this_month_rate": this_month_rate,
        "days_present": days_present,
        "days_late": days_late,
        "days_absent": days_absent,
    }

    # Get general statistics
    if current_user.is_admin:
        total_personnel = Personnel.query.count()
        total_users = User.query.count()
        today_attendance = Attendance.query.filter(
            Attendance.date == datetime.now().date()
        ).count()
    else:
        total_personnel = Personnel.query.filter_by(station_id=current_user.id).count()
        total_users = 1  # Just the current user
        today_attendance = (
            Attendance.query.join(Personnel)
            .filter(
                Personnel.station_id == current_user.id,
                Attendance.date == datetime.now().date(),
            )
            .count()
        )

    user_stats = {
        "total_personnel": total_personnel,
        "total_users": total_users,
        "today_attendance": today_attendance,
    }

    return render_template(
        "profile/index.html",
        recent_activities=recent_activities,
        user_stats=user_stats,
        attendance_stats=attendance_stats,
        recent_attendance=recent_attendance,
    )


@profile_bp.route("/edit", methods=["GET", "POST"])
@login_required
def edit():
    if request.method == "POST":
        current_user.username = request.form["username"]
        current_user.email = request.form["email"]

        # Only admin can change station type
        if current_user.is_admin:
            current_user.station_type = StationType(request.form["station_type"])

        # Handle profile picture upload
        if "profile_picture" in request.files:
            file = request.files["profile_picture"]
            if file and file.filename:
                # Validate file type
                allowed_extensions = {"png", "jpg", "jpeg", "gif"}
                if (
                    "." in file.filename
                    and file.filename.rsplit(".", 1)[1].lower() in allowed_extensions
                ):
                    filename = secure_filename(file.filename)
                    # Add timestamp to avoid conflicts
                    name, ext = os.path.splitext(filename)
                    filename = f"{current_user.username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"

                    # Save file
                    upload_path = os.path.join(
                        current_app.static_folder, "images", "profiles"
                    )
                    os.makedirs(upload_path, exist_ok=True)
                    file_path = os.path.join(upload_path, filename)
                    file.save(file_path)

                    # Update user profile picture path
                    current_user.profile_picture = f"images/profiles/{filename}"

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="Profile Updated",
            description=f"User {current_user.username} updated their profile",
        )
        db.session.add(activity)
        db.session.commit()

        flash("Profile updated successfully", "success")
        return redirect(url_for("profile.index"))

    return render_template("profile/edit.html", station_types=StationType)


@profile_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        # Validate current password (skip for forced password changes)
        if not current_user.must_change_password:
            if not check_password_hash(current_user.password, current_password):
                flash("Current password is incorrect", "error")
                return render_template(
                    "profile/change_password.html",
                    must_change=current_user.must_change_password,
                )

        # Validate new password match
        if new_password != confirm_password:
            flash("New passwords do not match", "error")
            return render_template(
                "profile/change_password.html",
                must_change=current_user.must_change_password,
            )

        # Validate password strength using security utility
        is_valid, message = validate_password(new_password)
        if not is_valid:
            flash(message, "error")
            return render_template(
                "profile/change_password.html",
                must_change=current_user.must_change_password,
            )

        # Update password
        current_user.password = generate_password_hash(new_password)

        # Clear must_change_password flag if it was set
        if current_user.must_change_password:
            current_user.must_change_password = False

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="Password Changed",
            description=f"User {current_user.username} changed their password",
        )
        db.session.add(activity)
        db.session.commit()

        flash("Password changed successfully", "success")
        return redirect(url_for("profile.index"))

    return render_template(
        "profile/change_password.html", must_change=current_user.must_change_password
    )


@profile_bp.route("/admin-tools")
@login_required
@admin_required()
def admin_tools():
    # Get system statistics
    total_users = User.query.count()
    total_personnel = Personnel.query.count()
    total_attendance = Attendance.query.count()

    # Recent system activities
    recent_activities = (
        ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(20).all()
    )

    return render_template(
        "profile/admin_tools.html",
        total_users=total_users,
        total_personnel=total_personnel,
        total_attendance=total_attendance,
        recent_activities=recent_activities,
    )


@profile_bp.route("/reset-attendance", methods=["POST"])
@login_required
@admin_required(api=True)
def reset_attendance():
    try:
        data = request.get_json()
        reset_type = data.get("type")
        date_range = data.get("date_range")

        if reset_type == "all":
            # Delete all attendance records
            Attendance.query.delete()
            message = "All attendance records have been reset"
        elif reset_type == "date_range" and date_range:
            start_date = datetime.strptime(date_range["start"], "%Y-%m-%d").date()
            end_date = datetime.strptime(date_range["end"], "%Y-%m-%d").date()

            Attendance.query.filter(
                Attendance.date.between(start_date, end_date)
            ).delete()
            message = (
                f"Attendance records from {start_date} to {end_date} have been reset"
            )
        else:
            return json_error("Invalid reset parameters", 400)

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id, title="Attendance Reset", description=message
        )
        db.session.add(activity)
        db.session.commit()

        return jsonify({"success": True, "message": message})

    except Exception as e:
        db.session.rollback()
        return handle_api_exception(e)


@profile_bp.route("/clean-demo", methods=["POST"])
@login_required
@admin_required(api=True)
def clean_demo():
    """Clean attendance + pending + related logs/images for demo resets."""
    try:
        deleted_attendance = Attendance.query.delete()
        deleted_pending = PendingAttendance.query.delete()
        deleted_logs = ActivityLog.query.filter(
            or_(
                ActivityLog.title.ilike("%attendance%"),
                ActivityLog.description.ilike("%attendance%"),
            )
        ).delete(synchronize_session=False)
        db.session.commit()

        deleted_images = _cleanup_attendance_images()

        activity = ActivityLog(
            user_id=current_user.id,
            title="Demo Cleanup",
            description=(
                "Demo reset completed. "
                f"Attendance: {deleted_attendance}, Pending: {deleted_pending}, "
                f"Logs: {deleted_logs}, Images: {deleted_images}"
            ),
        )
        db.session.add(activity)
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "message": "Demo data cleaned successfully.",
                "deleted": {
                    "attendance": deleted_attendance,
                    "pending": deleted_pending,
                    "logs": deleted_logs,
                    "images": deleted_images,
                },
            }
        )
    except Exception as e:
        db.session.rollback()
        return handle_api_exception(e, "Demo cleanup failed. Check server logs.")


@profile_bp.route("/system-backup", methods=["POST"])
@login_required
@admin_required(api=True)
def system_backup():
    try:
        backup_filename = _run_database_backup()

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="System Backup",
            description=f"System backup created: {backup_filename}",
        )
        db.session.add(activity)
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "message": "System backup completed successfully",
                "backup_file": backup_filename,
            }
        )

    except Exception as e:
        return handle_api_exception(e, "System backup failed. Check server logs.")


@profile_bp.route("/activity-logs")
@login_required
def activity_logs():
    # Get activity logs based on user role
    if current_user.is_admin:
        activities = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).all()
    else:
        activities = (
            ActivityLog.query.filter_by(user_id=current_user.id)
            .order_by(ActivityLog.timestamp.desc())
            .all()
        )

    return render_template("profile/activity_logs.html", activities=activities)
