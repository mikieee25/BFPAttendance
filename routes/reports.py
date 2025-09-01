from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    make_response,
    flash,
)
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import func, desc, and_
import pandas as pd
from io import BytesIO

from models import db, Personnel, Attendance, User, AttendanceStatus, StationType

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/")
@login_required
def index():
    # Get basic stats for the dashboard
    today = datetime.now().date()
    current_month_start = today.replace(day=1)

    # Base queries based on user role
    if current_user.is_admin:
        personnel_query = Personnel.query
        attendance_query = Attendance.query.join(Personnel)
    else:
        personnel_query = Personnel.query.filter_by(station_id=current_user.id)
        attendance_query = Attendance.query.join(Personnel).filter(
            Personnel.station_id == current_user.id
        )

    # Calculate stats
    total_personnel = personnel_query.count()

    # Today's attendance
    today_attendance = attendance_query.filter(Attendance.date == today).count()
    today_present = attendance_query.filter(
        Attendance.date == today, Attendance.status == AttendanceStatus.PRESENT
    ).count()
    today_late = attendance_query.filter(
        Attendance.date == today, Attendance.status == AttendanceStatus.LATE
    ).count()
    today_absent = total_personnel - (today_present + today_late)

    # This month's stats
    month_attendance = attendance_query.filter(
        Attendance.date >= current_month_start
    ).count()

    stats = {
        "total_personnel": total_personnel,
        "today_attendance": today_attendance,
        "today_present": today_present,
        "today_late": today_late,
        "today_absent": today_absent,
        "month_attendance": month_attendance,
    }

    return render_template("reports/index.html", stats=stats)


@reports_bp.route("/attendance-summary")
@login_required
def attendance_summary():
    # Get date range from query params
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    station_id = request.args.get("station_id")

    # Default to current month if no dates provided
    if not start_date:
        start_date = datetime.now().replace(day=1).date()
    else:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

    if not end_date:
        end_date = datetime.now().date()
    else:
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

    # Base queries
    if current_user.is_admin:
        personnel_query = Personnel.query
        attendance_query = Attendance.query.join(Personnel)
        stations = User.query.all()
    else:
        personnel_query = Personnel.query.filter_by(station_id=current_user.id)
        attendance_query = Attendance.query.join(Personnel).filter(
            Personnel.station_id == current_user.id
        )
        stations = [current_user]

    # Apply station filter for admin
    if current_user.is_admin and station_id:
        personnel_query = personnel_query.filter_by(station_id=int(station_id))
        attendance_query = attendance_query.filter(
            Personnel.station_id == int(station_id)
        )

    # Get attendance data for the date range
    attendance_data = attendance_query.filter(
        Attendance.date.between(start_date, end_date)
    ).all()

    # Summary statistics
    total_personnel = personnel_query.count()
    total_days = (end_date - start_date).days + 1
    total_expected_attendance = total_personnel * total_days

    present_count = len(
        [
            a
            for a in attendance_data
            if a.status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]
        ]
    )
    late_count = len([a for a in attendance_data if a.status == AttendanceStatus.LATE])
    absent_count = total_expected_attendance - present_count

    # Attendance rate
    attendance_rate = (
        (present_count / total_expected_attendance * 100)
        if total_expected_attendance > 0
        else 0
    )
    punctuality_rate = (
        ((present_count - late_count) / present_count * 100) if present_count > 0 else 0
    )

    # Daily attendance summary
    daily_summary = {}
    current_date = start_date
    while current_date <= end_date:
        day_attendance = [a for a in attendance_data if a.date == current_date]
        daily_summary[current_date] = {
            "present": len(
                [
                    a
                    for a in day_attendance
                    if a.status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]
                ]
            ),
            "late": len(
                [a for a in day_attendance if a.status == AttendanceStatus.LATE]
            ),
            "absent": total_personnel
            - len(
                [
                    a
                    for a in day_attendance
                    if a.status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]
                ]
            ),
        }
        current_date += timedelta(days=1)

    # Personnel attendance summary
    personnel_summary = []
    for person in personnel_query.all():
        person_attendance = [a for a in attendance_data if a.personnel_id == person.id]
        present_days = len(
            [
                a
                for a in person_attendance
                if a.status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]
            ]
        )
        late_days = len(
            [a for a in person_attendance if a.status == AttendanceStatus.LATE]
        )
        absent_days = total_days - present_days

        personnel_summary.append(
            {
                "personnel": person,
                "present_days": present_days,
                "late_days": late_days,
                "absent_days": absent_days,
                "attendance_rate": (
                    (present_days / total_days * 100) if total_days > 0 else 0
                ),
            }
        )

    # Sort by attendance rate
    personnel_summary.sort(key=lambda x: x["attendance_rate"], reverse=True)

    return render_template(
        "reports/attendance_summary.html",
        start_date=start_date,
        end_date=end_date,
        selected_station=int(station_id) if station_id else None,
        stations=stations,
        total_personnel=total_personnel,
        total_days=total_days,
        present_count=present_count,
        late_count=late_count,
        absent_count=absent_count,
        attendance_rate=attendance_rate,
        punctuality_rate=punctuality_rate,
        daily_summary=daily_summary,
        personnel_summary=personnel_summary,
    )


