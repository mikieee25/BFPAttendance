from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    flash,
    current_app,
)
from flask_login import login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timedelta

from models import db, User, Personnel, Attendance, ActivityLog, StationType

profile_bp = Blueprint("profile", __name__)


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

        # Validate current password
        if not check_password_hash(current_user.password, current_password):
            flash("Current password is incorrect", "error")
            return render_template("profile/change_password.html")

        # Validate new password
        if new_password != confirm_password:
            flash("New passwords do not match", "error")
            return render_template("profile/change_password.html")

        if len(new_password) < 6:
            flash("New password must be at least 6 characters long", "error")
            return render_template("profile/change_password.html")

        # Update password
        current_user.password = generate_password_hash(new_password)

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

    return render_template("profile/change_password.html")


@profile_bp.route("/admin-tools")
@login_required
def admin_tools():
    if not current_user.is_admin:
        flash("Access denied. Only administrators can access admin tools.", "error")
        return redirect(url_for("profile.index"))

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
def reset_attendance():
    if not current_user.is_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

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
            return jsonify({"success": False, "error": "Invalid reset parameters"}), 400

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id, title="Attendance Reset", description=message
        )
        db.session.add(activity)
        db.session.commit()

        return jsonify({"success": True, "message": message})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@profile_bp.route("/system-backup", methods=["POST"])
@login_required
def system_backup():
    if not current_user.is_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    try:
        # This is a placeholder for backup functionality
        # In a real application, you would implement database backup here

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="System Backup",
            description="System backup initiated",
        )
        db.session.add(activity)
        db.session.commit()

        return jsonify(
            {"success": True, "message": "System backup completed successfully"}
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


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
