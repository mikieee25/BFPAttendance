# Personnel management routes for BFP Sorsogon Attendance System
# Handles CRUD operations for personnel records and face registration

# Flask framework imports
from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    flash,
)
from flask_login import login_required, current_user

# File handling and utilities
from datetime import datetime

# Database models
from models import db, Personnel, User, FaceData, ActivityLog

# Face recognition service
from face_rec_module.face_service import register_face

personnel_bp = Blueprint("personnel", __name__)


@personnel_bp.route("/")
@login_required
def index():
    """Display personnel list with station-based access control.

    Admins can see all personnel across stations.
    Station users see only personnel from their assigned station.
    Only shows active personnel by default.
    """
    # Get show_inactive parameter
    show_inactive = request.args.get("show_inactive", "false") == "true"

    # Get personnel based on user role and station access
    if current_user.is_admin:
        query = Personnel.query
    else:
        query = Personnel.query.filter_by(station_id=current_user.id)

    # Filter by active status unless show_inactive is True
    if not show_inactive:
        query = query.filter_by(is_active=True)

    personnel = query.all()

    # Get all stations for the dropdown (admin only)
    stations = User.query.all() if current_user.is_admin else [current_user]

    return render_template(
        "personnel/index.html",
        personnel=personnel,
        stations=stations,
        show_inactive=show_inactive,
    )


@personnel_bp.route("/register", methods=["GET", "POST"])
@login_required
def register():
    """Personnel registration route - legacy redirect to add functionality.

    This route exists for backwards compatibility and redirects to the add route.
    """
    if request.method == "POST":
        # Handle POST requests through the add route logic
        return add()

    # Get available stations for dropdown (filtered by user permissions)
    if current_user.is_admin:
        stations = User.query.all()  # Admin can assign to any station
    else:
        stations = [current_user]  # Station users can only assign to their station

    return render_template("auth/register.html", stations=stations)


