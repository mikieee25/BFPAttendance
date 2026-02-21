from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    make_response,
    flash,
    jsonify,
)
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date
import pandas as pd
from io import BytesIO, StringIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

from models import Personnel, Attendance, User, AttendanceStatus

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

    # Get all stations for the dropdown (admin only)
    stations = User.query.all() if current_user.is_admin else [current_user]

    return render_template("reports/index.html", stats=stats, stations=stations)


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
    on_leave_count = len(
        [a for a in attendance_data if a.status == AttendanceStatus.ON_LEAVE]
    )
    absent_count = total_expected_attendance - present_count - on_leave_count

    # All personnel objects for shifting calculations
    all_personnel = personnel_query.all()

    # Daily attendance summary
    daily_summary = {}
    current_date = start_date
    while current_date <= end_date:
        day_attendance = [a for a in attendance_data if a.date == current_date]
        day_present = len(
            [
                a
                for a in day_attendance
                if a.status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]
            ]
        )
        day_late = len(
            [a for a in day_attendance if a.status == AttendanceStatus.LATE]
        )
        day_on_leave = len(
            [a for a in day_attendance if a.status == AttendanceStatus.ON_LEAVE]
        )
        day_absent = total_personnel - day_present - day_on_leave
        day_shifting_on_duty = len(
            [p for p in all_personnel if p.is_shifting and p.is_on_duty(current_date)]
        )
        daily_summary[current_date] = {
            "present": day_present,
            "late": day_late,
            "on_leave": day_on_leave,
            "absent": max(day_absent, 0),
            "shifting_on_duty": day_shifting_on_duty,
        }
        current_date += timedelta(days=1)

    # Personnel attendance summary
    personnel_summary = []
    for person in all_personnel:
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
        on_leave_days = len(
            [a for a in person_attendance if a.status == AttendanceStatus.ON_LEAVE]
        )
        absent_days = total_days - present_days - on_leave_days

        personnel_summary.append(
            {
                "personnel": person,
                "present_days": present_days,
                "late_days": late_days,
                "on_leave_days": on_leave_days,
                "absent_days": max(absent_days, 0),
                "attendance_rate": (
                    (present_days / total_days * 100) if total_days > 0 else 0
                ),
            }
        )

    # Sort by present days descending
    personnel_summary.sort(key=lambda x: x["present_days"], reverse=True)

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
        on_leave_count=on_leave_count,
        absent_count=absent_count,
        daily_summary=daily_summary,
        personnel_summary=personnel_summary,
    )


@reports_bp.route("/api/day-detail")
@login_required
def api_day_detail():
    """API endpoint: return present/late/absent/on_leave/shifting_off breakdown for a given date."""
    date_str = request.args.get("date")
    station_id = request.args.get("station_id")

    if not date_str:
        return jsonify({"error": "date parameter required"}), 400

    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format"}), 400

    # Build personnel + attendance queries respecting access control
    if current_user.is_admin:
        personnel_query = Personnel.query
        attendance_query = Attendance.query.join(Personnel)
    else:
        personnel_query = Personnel.query.filter_by(station_id=current_user.id)
        attendance_query = Attendance.query.join(Personnel).filter(
            Personnel.station_id == current_user.id
        )

    if station_id:
        try:
            sid = int(station_id)
            personnel_query = personnel_query.filter_by(station_id=sid)
            attendance_query = attendance_query.filter(Personnel.station_id == sid)
        except (ValueError, TypeError):
            pass

    all_personnel = personnel_query.all()
    day_attendance = {
        a.personnel_id: a
        for a in attendance_query.filter(Attendance.date == target_date).all()
    }

    def _fmt_person(person, record=None):
        return {
            "id": person.id,
            "full_name": person.full_name,
            "rank": person.rank,
            "station": person.station.station_name,
            "is_shifting": person.is_shifting,
            "status": record.status.value if record and record.status else None,
            "time_in": record.time_in.strftime("%H:%M") if record and record.time_in else None,
            "time_out": record.time_out.strftime("%H:%M") if record and record.time_out else None,
        }

    groups = {
        "present": [],
        "late": [],
        "on_leave": [],
        "absent": [],
        "shifting_off": [],
    }

    for person in all_personnel:
        record = day_attendance.get(person.id)

        # Shifting personnel whose cycle says they are off today → separate bucket
        if person.is_shifting and not person.is_on_duty(target_date):
            groups["shifting_off"].append(_fmt_person(person, record))
            continue

        if record is None:
            groups["absent"].append(_fmt_person(person))
        elif record.status == AttendanceStatus.PRESENT:
            groups["present"].append(_fmt_person(person, record))
        elif record.status == AttendanceStatus.LATE:
            groups["late"].append(_fmt_person(person, record))
        elif record.status == AttendanceStatus.ON_LEAVE:
            groups["on_leave"].append(_fmt_person(person, record))
        else:
            groups["absent"].append(_fmt_person(person, record))

    return jsonify(groups)


