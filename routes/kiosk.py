# Kiosk routes for BFP Sorsogon Attendance System
# Provides an attendance-only interface for dedicated kiosk devices.
# Kiosk accounts (is_kiosk=True) are redirected here after login and have
# no access to any other panel.

import logging
import os
from datetime import datetime

from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import desc

from models import (
    ActivityLog,
    Attendance,
    AttendanceStatus,
    Personnel,
    db,
)
from utils import handle_api_exception

logger = logging.getLogger(__name__)

kiosk_bp = Blueprint("kiosk", __name__)


def _kiosk_required(f):
    """Decorator that allows both kiosk accounts AND regular authenticated users.

    Kiosk accounts are restricted to only kiosk routes (enforced in app.before_request).
    Regular admin/station users can also visit the kiosk for testing purposes.
    """
    from functools import wraps

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return wrapper


@kiosk_bp.route("/")
@_kiosk_required
def index():
    """Main kiosk view — shows Time In / Time Out buttons and recent attendance."""
    today = datetime.now().date()

    # Load personnel for manual entry dropdown
    if current_user.is_admin:
        personnel_list = Personnel.query.filter_by(is_active=True).all()
        attendance_query = Attendance.query.join(Personnel)
    else:
        personnel_list = Personnel.query.filter_by(
            station_id=current_user.id, is_active=True
        ).all()
        attendance_query = Attendance.query.join(Personnel).filter(
            Personnel.station_id == current_user.id
        )

    # Today's most recent attendance records (last 20)
    recent_attendance = (
        attendance_query.filter(Attendance.date == today)
        .order_by(desc(Attendance.date_created))
        .limit(20)
        .all()
    )

    return render_template(
        "kiosk/index.html",
        recent_attendance=recent_attendance,
        personnel_list=personnel_list,
        today=today,
    )


@kiosk_bp.route("/manual-entry", methods=["POST"])
@_kiosk_required
def manual_entry():
    """JSON endpoint: create a manual attendance record from the kiosk manual form."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        personnel_id = data.get("personnel_id")
        attendance_type = data.get("attendance_type")  # TIME_IN | TIME_OUT
        status_value = data.get("status")
        reason = data.get("reason", "")
        notes = data.get("notes", "")
        selfie_data = data.get("selfie_data")  # base64 image, optional

        # ── Validation ──────────────────────────────────────────────────────
        if not personnel_id or not attendance_type or not status_value:
            return (
                jsonify({"success": False, "error": "Missing required fields"}),
                400,
            )

        try:
            status = AttendanceStatus(status_value)
        except ValueError:
            return jsonify({"success": False, "error": f"Invalid status: {status_value}"}), 400

        # ── Access control ───────────────────────────────────────────────────
        personnel = Personnel.query.get(int(personnel_id))
        if not personnel:
            return jsonify({"success": False, "error": "Personnel not found"}), 404

        if not current_user.is_admin and personnel.station_id != current_user.id:
            return (
                jsonify(
                    {"success": False, "error": "Access denied for this personnel"}
                ),
                403,
            )

        today = datetime.now().date()
        now = datetime.now()

        # ── Selfie save (optional) ────────────────────────────────────────────
        image_path = None
        if selfie_data:
            try:
                import base64
                import uuid

                from flask import current_app

                if "," in selfie_data:
                    selfie_data = selfie_data.split(",")[1]

                img_bytes = base64.b64decode(selfie_data)
                filename = f"kiosk_manual_{uuid.uuid4().hex}.jpg"
                save_folder = current_app.config.get(
                    "TEMP_ATTENDANCE_FOLDER",
                    os.path.join("static", "images", "attendance_temp"),
                )
                os.makedirs(save_folder, exist_ok=True)
                full_path = os.path.join(save_folder, filename)
                with open(full_path, "wb") as f:
                    f.write(img_bytes)
                image_path = os.path.join("images", "attendance_temp", filename)
            except Exception as exc:
                logger.warning("Could not save selfie image: %s", exc)

        # ── Upsert attendance record ─────────────────────────────────────────
        existing = Attendance.query.filter_by(
            personnel_id=personnel.id, date=today
        ).first()

        full_notes = notes
        if reason:
            full_notes = f"[{reason}] {notes}".strip()

        if existing:
            # Update existing record with time_out if TIME_OUT, or update status
            if attendance_type == "TIME_OUT":
                existing.time_out = now
            existing.status = status
            if image_path:
                existing.time_out_image = image_path
            attendance_record = existing
        else:
            attendance_record = Attendance(
                personnel_id=personnel.id,
                date=today,
                status=status,
                is_auto_captured=False,
                is_approved=True,
                approved_by=current_user.id,
            )
            if attendance_type == "TIME_IN":
                attendance_record.time_in = now
                if image_path:
                    attendance_record.time_in_image = image_path
            else:
                attendance_record.time_out = now
                if image_path:
                    attendance_record.time_out_image = image_path
            db.session.add(attendance_record)

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="Kiosk Manual Attendance",
            description=(
                f"Manual kiosk entry for {personnel.full_name} — "
                f"{attendance_type} | {status_value}"
                + (f" | Reason: {reason}" if reason else "")
                + (f" | Notes: {notes}" if notes else "")
            ),
        )
        db.session.add(activity)
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "personnel_name": personnel.name_with_rank,
                "station": personnel.station.station_name,
                "status": status.value,
                "attendance_type": attendance_type,
                "time": now.strftime("%H:%M"),
            }
        )

    except Exception as exc:
        return handle_api_exception(exc)


@kiosk_bp.route("/recent.json")
@_kiosk_required
def recent_json():
    """Return the most recent 20 attendance records for today as JSON (for live refresh)."""
    today = datetime.now().date()

    if current_user.is_admin:
        query = Attendance.query.join(Personnel)
    else:
        query = Attendance.query.join(Personnel).filter(
            Personnel.station_id == current_user.id
        )

    records = (
        query.filter(Attendance.date == today)
        .order_by(desc(Attendance.date_created))
        .limit(20)
        .all()
    )

    data = []
    for rec in records:
        p = rec.personnel
        data.append(
            {
                "id": rec.id,
                "full_name": p.name_with_rank,
                "rank": p.rank,
                "station": p.station.station_name,
                "image_url": url_for(
                    "static",
                    filename=p.image_path if p.image_path else "images/profile-placeholder.jpg",
                ),
                "time_in": rec.time_in.strftime("%H:%M") if rec.time_in else None,
                "time_out": rec.time_out.strftime("%H:%M") if rec.time_out else None,
                "status": rec.status.value if rec.status else None,
            }
        )

    return jsonify({"records": data})
