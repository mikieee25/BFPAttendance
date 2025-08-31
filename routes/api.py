from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime
import os

from models import db, Personnel, Attendance, User
from face_recognition.face_service import (
    process_base64_image,
    recognize_face,
    load_face_database,
    process_attendance,
    register_face,
)

api_bp = Blueprint("api", __name__)


@api_bp.route("/personnel")
@login_required
def get_personnel():
    """Get personnel list for current user's station"""
    if current_user.is_admin:
        personnel = Personnel.query.all()
    else:
        personnel = Personnel.query.filter_by(station_id=current_user.id).all()

    data = []
    for p in personnel:
        data.append(
            {
                "id": p.id,
                "full_name": p.full_name,
                "rank": p.rank,
                "station": p.station.station_name,
                "image_path": p.image_path,
            }
        )

    return jsonify({"personnel": data})


@api_bp.route("/attendance/capture", methods=["POST"])
@login_required
def capture_attendance():
    """API endpoint for capturing attendance via face recognition"""
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

        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/face/register/<int:personnel_id>", methods=["POST"])
@login_required
def register_personnel_face(personnel_id):
    """API endpoint for registering personnel face data"""
    try:
        personnel = Personnel.query.get_or_404(personnel_id)

        # Check access
        if not current_user.is_admin and personnel.station_id != current_user.id:
            return jsonify({"success": False, "error": "Access denied"}), 403

        data = request.get_json()
        images = data.get("images", [])

        if not images:
            return jsonify({"success": False, "error": "No images provided"}), 400

        # Register faces
        result = register_face(personnel_id, images)
        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/stats/dashboard")
@login_required
def dashboard_stats():
    """Get real-time dashboard statistics"""
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
        [a for a in today_attendance if a.status in ["PRESENT", "LATE"]]
    )
    absent_today = total_personnel - present_today
    late_today = len([a for a in today_attendance if a.status == "LATE"])

    return jsonify(
        {
            "total_personnel": total_personnel,
            "present_today": present_today,
            "absent_today": absent_today,
            "late_today": late_today,
            "attendance_rate": (
                (present_today / total_personnel * 100) if total_personnel > 0 else 0
            ),
        }
    )


@api_bp.route("/time")
@login_required
def get_current_time():
    """Get current time for dashboard clock"""
    current_time = datetime.now()
    return jsonify(
        {
            "time": current_time.strftime("%H:%M:%S"),
            "date": current_time.strftime("%A, %B %d, %Y"),
            "timestamp": current_time.isoformat(),
        }
    )


@api_bp.route("/personnel/<int:personnel_id>/attendance")
@login_required
def get_personnel_attendance(personnel_id):
    """Get attendance history for a specific personnel"""
    personnel = Personnel.query.get_or_404(personnel_id)

    # Check access
    if not current_user.is_admin and personnel.station_id != current_user.id:
        return jsonify({"error": "Access denied"}), 403

    attendance_records = (
        Attendance.query.filter_by(personnel_id=personnel_id)
        .order_by(Attendance.date.desc())
        .limit(30)
        .all()
    )

    data = []
    for record in attendance_records:
        data.append(
            {
                "date": record.date.strftime("%Y-%m-%d"),
                "time_in": (
                    record.time_in.strftime("%H:%M:%S") if record.time_in else None
                ),
                "time_out": (
                    record.time_out.strftime("%H:%M:%S") if record.time_out else None
                ),
                "status": record.status.value if record.status else None,
                "work_hours": record.work_hours,
            }
        )

    return jsonify({"attendance": data})


@api_bp.route("/health")
def health_check():
    """Health check endpoint"""
    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
        }
    )
