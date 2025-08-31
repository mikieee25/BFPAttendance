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
from datetime import datetime
import os

from models import (
    db,
    PendingAttendance,
    Personnel,
    Attendance,
    ActivityLog,
    AttendanceStatus,
)

pending_bp = Blueprint("pending", __name__)


@pending_bp.route("/")
@login_required
def index():
    if not current_user.is_admin:
        flash("Access denied. Only administrators can view pending approvals.", "error")
        return redirect(url_for("dashboard.index"))

    # Get all pending attendance requests
    pending_requests = (
        PendingAttendance.query.join(Personnel)
        .order_by(PendingAttendance.date_created.desc())
        .all()
    )

    return render_template("pending/index.html", pending_requests=pending_requests)


@pending_bp.route("/approve/<int:request_id>", methods=["POST"])
@login_required
def approve(request_id):
    if not current_user.is_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    try:
        pending_request = PendingAttendance.query.get_or_404(request_id)

        # Check if attendance already exists for this date
        existing_attendance = Attendance.query.filter_by(
            personnel_id=pending_request.personnel_id, date=pending_request.date
        ).first()

        if existing_attendance:
            # Update existing attendance
            if pending_request.attendance_type == "TIME_IN":
                if existing_attendance.time_in:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "Time-in already recorded for this date",
                            }
                        ),
                        400,
                    )
                existing_attendance.time_in = datetime.now()
                existing_attendance.time_in_image = pending_request.image_path
            else:  # TIME_OUT
                if existing_attendance.time_out:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "Time-out already recorded for this date",
                            }
                        ),
                        400,
                    )
                existing_attendance.time_out = datetime.now()
                existing_attendance.time_out_image = pending_request.image_path

            existing_attendance.is_approved = True
            existing_attendance.approved_by = current_user.id
        else:
            # Create new attendance record
            new_attendance = Attendance(
                personnel_id=pending_request.personnel_id,
                date=pending_request.date,
                status=AttendanceStatus.PRESENT,  # Default status
                is_auto_captured=False,
                is_approved=True,
                approved_by=current_user.id,
            )

            if pending_request.attendance_type == "TIME_IN":
                new_attendance.time_in = datetime.now()
                new_attendance.time_in_image = pending_request.image_path
            else:  # TIME_OUT
                new_attendance.time_out = datetime.now()
                new_attendance.time_out_image = pending_request.image_path

            db.session.add(new_attendance)

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="Attendance Approved",
            description=f"Approved {pending_request.attendance_type.lower()} for {pending_request.personnel.full_name} on {pending_request.date}",
        )
        db.session.add(activity)

        # Remove pending request
        db.session.delete(pending_request)
        db.session.commit()

        return jsonify({"success": True, "message": "Attendance approved successfully"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@pending_bp.route("/reject/<int:request_id>", methods=["POST"])
@login_required
def reject(request_id):
    if not current_user.is_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    try:
        data = request.get_json()
        reason = data.get("reason", "No reason provided")

        pending_request = PendingAttendance.query.get_or_404(request_id)

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="Attendance Rejected",
            description=f"Rejected {pending_request.attendance_type.lower()} for {pending_request.personnel.full_name} on {pending_request.date}. Reason: {reason}",
        )
        db.session.add(activity)

        # Remove the image file if it exists
        if pending_request.image_path:
            image_full_path = os.path.join(
                current_app.static_folder, pending_request.image_path
            )
            if os.path.exists(image_full_path):
                os.remove(image_full_path)

        # Remove pending request
        db.session.delete(pending_request)
        db.session.commit()

        return jsonify({"success": True, "message": "Attendance request rejected"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@pending_bp.route("/submit", methods=["GET", "POST"])
@login_required
def submit():
    if request.method == "POST":
        try:
            data = request.get_json()
            personnel_id = data.get("personnel_id")
            attendance_type = data.get("attendance_type")
            image_data = data.get("image")
            notes = data.get("notes", "")

            # Validate personnel access
            personnel = Personnel.query.get_or_404(personnel_id)
            if not current_user.is_admin and personnel.station_id != current_user.id:
                return jsonify({"success": False, "error": "Access denied"}), 403

            # Save the image
            from face_recognition.face_service import save_attendance_image

            image_path = save_attendance_image(
                personnel_id, image_data, f"pending_{attendance_type.lower()}"
            )

            if not image_path:
                return jsonify({"success": False, "error": "Failed to save image"}), 500

            # Create pending request
            pending_request = PendingAttendance(
                personnel_id=personnel_id,
                date=datetime.now().date(),
                attendance_type=attendance_type,
                image_path=image_path,
                notes=notes,
            )

            db.session.add(pending_request)

            # Log activity
            activity = ActivityLog(
                user_id=current_user.id,
                title="Pending Attendance Submitted",
                description=f"Submitted {attendance_type.lower()} request for {personnel.full_name}",
            )
            db.session.add(activity)
            db.session.commit()

            return jsonify(
                {
                    "success": True,
                    "message": "Attendance request submitted for approval",
                }
            )

        except Exception as e:
            db.session.rollback()
            return jsonify({"success": False, "error": str(e)}), 500

    # GET request - show form
    if current_user.is_admin:
        personnel_list = Personnel.query.all()
    else:
        personnel_list = Personnel.query.filter_by(station_id=current_user.id).all()

    return render_template("pending/submit.html", personnel_list=personnel_list)


@pending_bp.route("/api/data")
@login_required
def api_data():
    """DataTables API endpoint for pending requests"""
    if not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403

    pending_requests = (
        PendingAttendance.query.join(Personnel)
        .order_by(PendingAttendance.date_created.desc())
        .all()
    )

    data = []
    for request in pending_requests:
        data.append(
            {
                "id": request.id,
                "personnel": request.personnel.name_with_rank,
                "station": request.personnel.station.station_name,
                "date": request.date.strftime("%Y-%m-%d"),
                "type": request.attendance_type.replace("_", " ").title(),
                "notes": request.notes or "",
                "submitted": request.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                "image": f'<img src="/static/{request.image_path}" alt="Attendance Image" style="max-width: 100px; max-height: 100px; cursor: pointer;" onclick="showImageModal(this.src)">',
                "actions": f"""
                <button class="btn btn-sm btn-success" onclick="approveRequest({request.id})">
                    <i class="fas fa-check"></i> Approve
                </button>
                <button class="btn btn-sm btn-danger" onclick="rejectRequest({request.id})">
                    <i class="fas fa-times"></i> Reject
                </button>
            """,
            }
        )

    return jsonify({"data": data})
