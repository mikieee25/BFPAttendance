# Database models for BFP Sorsogon Attendance System
# Contains all SQLAlchemy models and enums used throughout the application

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from enum import Enum
import json

# Global database instance used by all models
db = SQLAlchemy()


class StationType(Enum):
    """Enumeration of BFP station types in Sorsogon"""

    CENTRAL = "CENTRAL"
    TALISAY = "TALISAY"
    BACON = "BACON"
    ABUYOG = "ABUYOG"


class AttendanceStatus(Enum):
    """Enumeration of possible attendance statuses"""

    PRESENT = "PRESENT"
    LATE = "LATE"
    ABSENT = "ABSENT"


class User(UserMixin, db.Model):
    """User model for system authentication and authorization.

    Represents admin users and station users who can log into the system.
    Admin users can manage all stations, while station users manage only their assigned station.
    """

    __tablename__ = "user"

    # Primary key and authentication fields
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)  # Hashed password

    # Station assignment and permissions
    station_type = db.Column(db.Enum(StationType), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)  # Admin can access all stations

    # Metadata
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    profile_picture = db.Column(
        db.String(255), default="images/profile-placeholder.jpg"
    )

    # Relationships
    personnel = db.relationship("Personnel", backref="station", lazy=True)
    activity_logs = db.relationship("ActivityLog", backref="user", lazy=True)
    approved_attendance = db.relationship(
        "Attendance",
        foreign_keys="Attendance.approved_by",
        backref="approver",
        lazy=True,
    )

    def __repr__(self):
        return f"<User {self.username}>"

    @property
    def station_name(self):
        station_names = {
            StationType.CENTRAL: "Central Station",
            StationType.TALISAY: "Talisay Station",
            StationType.BACON: "Bacon Station",
            StationType.ABUYOG: "Abuyog Station",
        }
        return station_names.get(self.station_type, "Unknown Station")


class Personnel(db.Model):
    """Personnel model representing BFP officers and staff.

    Each personnel record belongs to a station and can have face data for biometric recognition.
    Personnel records are used for attendance tracking and reporting.
    """

    __tablename__ = "personnel"

    # Primary key and basic information
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    rank = db.Column(db.String(100), nullable=False)  # BFP rank/position

    # Station assignment (foreign key to User table)
    station_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Metadata
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    image_path = db.Column(db.String(255))  # Profile photo path

    # Relationships
    attendances = db.relationship(
        "Attendance", backref="personnel", lazy=True, cascade="all, delete-orphan"
    )
    face_data = db.relationship("FaceData", backref="personnel", lazy=True)
    pending_attendance = db.relationship(
        "PendingAttendance", backref="personnel", lazy=True
    )

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def name_with_rank(self):
        return f"{self.rank} {self.first_name} {self.last_name}"

    def __repr__(self):
        return f"<Personnel {self.full_name}>"


class Attendance(db.Model):
    """Attendance model for tracking daily time-in and time-out records.

    Records can be created automatically via face recognition or manually by station users.
    Includes approval workflow and image storage for verification.
    """

    __tablename__ = "attendance"

    # Primary key and personnel reference
    id = db.Column(db.Integer, primary_key=True)
    personnel_id = db.Column(db.Integer, db.ForeignKey("personnel.id"), nullable=False)

    # Time tracking
    date = db.Column(db.Date, nullable=False)
    time_in = db.Column(db.DateTime)
    time_out = db.Column(db.DateTime)
    status = db.Column(db.Enum(AttendanceStatus))  # PRESENT, LATE, ABSENT

    # Face recognition metadata
    confidence_score = db.Column(db.Float)  # Face recognition confidence (0-1)
    is_auto_captured = db.Column(db.Boolean)  # True if created via face recognition

    # Approval workflow
    is_approved = db.Column(db.Boolean)
    approved_by = db.Column(
        db.Integer, db.ForeignKey("user.id")
    )  # Who approved this record

    # Image storage for verification
    time_in_image = db.Column(db.String(255))  # Captured image for time-in
    time_out_image = db.Column(db.String(255))  # Captured image for time-out

    # Metadata
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Attendance {self.personnel.full_name} - {self.date}>"

    @property
    def work_hours(self):
        """Calculate total work hours if both time_in and time_out are recorded"""
        if self.time_in and self.time_out:
            delta = self.time_out - self.time_in
            return round(delta.total_seconds() / 3600, 2)
        return 0


class FaceData(db.Model):
    """Face recognition data storage for personnel biometric identification.

    Stores facial embeddings/encodings extracted from registered photos.
    Multiple face samples per personnel improve recognition accuracy.
    """

    __tablename__ = "face_data"

    # Primary key and personnel reference
    id = db.Column(db.Integer, primary_key=True)
    personnel_id = db.Column(db.Integer, db.ForeignKey("personnel.id"), nullable=False)

    # Face data storage
    filename = db.Column(db.String(255), nullable=False)  # Original image filename
    embedding = db.Column(db.Text)  # JSON-encoded face embedding/encoding
    confidence = db.Column(db.Float)  # Quality/confidence of the face detection

    # Metadata
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<FaceData {self.personnel.full_name} - {self.filename}>"


class ActivityLog(db.Model):
    """System activity log for audit trail and monitoring.

    Records all significant user actions including logins, attendance operations,
    personnel management, and system administration activities.
    """

    __tablename__ = "activity_log"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ActivityLog {self.title}>"


class PendingAttendance(db.Model):
    """Pending attendance requests that require manual approval.

    Used when face recognition fails or for manual attendance submissions
    that need supervisor review before being added to official attendance records.
    """

    __tablename__ = "pending_attendance"

    # Primary key and personnel reference
    id = db.Column(db.Integer, primary_key=True)
    personnel_id = db.Column(db.Integer, db.ForeignKey("personnel.id"), nullable=False)

    # Attendance details
    date = db.Column(db.Date, nullable=False)
    attendance_type = db.Column(
        db.Enum("TIME_IN", "TIME_OUT", name="attendance_type_enum"), nullable=False
    )

    # Supporting documentation
    image_path = db.Column(db.String(255), nullable=False)  # Photo evidence
    notes = db.Column(db.Text)  # Additional context or reason

    # Metadata
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return (
            f"<PendingAttendance {self.personnel.full_name} - {self.attendance_type}>"
        )
