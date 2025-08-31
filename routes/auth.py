from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from models import db, User, ActivityLog, StationType

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user, remember=remember)

            # Log activity
            activity = ActivityLog(
                user_id=user.id,
                title="User Login",
                description=f"User {user.username} logged in successfully",
            )
            db.session.add(activity)
            db.session.commit()

            next_page = request.args.get("next")
            if next_page:
                return redirect(next_page)
            return redirect(url_for("dashboard.index"))
        else:
            flash("Invalid username or password", "error")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
def logout():
    if current_user.is_authenticated:
        # Log activity
        activity = ActivityLog(
            user_id=current_user.id,
            title="User Logout",
            description=f"User {current_user.username} logged out",
        )
        db.session.add(activity)
        db.session.commit()

        logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if not current_user.is_authenticated or not current_user.is_admin:
        flash("Access denied. Only administrators can create new accounts.", "error")
        return redirect(url_for("auth.login"))

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
            return render_template("auth/register.html", station_types=StationType)

        if User.query.filter_by(username=username).first():
            flash("Username already exists", "error")
            return render_template("auth/register.html", station_types=StationType)

        if User.query.filter_by(email=email).first():
            flash("Email already exists", "error")
            return render_template("auth/register.html", station_types=StationType)

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

    return render_template("auth/register.html", station_types=StationType)


@auth_bp.route("/manage-users")
def manage_users():
    if not current_user.is_authenticated or not current_user.is_admin:
        flash("Access denied. Only administrators can manage users.", "error")
        return redirect(url_for("dashboard.index"))

    users = User.query.all()
    return render_template("auth/manage_users.html", users=users)


@auth_bp.route("/delete-user/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    if not current_user.is_authenticated or not current_user.is_admin:
        flash("Access denied. Only administrators can delete users.", "error")
        return redirect(url_for("dashboard.index"))

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
