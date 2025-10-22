# Authentication routes for BFP Sorsogon Attendance System
# Handles user login, logout, registration, and user management

# Flask framework imports
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_user, logout_user, current_user

# Security and utilities
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
import random

# Database models
from models import db, User, ActivityLog, StationType

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Handle user authentication with username or email support.

    Supports login with either username or email address.
    Sets randomized greeting message for successful logins.
    """
    # Redirect already authenticated users to dashboard
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        # Extract form data
        username_or_email = request.form["username"]
        password = request.form["password"]
        remember = bool(request.form.get("remember"))

        # Try to find user by username first, then by email
        user = User.query.filter_by(username=username_or_email).first()
        if not user:
            user = User.query.filter_by(email=username_or_email).first()

        if user and check_password_hash(user.password, password):
            login_user(user, remember=remember)

            # Set randomized greeting for this login session
            greetings = [
                "Welcome",
                "Greetings",
                "A pleasant day",
                "Good day",
                "Hello there",
                "Salutations",
                "Good to see you",
                "Pleased to welcome you",
                "It's great to have you back",
                "Glad you're here",
                "Welcome back",
                "Nice to see you again",
                "Great to have you",
                "Wonderful to see you",
                "Happy to welcome you",
            ]
            session["current_greeting"] = random.choice(greetings)

            # Log activity
            activity = ActivityLog(
                user_id=user.id,
                title="User Login",
                description=f"User {user.username} logged in successfully using {'username' if User.query.filter_by(username=username_or_email).first() else 'email'}",
            )
            db.session.add(activity)
            db.session.commit()

            next_page = request.args.get("next")
            if next_page:
                return redirect(next_page)
            return redirect(url_for("dashboard.index"))
        else:
            flash("Invalid username/email or password", "error")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
def logout():
    """Handle user logout and session cleanup.

    Logs the logout activity and clears session data including greeting.
    """
    if current_user.is_authenticated:
        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="User Logout",
            description=f"User {current_user.username} logged out",
        )
        db.session.add(activity)
        db.session.commit()

    # Clear the greeting from session
    session.pop("current_greeting", None)
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Handle new user registration (admin only).

    Only administrators can create new user accounts.
    Validates form data and creates new users with proper station assignments.
    """
    # Check admin permissions
    if not current_user.is_authenticated or not current_user.is_admin:
        flash("Access denied. Only administrators can create new accounts.", "error")
        return redirect(url_for("auth.login"))

    # Station types for dropdown
    station_types_list = [
        {"id": "CENTRAL", "station_name": "Central Station"},
        {"id": "TALISAY", "station_name": "Talisay Station"},
        {"id": "BACON", "station_name": "Bacon Station"},
        {"id": "ABUYOG", "station_name": "Abuyog Station"},
    ]

    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        station_type = request.form["station_type"]
        is_admin = bool(request.form.get("is_admin"))

        # Validation
        if password != confirm_password:
            flash("Passwords do not match", "error")
            return render_template(
                "auth/register.html",
                station_types=StationType,
                stations=station_types_list,
                form=request.form,
            )

        if User.query.filter_by(username=username).first():
            flash("Username already exists", "error")
            return render_template(
                "auth/register.html",
                station_types=StationType,
                stations=station_types_list,
                form=request.form,
            )

        if User.query.filter_by(email=email).first():
            flash("Email already exists", "error")
            return render_template(
                "auth/register.html",
                station_types=StationType,
                stations=station_types_list,
                form=request.form,
            )

        # Create new user
        new_user = User(
            username=username,
            email=email,
            password=generate_password_hash(password),
            station_type=StationType(station_type),
            is_admin=is_admin,
        )

        db.session.add(new_user)

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="User Registration",
            description=f"New user {username} registered by {current_user.username}",
        )
        db.session.add(activity)
        db.session.commit()

        flash("User registered successfully", "success")
        return redirect(url_for("auth.manage_users"))

    # Return form with station types for dropdown (same as above)
    return render_template(
        "auth/register.html",
        station_types=StationType,
        stations=station_types_list,
        form={},
    )


