from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from sqlalchemy import func, desc, and_, or_
import os

from models import db, Personnel, Attendance, User, AttendanceStatus, ActivityLog
from face_recognition.face_service import (
    process_base64_image,
    recognize_face,
    load_face_database,
    process_attendance,
)

attendance_bp = Blueprint("attendance", __name__)


@attendance_bp.route("/")
@login_required
def index():
    # Get date range from query params
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    personnel_id = request.args.get("personnel_id")
    status = request.args.get("status")

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
        attendance_query = Attendance.query.join(Personnel)
        personnel_list = Personnel.query.all()
    else:
        attendance_query = Attendance.query.join(Personnel).filter(
            Personnel.station_id == current_user.id
        )
        personnel_list = Personnel.query.filter_by(station_id=current_user.id).all()

    # Apply filters
    attendance_query = attendance_query.filter(
        Attendance.date.between(start_date, end_date)
    )

    if personnel_id:
        attendance_query = attendance_query.filter(
            Attendance.personnel_id == personnel_id
        )

    if status:
        attendance_query = attendance_query.filter(
            Attendance.status == AttendanceStatus(status)
        )

    # Get attendance records
    attendance_records = attendance_query.order_by(
        desc(Attendance.date), desc(Attendance.time_in)
    ).all()

    return render_template(
        "attendance/index.html",
        attendance_records=attendance_records,
        personnel_list=personnel_list,
        start_date=start_date,
        end_date=end_date,
        selected_personnel=int(personnel_id) if personnel_id else None,
        selected_status=status,
        attendance_statuses=AttendanceStatus,
    )


@attendance_bp.route("/capture")
@login_required
def capture():
    return render_template("attendance/capture.html")


@attendance_bp.route("/api/capture", methods=["POST"])
@login_required
def api_capture():
    try:
        data = request.get_json()
        image_data = data.get("image")

        if not image_data:
            return jsonify({"success": False, "error": "No image provided"}), 400

        # Process the image and extract face
        face_embedding, face_metadata, temp_path = process_base64_image(image_data)

        if face_embedding is None:
            return (
                jsonify({"success": False, "error": "No face detected in the image"}),
                400,
            )

        # Load face database for current station
        station_id = None if current_user.is_admin else current_user.id
        face_database = load_face_database(station_id)

        if not face_database:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "No personnel registered in the face database",
                    }
                ),
                400,
            )

        # Recognize face
        recognized_id, confidence = recognize_face(face_embedding, face_database)

        if recognized_id is None:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Face not recognized. Please ensure you are registered in the system.",
                    }
                ),
                400,
            )

        # Process attendance
        result = process_attendance(recognized_id, confidence, image_data)

        # Clean up temp file
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

        # Log activity if successful
        if result.get("success"):
            personnel = Personnel.query.get(recognized_id)
            activity = ActivityLog(
                user_id=current_user.id,
                title="Attendance Captured",
                description=f"Attendance captured for {personnel.full_name} via face recognition",
            )
            db.session.add(activity)
            db.session.commit()

        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@attendance_bp.route("/manual", methods=["GET", "POST"])
@login_required
def manual():
    if request.method == "POST":
        personnel_id = request.form["personnel_id"]
        attendance_date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        time_in = request.form.get("time_in")
        time_out = request.form.get("time_out")
        status = AttendanceStatus(request.form["status"])
        notes = request.form.get("notes", "")

        # Validate personnel access
        personnel = Personnel.query.get_or_404(personnel_id)
        if not current_user.is_admin and personnel.station_id != current_user.id:
            flash(
                "You can only add attendance for personnel from your own station",
                "error",
            )
            return redirect(url_for("attendance.manual"))

        # Check if attendance already exists for this date
        existing = Attendance.query.filter_by(
            personnel_id=personnel_id, date=attendance_date
        ).first()
        if existing:
            flash(
                "Attendance record already exists for this personnel on this date",
                "error",
            )
            return redirect(url_for("attendance.manual"))

        # Create attendance record
        attendance = Attendance(
            personnel_id=personnel_id,
            date=attendance_date,
            status=status,
            is_auto_captured=False,
            is_approved=True,
            approved_by=current_user.id,
        )

        if time_in:
            time_in_obj = datetime.strptime(time_in, "%H:%M").time()
            attendance.time_in = datetime.combine(attendance_date, time_in_obj)

        if time_out:
            time_out_obj = datetime.strptime(time_out, "%H:%M").time()
            attendance.time_out = datetime.combine(attendance_date, time_out_obj)

        db.session.add(attendance)

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="Manual Attendance Added",
            description=f"Manual attendance added for {personnel.full_name} on {attendance_date}",
        )
        db.session.add(activity)
        db.session.commit()

        flash("Attendance record added successfully", "success")
        return redirect(url_for("attendance.index"))

    # Get personnel for dropdown
    if current_user.is_admin:
        personnel_list = Personnel.query.all()
    else:
        personnel_list = Personnel.query.filter_by(station_id=current_user.id).all()

    return render_template(
        "attendance/manual.html",
        personnel_list=personnel_list,
        attendance_statuses=AttendanceStatus,
        today=datetime.now().date(),
    )