@reports_bp.route("/monthly-trends")
@login_required
def monthly_trends():
    # Get the last 12 months of data
    months_data = []
    current_date = datetime.now().replace(day=1)

    for i in range(12):
        month_start = current_date - timedelta(days=30 * i)
        month_start = month_start.replace(day=1)

        # Calculate month end
        if month_start.month == 12:
            month_end = month_start.replace(
                year=month_start.year + 1, month=1
            ) - timedelta(days=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1) - timedelta(
                days=1
            )

        # Base query
        if current_user.is_admin:
            personnel_count = Personnel.query.count()
            attendance_query = Attendance.query.join(Personnel)
        else:
            personnel_count = Personnel.query.filter_by(
                station_id=current_user.id
            ).count()
            attendance_query = Attendance.query.join(Personnel).filter(
                Personnel.station_id == current_user.id
            )

        # Get attendance for this month
        month_attendance = attendance_query.filter(
            Attendance.date.between(month_start.date(), month_end.date())
        ).all()

        present_count = len(
            [
                a
                for a in month_attendance
                if a.status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]
            ]
        )
        late_count = len(
            [a for a in month_attendance if a.status == AttendanceStatus.LATE]
        )

        # Calculate working days in month (approximate)
        working_days = (month_end - month_start).days + 1
        expected_attendance = personnel_count * working_days

        months_data.insert(
            0,
            {
                "month": month_start.strftime("%b %Y"),
                "present": present_count,
                "late": late_count,
                "attendance_rate": (
                    (present_count / expected_attendance * 100)
                    if expected_attendance > 0
                    else 0
                ),
                "punctuality_rate": (
                    ((present_count - late_count) / present_count * 100)
                    if present_count > 0
                    else 0
                ),
            },
        )

    return render_template("reports/monthly_trends.html", months_data=months_data)


@reports_bp.route("/station-comparison")
@login_required
def station_comparison():
    if not current_user.is_admin:
        flash(
            "Access denied. Only administrators can view station comparison reports.",
            "error",
        )
        return redirect(url_for("reports.index"))

    # Get date range from query params
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    # Default to current month if no dates provided
    if not start_date:
        start_date = datetime.now().replace(day=1).date()
    else:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

    if not end_date:
        end_date = datetime.now().date()
    else:
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

    # Get all stations
    stations = User.query.all()
    station_data = []

    total_days = (end_date - start_date).days + 1

    for station in stations:
        personnel_count = Personnel.query.filter_by(station_id=station.id).count()
        attendance_data = (
            Attendance.query.join(Personnel)
            .filter(
                Personnel.station_id == station.id,
                Attendance.date.between(start_date, end_date),
            )
            .all()
        )

        present_count = len(
            [
                a
                for a in attendance_data
                if a.status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]
            ]
        )
        late_count = len(
            [a for a in attendance_data if a.status == AttendanceStatus.LATE]
        )
        expected_attendance = personnel_count * total_days

        station_data.append(
            {
                "station": station,
                "personnel_count": personnel_count,
                "present_count": present_count,
                "late_count": late_count,
                "expected_attendance": expected_attendance,
                "attendance_rate": (
                    (present_count / expected_attendance * 100)
                    if expected_attendance > 0
                    else 0
                ),
                "punctuality_rate": (
                    ((present_count - late_count) / present_count * 100)
                    if present_count > 0
                    else 0
                ),
            }
        )

    # Sort by attendance rate
    station_data.sort(key=lambda x: x["attendance_rate"], reverse=True)

    return render_template(
        "reports/station_comparison.html",
        start_date=start_date,
        end_date=end_date,
        station_data=station_data,
        total_days=total_days,
    )


@reports_bp.route("/export/attendance")
@login_required
def export_attendance():
    # Get parameters
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    station_id = request.args.get("station_id")
    format_type = request.args.get("format", "xlsx")

    # Default to current month if no dates provided
    if not start_date:
        start_date = datetime.now().replace(day=1).date()
    else:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

    if not end_date:
        end_date = datetime.now().date()
    else:
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

    # Base query
    if current_user.is_admin:
        query = Attendance.query.join(Personnel)
    else:
        query = Attendance.query.join(Personnel).filter(
            Personnel.station_id == current_user.id
        )

    # Apply filters
    query = query.filter(Attendance.date.between(start_date, end_date))

    if current_user.is_admin and station_id:
        query = query.filter(Personnel.station_id == int(station_id))

    # Get data
    attendance_data = query.order_by(Attendance.date, Personnel.last_name).all()

    # Prepare data for export
    export_data = []
    for record in attendance_data:
        export_data.append(
            {
                "Date": record.date.strftime("%Y-%m-%d"),
                "Personnel": record.personnel.full_name,
                "Rank": record.personnel.rank,
                "Station": record.personnel.station.station_name,
                "Time In": (
                    record.time_in.strftime("%H:%M:%S") if record.time_in else ""
                ),
                "Time Out": (
                    record.time_out.strftime("%H:%M:%S") if record.time_out else ""
                ),
                "Status": record.status.value if record.status else "",
                "Work Hours": (
                    f"{record.work_hours:.2f}" if record.work_hours > 0 else ""
                ),
                "Confidence Score": (
                    f"{record.confidence_score:.2f}" if record.confidence_score else ""
                ),
                "Auto Captured": "Yes" if record.is_auto_captured else "No",
            }
        )

    # Create DataFrame
    df = pd.DataFrame(export_data)

    # Generate filename
    filename = f"attendance_report_{start_date}_{end_date}"

    if format_type == "xlsx":
        # Create Excel file
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Attendance Report", index=False)
        output.seek(0)

        response = make_response(output.read())
        response.headers["Content-Type"] = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response.headers["Content-Disposition"] = (
            f"attachment; filename={filename}.xlsx"
        )
        return response

    elif format_type == "csv":
        # Create CSV file
        output = BytesIO()
        df.to_csv(output, index=False)
        output.seek(0)

        response = make_response(output.getvalue())
        response.headers["Content-Type"] = "text/csv"
        response.headers["Content-Disposition"] = f"attachment; filename={filename}.csv"
        return response

    else:
        flash("Invalid export format", "error")
        return redirect(url_for("reports.index"))