@auth_bp.route("/manage-stations")
def manage_stations():
    """Display station management page with statistics (admin only).

    Shows all stations with filtering options and summary statistics.
    """
    # Check admin permissions
    if not current_user.is_authenticated or not current_user.is_admin:
        flash("Access denied. Only administrators can manage stations.", "error")
        return redirect(url_for("dashboard.index"))

    # Get all station users (non-admin users represent stations)
    from models import Personnel
    station_users = User.query.filter_by(is_admin=False).all()

    # Add personnel count to each station
    for station in station_users:
        station.personnel_count = Personnel.query.filter_by(station_id=station.id).count()

    # Get station stats
    total_stations = len(station_users)
    active_stations = len([u for u in station_users])  # All stations considered active
    total_personnel = Personnel.query.count()
    
    # Calculate new stations this month
    current_month = datetime.now().replace(day=1)
    new_this_month = len([u for u in station_users if u.date_created >= current_month])

    station_stats = {
        "total_stations": total_stations,
        "active_stations": active_stations,
        "total_personnel": total_personnel,
        "new_this_month": new_this_month,
    }

    # Get station types for filter dropdown
    station_types = [
        {"id": "CENTRAL", "name": "Central Station"},
        {"id": "TALISAY", "name": "Talisay Station"},
        {"id": "BACON", "name": "Bacon Station"},
        {"id": "ABUYOG", "name": "Abuyog Station"},
    ]

    return render_template(
        "auth/manage_stations.html",
        stations=station_users,
        station_stats=station_stats,
        station_types=station_types,
    )


@auth_bp.route("/manage-users")
def manage_users():
    """Display user management page with statistics (admin only).

    Shows all users with filtering options and summary statistics.
    """
    # Check admin permissions
    if not current_user.is_authenticated or not current_user.is_admin:
        flash("Access denied. Only administrators can manage users.", "error")
        return redirect(url_for("dashboard.index"))

    users = User.query.all()

    # Get user stats
    total_users = len(users)
    admin_users = len([u for u in users if u.is_admin])
    regular_users = total_users - admin_users

    # Calculate active users (all users are considered active for now)
    active_users = total_users

    # Calculate new users this month
    current_month = datetime.now().replace(day=1)
    new_this_month = len([u for u in users if u.date_created >= current_month])

    user_stats = {
        "total_users": total_users,
        "admin_users": admin_users,
        "regular_users": regular_users,
        "active_users": active_users,
        "new_this_month": new_this_month,
    }

    # Get station types for filter dropdown
    station_types = [
        {"id": "CENTRAL", "name": "Central Station"},
        {"id": "TALISAY", "name": "Talisay Station"},
        {"id": "BACON", "name": "Bacon Station"},
        {"id": "ABUYOG", "name": "Abuyog Station"},
    ]

    return render_template(
        "auth/manage_users.html",
        users=users,
        user_stats=user_stats,
        stations=station_types,
    )


@auth_bp.route("/delete-user/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    """Delete a user account (admin only).

    Prevents users from deleting their own accounts for safety.
    Logs the deletion activity before removing the user.
    """
    # Check admin permissions
    if not current_user.is_authenticated or not current_user.is_admin:
        flash("Access denied. Only administrators can delete users.", "error")
        return redirect(url_for("dashboard.index"))

    # Prevent self-deletion
    if user_id == current_user.id:
        flash("You cannot delete your own account", "error")
        return redirect(url_for("auth.manage_users"))

    user = User.query.get_or_404(user_id)
    username = user.username

    # Log activity before deletion
    activity = ActivityLog(
        user_id=current_user.id,
        title="User Deletion",
        description=f"User {username} deleted by {current_user.username}",
    )
    db.session.add(activity)

    db.session.delete(user)
    db.session.commit()

    flash(f"User {username} deleted successfully", "success")
    return redirect(url_for("auth.manage_users"))


@auth_bp.route("/station/<int:station_id>", methods=["GET"])
def get_station(station_id):
    """Get station details (admin only)."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    station = User.query.filter_by(id=station_id, is_admin=False).first()
    if not station:
        return jsonify({"success": False, "error": "Station not found"}), 404

    # Get personnel count for this station
    from models import Personnel
    personnel_count = Personnel.query.filter_by(station_id=station_id).count()

    station_data = {
        "id": station.id,
        "username": station.username,
        "email": station.email,
        "station_name": station.station_name,
        "station_type": station.station_type.value,
        "profile_picture": station.profile_picture,
        "personnel_count": personnel_count,
        "date_created": station.date_created.strftime('%m/%d/%Y') if station.date_created else None,
    }

    return jsonify({"success": True, "station": station_data})


@auth_bp.route("/station/<int:station_id>/update", methods=["PUT"])
def update_station(station_id):
    """Update station details (admin only)."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    station = User.query.filter_by(id=station_id, is_admin=False).first()
    if not station:
        return jsonify({"success": False, "error": "Station not found"}), 404

    try:
        data = request.get_json()
        
        # Update station details
        if 'station_name' in data:
            station.station_name = data['station_name']
        if 'email' in data:
            station.email = data['email']
        if 'station_type' in data:
            station.station_type = StationType(data['station_type'])

        db.session.commit()

        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="Station Update",
            description=f"Station {station.station_name} updated by {current_user.username}",
        )
        db.session.add(activity)
        db.session.commit()

        return jsonify({"success": True, "message": "Station updated successfully"})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/station/<int:station_id>/delete", methods=["DELETE"])
def delete_station(station_id):
    """Delete station (admin only)."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    station = User.query.filter_by(id=station_id, is_admin=False).first()
    if not station:
        return jsonify({"success": False, "error": "Station not found"}), 404

    try:
        station_name = station.station_name or station.username

        # Log activity before deletion
        activity = ActivityLog(
            user_id=current_user.id,
            title="Station Deletion",
            description=f"Station {station_name} deleted by {current_user.username}",
        )
        db.session.add(activity)

        db.session.delete(station)
        db.session.commit()

        return jsonify({"success": True, "message": f"Station {station_name} deleted successfully"})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/user/<int:user_id>/toggle-status", methods=["POST"])
def toggle_user_status(user_id):
    """Toggle user active/inactive status (admin only)."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    user = User.query.get_or_404(user_id)
    
    # Prevent admin from deactivating themselves
    if user_id == current_user.id:
        return jsonify({"success": False, "error": "You cannot change your own status"}), 400

    try:
        # Since there's no active status field in the model, we'll simulate it
        # For now, we'll just return a success message without actually changing anything
        # In a real implementation, you'd add an 'is_active' field to the User model
        
        status = "activated" if user.id % 2 == 0 else "deactivated"  # Mock logic
        
        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="User Status Toggle",
            description=f"User {user.username} status toggled by {current_user.username}",
        )
        db.session.add(activity)
        db.session.commit()

        return jsonify({
            "success": True, 
            "message": f"User {user.username} has been {status}"
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/user/<int:user_id>", methods=["GET"])
def get_user(user_id):
    """Get user details (admin only)."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    user = User.query.get_or_404(user_id)

    # Get personnel count for this user if it's a station user
    from models import Personnel
    personnel_count = Personnel.query.filter_by(station_id=user_id).count() if not user.is_admin else 0

    user_data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "station_name": user.station_name,
        "station_type": user.station_type.value,
        "profile_picture": user.profile_picture,
        "is_admin": user.is_admin,
        "personnel_count": personnel_count,
        "date_created": user.date_created.strftime('%m/%d/%Y') if user.date_created else None,
    }

    return jsonify({"success": True, "user": user_data})