@attendance_bp.route("/edit/<int:attendance_id>", methods=["GET", "POST"])
@login_required
def edit(attendance_id):
    attendance = Attendance.query.get_or_404(attendance_id)

    # Check access
    if not current_user.is_admin and attendance.personnel.station_id != current_user.id:
        flash(
            "You can only edit attendance for personnel from your own station", "error"
        )
        return redirect(url_for("attendance.index"))

    if request.method == "POST":
        attendance.status = AttendanceStatus(request.form["status"])

        time_in = request.form.get("time_in")
        time_out = request.form.get("time_out")

        if time_in:
            time_in_obj = datetime.strptime(time_in, "%H:%M").time()
            attendance.time_in = datetime.combine(attendance.date, time_in_obj)

        if time_out:
            time_out_obj = datetime.strptime(time_out, "%H:%M").time()
            attendance.time_out = datetime.combine(attendance.date, time_out_obj)

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="Attendance Updated",
            description=f"Attendance updated for {attendance.personnel.full_name} on {attendance.date}",
        )
        db.session.add(activity)
        db.session.commit()

        flash("Attendance updated successfully", "success")
        return redirect(url_for("attendance.index"))

    return render_template(
        "attendance/edit.html",
        attendance=attendance,
        attendance_statuses=AttendanceStatus,
    )


@attendance_bp.route("/delete/<int:attendance_id>", methods=["POST"])
@login_required
def delete(attendance_id):
    attendance = Attendance.query.get_or_404(attendance_id)

    # Check access
    if not current_user.is_admin and attendance.personnel.station_id != current_user.id:
        flash(
            "You can only delete attendance for personnel from your own station",
            "error",
        )
        return redirect(url_for("attendance.index"))

    personnel_name = attendance.personnel.full_name
    attendance_date = attendance.date

    # Log activity before deletion
    activity = ActivityLog(
        user_id=current_user.id,
        title="Attendance Deleted",
        description=f"Attendance deleted for {personnel_name} on {attendance_date}",
    )
    db.session.add(activity)

    db.session.delete(attendance)
    db.session.commit()

    flash(
        f"Attendance record for {personnel_name} on {attendance_date} deleted successfully",
        "success",
    )
    return redirect(url_for("attendance.index"))


@attendance_bp.route("/api/data")
@login_required
def api_data():
    """DataTables API endpoint"""
    # Get query parameters
    draw = request.args.get("draw", type=int)
    start = request.args.get("start", type=int)
    length = request.args.get("length", type=int)
    search_value = request.args.get("search[value]", "")

    # Base query
    if current_user.is_admin:
        query = Attendance.query.join(Personnel)
    else:
        query = Attendance.query.join(Personnel).filter(
            Personnel.station_id == current_user.id
        )

    # Apply search
    if search_value:
        query = query.filter(
            or_(
                Personnel.first_name.contains(search_value),
                Personnel.last_name.contains(search_value),
                Personnel.rank.contains(search_value),
            )
        )

    # Get total count
    total_records = query.count()

    # Apply pagination
    records = (
        query.order_by(desc(Attendance.date), desc(Attendance.time_in))
        .offset(start)
        .limit(length)
        .all()
    )

    # Format data
    data = []
    for record in records:
        data.append(
            {
                "id": record.id,
                "personnel": record.personnel.name_with_rank,
                "date": record.date.strftime("%Y-%m-%d"),
                "time_in": (
                    record.time_in.strftime("%H:%M:%S") if record.time_in else ""
                ),
                "time_out": (
                    record.time_out.strftime("%H:%M:%S") if record.time_out else ""
                ),
                "status": record.status.value if record.status else "",
                "work_hours": (
                    f"{record.work_hours:.2f}" if record.work_hours > 0 else ""
                ),
                "station": record.personnel.station.station_name,
                "actions": f"""
                <a href="{url_for('attendance.edit', attendance_id=record.id)}" class="btn btn-sm btn-warning">
                    <i class="fas fa-edit"></i> Edit
                </a>
                <form method="POST" action="{url_for('attendance.delete', attendance_id=record.id)}" style="display: inline-block;" onsubmit="return confirm('Are you sure you want to delete this attendance record?')">
                    <button type="submit" class="btn btn-sm btn-danger btn-delete-custom">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                </form>
            """,
            }
        )

    return jsonify(
        {
            "draw": draw,
            "recordsTotal": total_records,
            "recordsFiltered": total_records,
            "data": data,
        }
    )