@personnel_bp.route("/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "POST":
        try:
            # Get data from form (works for both FormData and regular form submissions)
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            rank = request.form.get("rank", "").strip()
            station_id = request.form.get("station_id", "").strip()

            # Validation
            if not all([first_name, last_name, rank, station_id]):
                # Check if AJAX request (XMLHttpRequest header)
                if (
                    request.headers.get("X-Requested-With") == "XMLHttpRequest"
                    or request.accept_mimetypes.accept_json
                ):
                    return jsonify(
                        {
                            "success": False,
                            "error": "Please fill in all required fields (First Name, Last Name, Rank, Station)",
                        }
                    )
                flash("Please fill in all required fields", "error")
                return redirect(url_for("personnel.add"))

            # Convert station_id to integer
            try:
                station_id = int(station_id)
            except ValueError:
                if (
                    request.headers.get("X-Requested-With") == "XMLHttpRequest"
                    or request.accept_mimetypes.accept_json
                ):
                    return jsonify(
                        {"success": False, "error": "Invalid station selection"}
                    )
                flash("Invalid station selection", "error")
                return redirect(url_for("personnel.add"))

            # Validate station access
            if not current_user.is_admin and station_id != current_user.id:
                if (
                    request.headers.get("X-Requested-With") == "XMLHttpRequest"
                    or request.accept_mimetypes.accept_json
                ):
                    return jsonify(
                        {
                            "success": False,
                            "error": "You can only add personnel to your own station",
                        }
                    )
                flash("You can only add personnel to your own station", "error")
                return redirect(url_for("personnel.index"))

            # Get shift-related fields
            shift_start_time = request.form.get("shift_start_time", "").strip()
            shift_end_time = request.form.get("shift_end_time", "").strip()
            is_shifting = request.form.get("is_shifting") == "on"
            shift_start_date = request.form.get("shift_start_date", "").strip()
            shift_duration_days = request.form.get("shift_duration_days", "").strip()

            # Parse time values
            parsed_shift_start = None
            parsed_shift_end = None
            parsed_shift_date = None
            parsed_duration = 15  # Default to 15 days

            if shift_start_time:
                from datetime import time

                hours, minutes = map(int, shift_start_time.split(":"))
                parsed_shift_start = time(hours, minutes)

            if shift_end_time:
                from datetime import time

                hours, minutes = map(int, shift_end_time.split(":"))
                parsed_shift_end = time(hours, minutes)

            if shift_start_date and is_shifting:
                parsed_shift_date = datetime.strptime(
                    shift_start_date, "%Y-%m-%d"
                ).date()

            if shift_duration_days and is_shifting:
                try:
                    parsed_duration = int(shift_duration_days)
                    # Ensure reasonable bounds
                    parsed_duration = max(1, min(60, parsed_duration))
                except ValueError:
                    parsed_duration = 15

            # Create new personnel
            new_personnel = Personnel(
                first_name=first_name,
                last_name=last_name,
                rank=rank,
                station_id=station_id,
                shift_start_time=parsed_shift_start,
                shift_end_time=parsed_shift_end,
                is_shifting=is_shifting,
                shift_start_date=parsed_shift_date,
                shift_duration_days=parsed_duration if is_shifting else None,
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

            # Check if AJAX request
            if (
                request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or request.accept_mimetypes.accept_json
            ):
                return jsonify(
                    {
                        "success": True,
                        "message": "Personnel registered successfully",
                        "personnel_id": new_personnel.id,
                    }
                )

            flash("Personnel added successfully", "success")
            return redirect(url_for("personnel.index"))

        except Exception as e:
            db.session.rollback()
            # Check if AJAX request
            if (
                request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or request.accept_mimetypes.accept_json
            ):
                return jsonify({"success": False, "error": str(e)})
            flash(f"Error adding personnel: {str(e)}", "error")
            return redirect(url_for("personnel.add"))

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

        # Update shift-related fields
        shift_start_time = request.form.get("shift_start_time", "").strip()
        shift_end_time = request.form.get("shift_end_time", "").strip()
        is_shifting = request.form.get("is_shifting") == "on"
        shift_start_date = request.form.get("shift_start_date", "").strip()
        shift_duration_days = request.form.get("shift_duration_days", "").strip()

        # Parse time values
        if shift_start_time:
            from datetime import time

            hours, minutes = map(int, shift_start_time.split(":"))
            personnel.shift_start_time = time(hours, minutes)
        else:
            personnel.shift_start_time = None

        if shift_end_time:
            from datetime import time

            hours, minutes = map(int, shift_end_time.split(":"))
            personnel.shift_end_time = time(hours, minutes)
        else:
            personnel.shift_end_time = None

        personnel.is_shifting = is_shifting

        if shift_start_date and is_shifting:
            personnel.shift_start_date = datetime.strptime(
                shift_start_date, "%Y-%m-%d"
            ).date()
        elif not is_shifting:
            personnel.shift_start_date = None

        # Handle shift duration
        if shift_duration_days and is_shifting:
            try:
                duration = int(shift_duration_days)
                personnel.shift_duration_days = max(1, min(60, duration))
            except ValueError:
                personnel.shift_duration_days = 15
        elif not is_shifting:
            personnel.shift_duration_days = None

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


@personnel_bp.route("/archive/<int:personnel_id>", methods=["POST"])
@login_required
def archive(personnel_id):
    """Archive a personnel record (soft delete).

    Personnel records are never truly deleted to maintain attendance history.
    Instead, they are marked as inactive.
    """
    personnel = Personnel.query.get_or_404(personnel_id)

    # Check access
    if not current_user.is_admin and personnel.station_id != current_user.id:
        flash("You can only archive personnel from your own station", "error")
        return redirect(url_for("personnel.index"))

    try:
        name = personnel.full_name
        station_name = personnel.station.station_name

        # Mark as inactive instead of deleting
        personnel.is_active = False

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="Personnel Archived",
            description=f"Personnel {name} archived from {station_name}",
        )
        db.session.add(activity)
        db.session.commit()

        flash(
            f"Personnel {name} archived successfully. Their records are preserved.",
            "success",
        )
        return redirect(url_for("personnel.index"))

    except Exception as e:
        db.session.rollback()
        flash(f"Error archiving personnel: {str(e)}", "error")
        return redirect(url_for("personnel.index"))


@personnel_bp.route("/restore/<int:personnel_id>", methods=["POST"])
@login_required
def restore(personnel_id):
    """Restore an archived personnel record."""
    personnel = Personnel.query.get_or_404(personnel_id)

    # Check access
    if not current_user.is_admin and personnel.station_id != current_user.id:
        flash("You can only restore personnel from your own station", "error")
        return redirect(url_for("personnel.index"))

    try:
        name = personnel.full_name
        station_name = personnel.station.station_name

        # Mark as active
        personnel.is_active = True

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="Personnel Restored",
            description=f"Personnel {name} restored to {station_name}",
        )
        db.session.add(activity)
        db.session.commit()

        flash(f"Personnel {name} restored successfully.", "success")
        return redirect(url_for("personnel.index"))

    except Exception as e:
        db.session.rollback()
        flash(f"Error restoring personnel: {str(e)}", "error")
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
        images = []

        # Check if request contains JSON data (base64 images)
        if request.is_json:
            data = request.get_json()
            images = data.get("images", [])
        # Check if request contains FormData with image file
        elif "image" in request.files:
            import base64
            
            # Get the uploaded file
            image_file = request.files["image"]

            # Read the image data
            image_data = image_file.read()

            # Convert to base64
            base64_image = base64.b64encode(image_data).decode("utf-8")
            images = [base64_image]
        else:
            return jsonify({"success": False, "error": "No images provided"}), 400

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
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@personnel_bp.route("/api/data")
@login_required
def api_data():
    """DataTables API endpoint"""
    # Get show_inactive parameter
    show_inactive = request.args.get("show_inactive", "false") == "true"

    # Get personnel based on user role
    if current_user.is_admin:
        query = Personnel.query
    else:
        query = Personnel.query.filter_by(station_id=current_user.id)

    # Filter by active status unless show_inactive is True
    if not show_inactive:
        query = query.filter_by(is_active=True)

    personnel = query.all()

    data = []
    for p in personnel:
        face_count = FaceData.query.filter_by(personnel_id=p.id).count()

        # Build status badge
        status_badge = (
            '<span class="badge bg-success">Active</span>'
            if p.is_active
            else '<span class="badge bg-secondary">Archived</span>'
        )

        # Build shift info
        shift_info = ""
        if p.is_shifting:
            on_duty = p.is_on_duty()
            shift_info = '<span class="badge bg-info">Shifting</span> '
            shift_info += (
                '<span class="badge bg-success">On Duty</span>'
                if on_duty
                else '<span class="badge bg-warning">Off Duty</span>'
            )
        elif p.shift_start_time and p.shift_end_time:
            shift_info = f'{p.shift_start_time.strftime("%H:%M")} - {p.shift_end_time.strftime("%H:%M")}'

        # Build action buttons based on active status
        if p.is_active:
            action_buttons = f"""
                <a href="{url_for('personnel.view', personnel_id=p.id)}" class="btn btn-sm btn-info">
                    <i class="fas fa-eye"></i> View
                </a>
                <a href="{url_for('personnel.edit', personnel_id=p.id)}" class="btn btn-sm btn-warning">
                    <i class="fas fa-edit"></i> Edit
                </a>
                <a href="{url_for('personnel.register_face_page', personnel_id=p.id)}" class="btn btn-sm btn-camera">
                    <i class="fas fa-camera"></i> Face
                </a>
                <form method="POST" action="{url_for('personnel.archive', personnel_id=p.id)}" style="display: inline-block;" onsubmit="return confirm('Are you sure you want to archive this personnel? Their records will be preserved.')">
                    <button type="submit" class="btn btn-sm btn-secondary">
                        <i class="fas fa-archive"></i> Archive
                    </button>
                </form>
            """
        else:
            action_buttons = f"""
                <a href="{url_for('personnel.view', personnel_id=p.id)}" class="btn btn-sm btn-info">
                    <i class="fas fa-eye"></i> View
                </a>
                <form method="POST" action="{url_for('personnel.restore', personnel_id=p.id)}" style="display: inline-block;" onsubmit="return confirm('Are you sure you want to restore this personnel?')">
                    <button type="submit" class="btn btn-sm btn-success">
                        <i class="fas fa-undo"></i> Restore
                    </button>
                </form>
            """

        data.append(
            {
                "id": p.id,
                "full_name": p.full_name,
                "rank": p.rank,
                "station": p.station.station_name,
                "status": status_badge,
                "shift_info": shift_info,
                "face_count": face_count,
                "date_created": (
                    p.date_created.strftime("%Y-%m-%d %H:%M:%S")
                    if p.date_created
                    else ""
                ),
                "actions": action_buttons,
            }
        )

    return jsonify({"data": data})
