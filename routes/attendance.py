# Attendance management routes for BFP Sorsogon Attendance System
# Handles attendance viewing, face recognition capture, manual entry, and CRUD operations

# Flask framework imports
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user

# Date/time utilities and database queries
from datetime import datetime, date, timedelta
from sqlalchemy import func, desc, and_, or_
import os
import logging

# Database models
from models import db, Personnel, Attendance, User, AttendanceStatus, ActivityLog

# Set up logger
logger = logging.getLogger(__name__)

# Face recognition service functions
from face_rec_module.face_service import (
    process_base64_image,
    recognize_face,
    load_face_database,
    process_attendance,
)

attendance_bp = Blueprint("attendance", __name__)


@attendance_bp.route("/")
@login_required
def index():
    """Display attendance records with filtering options.

    Shows attendance records based on user permissions:
    - Admins can see all stations
    - Station users see only their station's records

    Supports filtering by date range, personnel, and status.
    """
    # Get filter parameters from query string
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

    # Build base query with station access control
    if current_user.is_admin:
        attendance_query = Attendance.query.join(Personnel)  # Admin sees all stations
        personnel_list = Personnel.query.all()
    else:
        # Station users see only their own station's personnel
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
    """Display the face recognition attendance capture interface.

    Provides camera interface for biometric attendance recording.
    """
    return render_template("attendance/capture.html")


@attendance_bp.route("/api/capture", methods=["POST"])
@login_required
def api_capture():
    """API endpoint for processing face recognition attendance capture.

    Processes base64 image data, performs face recognition with liveness detection,
    and records attendance if person is identified and passes liveness check.

    Returns JSON response with success status and attendance details.
    """
    try:
        data = request.get_json()
        image_data = data.get("image")

        if not image_data:
            return jsonify({"success": False, "error": "No image provided"}), 400

        # Process the image and extract face with liveness detection
        face_embedding, face_metadata, temp_path = process_base64_image(
            image_data, enable_liveness=True
        )

        # Log detailed liveness results
        if face_metadata:
            liveness_failed = face_metadata.get("liveness_failed", False)
            liveness_details = face_metadata.get("liveness_details", {})
            logger.info(
                f"Attendance capture - Liveness check: {'FAILED' if liveness_failed else 'PASSED'}"
            )
            logger.info(f"  Liveness details: {liveness_details}")

        # Check if liveness detection failed
        if face_metadata and face_metadata.get("liveness_failed"):
            liveness_details = face_metadata.get("liveness_details", {})
            logger.warning(
                f"❌ LIVENESS DETECTION FAILED - Possible spoofing attempt detected!"
            )
            logger.warning(f"Liveness details: {liveness_details}")
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Liveness detection failed. Please use a live camera feed, not a photo or video.",
                        "liveness_details": liveness_details,
                    }
                ),
                400,
            )

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
        from app import app

        threshold = app.config.get("FACE_RECOGNITION_THRESHOLD", 0.6)
        app.logger.info(f"Attempting face recognition with threshold: {threshold}")
        app.logger.info(f"Database has {len(face_database)} registered personnel")

        recognized_id, confidence = recognize_face(
            face_embedding, face_database, threshold
        )

        if recognized_id is None:
            app.logger.warning(
                f"Face not recognized. No match found above threshold {threshold}"
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Face not recognized. Please ensure you are registered in the system.",
                    }
                ),
                400,
            )

        # Log successful recognition
        personnel = Personnel.query.get(recognized_id)
        app.logger.info(
            f"✓ Face recognized: {personnel.full_name} (ID: {recognized_id}, Confidence: {confidence:.3f})"
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
                description=f"Attendance captured for {personnel.full_name} via face recognition (liveness verified)",
            )
            db.session.add(activity)
            db.session.commit()

        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@attendance_bp.route("/manual", methods=["GET", "POST"])
@login_required
def manual():
    """Handle manual attendance entry when face recognition is not available.

    Allows authorized users to manually record attendance with time entries.
    Validates personnel access based on station permissions.
    """
    if request.method == "POST":
        personnel_id = request.form["personnel_id"]
        attendance_date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        time_in = request.form.get("time_in")
        time_out = request.form.get("time_out")
        status = AttendanceStatus(request.form["status"])
        notes = request.form.get("notes", "")

        # Validate user has permission to add attendance for this personnel
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

    # Get personnel list for form dropdown (filtered by station access)
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
    """Edit existing attendance record.

    Allows modification of attendance status and time entries.
    Access controlled by station permissions.
    """
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
    """Delete an attendance record.

    Removes attendance record with proper access control and activity logging.
    """
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
    """DataTables API endpoint for attendance table data.

    Provides paginated, searchable attendance data for DataTables frontend.
    Respects user station permissions for data filtering.
    """
    # Get DataTables query parameters
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