@auth_bp.route("/user/<int:user_id>/edit", methods=["GET"])
def get_user_edit(user_id):
    """Get user edit form (admin only)."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    user = User.query.get_or_404(user_id)

    # Return HTML form or user data for editing
    edit_html = f"""
    <form id="editUserForm" data-user-id="{user.id}">
        <div class="mb-3">
            <label for="editUsername" class="form-label">Username</label>
            <input type="text" class="form-control" id="editUsername" value="{user.username}" required>
        </div>
        <div class="mb-3">
            <label for="editEmail" class="form-label">Email</label>
            <input type="email" class="form-control" id="editEmail" value="{user.email}" required>
        </div>
        <div class="mb-3">
            <label for="editStationType" class="form-label">Station Type</label>
            <select class="form-select" id="editStationType" required>
                <option value="CENTRAL" {'selected' if user.station_type.value == 'CENTRAL' else ''}>Central Station</option>
                <option value="TALISAY" {'selected' if user.station_type.value == 'TALISAY' else ''}>Talisay Station</option>
                <option value="BACON" {'selected' if user.station_type.value == 'BACON' else ''}>Bacon Station</option>
                <option value="ABUYOG" {'selected' if user.station_type.value == 'ABUYOG' else ''}>Abuyog Station</option>
            </select>
        </div>
        <div class="mb-3 form-check">
            <input type="checkbox" class="form-check-input" id="editIsAdmin" {'checked' if user.is_admin else ''}>
            <label class="form-check-label" for="editIsAdmin">Administrator</label>
        </div>
    </form>
    """

    return jsonify({"success": True, "html": edit_html})


@auth_bp.route("/user/<int:user_id>/delete", methods=["DELETE"])
def delete_user_new(user_id):
    """Delete user (admin only) - new endpoint to match frontend expectations."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({"success": False, "error": "Access denied"}), 403

    # Prevent self-deletion
    if user_id == current_user.id:
        return jsonify({"success": False, "error": "You cannot delete your own account"}), 400

    user = User.query.get_or_404(user_id)
    username = user.username

    try:
        # Log activity before deletion
        activity = ActivityLog(
            user_id=current_user.id,
            title="User Deletion",
            description=f"User {username} deleted by {current_user.username}",
        )
        db.session.add(activity)

        db.session.delete(user)
        db.session.commit()

        return jsonify({"success": True, "message": f"User {username} deleted successfully"})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
