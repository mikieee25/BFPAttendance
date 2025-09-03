from flask import Blueprint, render_template, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func, desc
from models import db, Personnel, Attendance, User, AttendanceStatus, StationType

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

    # Recent attendance records (last 10)
    recent_attendance = (
        attendance_query.order_by(desc(Attendance.date_created)).limit(10).all()
    )

    # Weekly attendance summary
    week_start = today - timedelta(days=today.weekday())
    weekly_data = []
    for i in range(7):
        date = week_start + timedelta(days=i)
        count = attendance_query.filter(
            Attendance.date == date,
            Attendance.status.in_([AttendanceStatus.PRESENT, AttendanceStatus.LATE]),
        ).count()
        weekly_data.append({"date": date.strftime("%A"), "count": count})

    # Monthly attendance trends
    current_month = datetime.now().replace(day=1)
    monthly_data = []
    for i in range(12):
        month = current_month - timedelta(days=30 * i)
        month_start = month.replace(day=1)
        if month == current_month:
            month_end = datetime.now().date()
        else:
            if month.month == 12:
                month_end = month.replace(
                    year=month.year + 1, month=1, day=1
                ) - timedelta(days=1)
            else:
                month_end = month.replace(month=month.month + 1, day=1) - timedelta(
                    days=1
                )

        count = attendance_query.filter(
            Attendance.date >= month_start.date(),
            Attendance.date <= month_end,
            Attendance.status.in_([AttendanceStatus.PRESENT, AttendanceStatus.LATE]),
        ).count()

        monthly_data.insert(0, {"month": month.strftime("%b %Y"), "count": count})

    # Get current time for the clock
    current_time = datetime.now()

    context = {
        "total_personnel": total_personnel,
        "present_today": present_today,
        "absent_today": absent_today,
        "late_today": late_today,
        "recent_attendance": recent_attendance,
        "weekly_data": weekly_data,
        "monthly_data": monthly_data,
        "current_time": current_time,
        "today": today,
    }

    return render_template("dashboard/index.html", **context)


@dashboard_bp.route("/api/time")
@login_required
def get_current_time():
    """API endpoint to get current time for the dashboard clock - DEPRECATED: Now using client-side clock"""
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

    return jsonify(
        {
            "total_personnel": total_personnel,
            "present_today": present_today,
            "absent_today": absent_today,
            "late_today": late_today,
        }
    )