@reports_bp.route("/monthly-trends")
@login_required
def monthly_trends():
    # Get the last 12 months of data
    months_data = []
    current_month_start = datetime.now().date().replace(day=1)

    for i in range(12):
        month_number = current_month_start.month - i
        year_number = current_month_start.year
        while month_number <= 0:
            month_number += 12
            year_number -= 1
        month_start = date(year_number, month_number, 1)

        # Calculate month end
        if month_start.month == 12:
            month_end = date(month_start.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(month_start.year, month_start.month + 1, 1) - timedelta(
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
            Attendance.date.between(month_start, month_end)
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
        on_leave_count = len(
            [a for a in month_attendance if a.status == AttendanceStatus.ON_LEAVE]
        )

        # Calculate working days in month (approximate)
        total_days = (month_end - month_start).days + 1
        expected_attendance = personnel_count * total_days
        absent_count = max(expected_attendance - present_count - on_leave_count, 0)

        months_data.insert(
            0,
            {
                "month": month_start.strftime("%b %Y"),
                "present": present_count,
                "late": late_count,
                "on_leave": on_leave_count,
                "absent": absent_count,
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
        output = StringIO()
        df.to_csv(output, index=False)
        response = make_response(output.getvalue())
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = f"attachment; filename={filename}.csv"
        return response

    elif format_type == "pdf":
        # Create PDF file
        output = BytesIO()

        # Create PDF document
        doc = SimpleDocTemplate(
            output,
            pagesize=landscape(letter),
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=18,
        )

        # Container for PDF elements
        elements = []

        # Styles
        styles = getSampleStyleSheet()

        # Title
        title_text = f"Attendance Report ({start_date} to {end_date})"
        title = Paragraph(f"<b>{title_text}</b>", styles["Title"])
        elements.append(title)
        elements.append(Spacer(1, 0.3 * inch))

        # Prepare table data
        table_data = [
            [
                "Date",
                "Personnel",
                "Rank",
                "Station",
                "Time In",
                "Time Out",
                "Status",
                "Hours",
            ]
        ]

        for record in attendance_data:
            table_data.append(
                [
                    record.date.strftime("%Y-%m-%d"),
                    record.personnel.full_name,
                    record.personnel.rank if record.personnel.rank else "",
                    record.personnel.station.station_name,
                    record.time_in.strftime("%H:%M") if record.time_in else "",
                    record.time_out.strftime("%H:%M") if record.time_out else "",
                    record.status.value if record.status else "",
                    f"{record.work_hours:.1f}" if record.work_hours > 0 else "",
                ]
            )

        # Create table
        table = Table(table_data, repeatRows=1)

        # Style the table
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.lightgrey],
                    ),
                ]
            )
        )

        elements.append(table)

        # Build PDF
        doc.build(elements)
        output.seek(0)

        response = make_response(output.read())
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f"attachment; filename={filename}.pdf"
        return response

    else:
        flash("Invalid export format", "error")
        return redirect(url_for("reports.index"))
