from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
import json
from datetime import datetime

from models import db, Personnel, User, FaceData, ActivityLog, StationType
from face_recognition.face_service import register_face

personnel_bp = Blueprint("personnel", __name__)


@personnel_bp.route("/")
@login_required
def index():
    # Get personnel based on user role
    if current_user.is_admin:
        personnel = Personnel.query.all()
    else:
        personnel = Personnel.query.filter_by(station_id=current_user.id).all()

    # Get all stations for the dropdown (admin only)
    stations = User.query.all() if current_user.is_admin else [current_user]

    return render_template(
        "personnel/index.html", personnel=personnel, stations=stations
    )


@personnel_bp.route("/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "POST":
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]
        rank = request.form["rank"]
        station_id = int(request.form["station_id"])

        # Validate station access
        if not current_user.is_admin and station_id != current_user.id:
            flash("You can only add personnel to your own station", "error")
            return redirect(url_for("personnel.index"))

        # Create new personnel
        new_personnel = Personnel(
            first_name=first_name, last_name=last_name, rank=rank, station_id=station_id
        )

        db.session.add(new_personnel)
        db.session.flush()  # Get the ID

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="Personnel Added",
            description=f"Personnel {new_personnel.full_name} added to {new_personnel.station.station_name}",
        )
        db.session.add(activity)
        db.session.commit()

        flash("Personnel added successfully", "success")
        return redirect(url_for("personnel.index"))

    # Get stations for dropdown
    if current_user.is_admin:
        stations = User.query.all()
    else:
        stations = [current_user]

    return render_template("personnel/add.html", stations=stations)


@personnel_bp.route("/edit/<int:personnel_id>", methods=["GET", "POST"])
@login_required
def edit(personnel_id):
    personnel = Personnel.query.get_or_404(personnel_id)

    # Check access
    if not current_user.is_admin and personnel.station_id != current_user.id:
        flash("You can only edit personnel from your own station", "error")
        return redirect(url_for("personnel.index"))

    if request.method == "POST":
        personnel.first_name = request.form["first_name"]
        personnel.last_name = request.form["last_name"]
        personnel.rank = request.form["rank"]

        # Only admin can change station
        if current_user.is_admin:
            personnel.station_id = int(request.form["station_id"])

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="Personnel Updated",
            description=f"Personnel {personnel.full_name} information updated",
        )
        db.session.add(activity)
        db.session.commit()

        flash("Personnel updated successfully", "success")
        return redirect(url_for("personnel.index"))

    # Get stations for dropdown
    if current_user.is_admin:
        stations = User.query.all()
    else:
        stations = [current_user]

    return render_template(
        "personnel/edit.html", personnel=personnel, stations=stations
    )


@personnel_bp.route("/delete/<int:personnel_id>", methods=["POST"])
@login_required
def delete(personnel_id):
    personnel = Personnel.query.get_or_404(personnel_id)

    # Check access
    if not current_user.is_admin and personnel.station_id != current_user.id:
        flash("You can only delete personnel from your own station", "error")
        return redirect(url_for("personnel.index"))

    name = personnel.full_name

    # Log activity before deletion
    activity = ActivityLog(
        user_id=current_user.id,
        title="Personnel Deleted",
        description=f"Personnel {name} deleted from {personnel.station.station_name}",
    )
    db.session.add(activity)

    db.session.delete(personnel)
    db.session.commit()

    flash(f"Personnel {name} deleted successfully", "success")
    return redirect(url_for("personnel.index"))


@personnel_bp.route("/view/<int:personnel_id>")
@login_required
def view(personnel_id):
    personnel = Personnel.query.get_or_404(personnel_id)

    # Check access
    if not current_user.is_admin and personnel.station_id != current_user.id:
        flash("You can only view personnel from your own station", "error")
        return redirect(url_for("personnel.index"))

    # Get face data count
    face_count = FaceData.query.filter_by(personnel_id=personnel_id).count()

    # Get recent attendance
    recent_attendance = personnel.attendances[-10:] if personnel.attendances else []

    return render_template(
        "personnel/view.html",
        personnel=personnel,
        face_count=face_count,
        recent_attendance=recent_attendance,
    )


@personnel_bp.route("/register-face/<int:personnel_id>")
@login_required
def register_face_page(personnel_id):
    personnel = Personnel.query.get_or_404(personnel_id)

    # Check access
    if not current_user.is_admin and personnel.station_id != current_user.id:
        flash(
            "You can only register faces for personnel from your own station", "error"
        )
        return redirect(url_for("personnel.index"))

    return render_template("personnel/register_face.html", personnel=personnel)


@personnel_bp.route("/api/register-face/<int:personnel_id>", methods=["POST"])
@login_required
def api_register_face(personnel_id):
    personnel = Personnel.query.get_or_404(personnel_id)

    # Check access
    if not current_user.is_admin and personnel.station_id != current_user.id:
        return jsonify({"success": False, "error": "Access denied"}), 403

    try:
        data = request.get_json()
        images = data.get("images", [])

        if not images:
            return jsonify({"success": False, "error": "No images provided"}), 400

        # Register faces using the face service
        result = register_face(personnel_id, images)

        if result["success"]:
            # Log activity
            activity = ActivityLog(
                user_id=current_user.id,
                title="Face Registration",
                description=f"Face data registered for {personnel.full_name}",
            )
            db.session.add(activity)
            db.session.commit()

        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@personnel_bp.route("/api/data")
@login_required
def api_data():
    """DataTables API endpoint"""
    # Get personnel based on user role
    if current_user.is_admin:
        personnel = Personnel.query.all()
    else:
        personnel = Personnel.query.filter_by(station_id=current_user.id).all()

    data = []
    for p in personnel:
        face_count = FaceData.query.filter_by(personnel_id=p.id).count()
        data.append(
            {
                "id": p.id,
                "full_name": p.full_name,
                "rank": p.rank,
                "station": p.station.station_name,
                "face_count": face_count,
                "date_created": (
                    p.date_created.strftime("%Y-%m-%d %H:%M:%S")
                    if p.date_created
                    else ""
                ),
                "actions": f"""
                <a href="{url_for('personnel.view', personnel_id=p.id)}" class="btn btn-sm btn-info">
                    <i class="fas fa-eye"></i> View
                </a>
                <a href="{url_for('personnel.edit', personnel_id=p.id)}" class="btn btn-sm btn-warning">
                    <i class="fas fa-edit"></i> Edit
                </a>
                <a href="{url_for('personnel.register_face_page', personnel_id=p.id)}" class="btn btn-sm btn-camera">
                    <i class="fas fa-camera"></i> Face
                </a>
                <form method="POST" action="{url_for('personnel.delete', personnel_id=p.id)}" style="display: inline-block;" onsubmit="return confirm('Are you sure you want to delete this personnel?')">
                    <button type="submit" class="btn btn-sm btn-danger btn-delete-custom">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                </form>
            """,
            }
        )

    return jsonify({"data": data})
