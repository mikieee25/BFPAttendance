from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import desc
from models import Personnel, Attendance, AttendanceStatus

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    # Get today's date
    today = datetime.now().date()

    # Base query for personnel under current user's station
    if current_user.is_admin:
        # Admin can see all personnel
        personnel_query = Personnel.query
        attendance_query = Attendance.query
    else:
        # Station users see only their personnel
        personnel_query = Personnel.query.filter_by(station_id=current_user.id)
        attendance_query = Attendance.query.join(Personnel).filter(
            Personnel.station_id == current_user.id
        )

    # Statistics
    total_personnel = personnel_query.count()

    # Today's attendance stats
    today_attendance = attendance_query.filter(Attendance.date == today).all()
    present_today = len(
        [
            a
            for a in today_attendance
            if a.status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]
        ]
    )
    absent_today = total_personnel - present_today
    late_today = len([a for a in today_attendance if a.status == AttendanceStatus.LATE])

    # Shifting personnel on duty today
    all_personnel = personnel_query.all()
    shifting_today = len(
        [p for p in all_personnel if p.is_shifting and p.is_on_duty(today)]
    )

    # Recent attendance records (last 10)
    recent_attendance = (
        attendance_query.order_by(desc(Attendance.date_created)).limit(10).all()
    )

    # Get current time for the clock
    current_time = datetime.now()

    context = {
        "total_personnel": total_personnel,
        "present_today": present_today,
        "absent_today": absent_today,
        "late_today": late_today,
        "shifting_today": shifting_today,
        "recent_attendance": recent_attendance,
        "current_time": current_time,
        "today": today,
    }

    return render_template("dashboard/index.html", **context)


@dashboard_bp.route("/api/time")
@login_required
def get_current_time():
    """API endpoint to get current time - DEPRECATED: Now using client-side clock"""
    current_time = datetime.now()
    return jsonify(
        {
            "time": current_time.strftime("%H:%M:%S"),
            "date": current_time.strftime("%A, %B %d, %Y"),
            "timestamp": current_time.isoformat(),
        }
    )


@dashboard_bp.route("/api/stats")
@login_required
def get_stats():
    """API endpoint for real-time dashboard statistics"""
    today = datetime.now().date()

    # Base query for personnel under current user's station
    if current_user.is_admin:
        personnel_query = Personnel.query
        attendance_query = Attendance.query
    else:
        personnel_query = Personnel.query.filter_by(station_id=current_user.id)
        attendance_query = Attendance.query.join(Personnel).filter(
            Personnel.station_id == current_user.id
        )

    total_personnel = personnel_query.count()
    today_attendance = attendance_query.filter(Attendance.date == today).all()
    present_today = len(
        [
            a
            for a in today_attendance
            if a.status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]
        ]
    )
    absent_today = total_personnel - present_today
    late_today = len([a for a in today_attendance if a.status == AttendanceStatus.LATE])

    all_personnel = personnel_query.all()
    shifting_today = len(
        [p for p in all_personnel if p.is_shifting and p.is_on_duty(today)]
    )

    return jsonify(
        {
            "total_personnel": total_personnel,
            "present_today": present_today,
            "absent_today": absent_today,
            "late_today": late_today,
            "shifting_today": shifting_today,
        }
    )
