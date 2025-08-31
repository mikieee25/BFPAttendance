from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from enum import Enum
import json

db = SQLAlchemy()


class StationType(Enum):
    CENTRAL = "CENTRAL"
    TALISAY = "TALISAY"
    BACON = "BACON"
    ABUYOG = "ABUYOG"


class AttendanceStatus(Enum):
    PRESENT = "PRESENT"
    LATE = "LATE"
    ABSENT = "ABSENT"


class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    station_type = db.Column(db.Enum(StationType), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
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
    __tablename__ = "personnel"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    rank = db.Column(db.String(100), nullable=False)
    station_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    image_path = db.Column(db.String(255))

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
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True)
    personnel_id = db.Column(db.Integer, db.ForeignKey("personnel.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time_in = db.Column(db.DateTime)
    time_out = db.Column(db.DateTime)
    status = db.Column(db.Enum(AttendanceStatus))
    confidence_score = db.Column(db.Float)
    is_auto_captured = db.Column(db.Boolean)
    is_approved = db.Column(db.Boolean)
    approved_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    time_in_image = db.Column(db.String(255))
    time_out_image = db.Column(db.String(255))
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Attendance {self.personnel.full_name} - {self.date}>"

    @property
    def work_hours(self):
        if self.time_in and self.time_out:
            delta = self.time_out - self.time_in
            return round(delta.total_seconds() / 3600, 2)
        return 0


class FaceData(db.Model):
    __tablename__ = "face_data"

    id = db.Column(db.Integer, primary_key=True)
    personnel_id = db.Column(db.Integer, db.ForeignKey("personnel.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    embedding = db.Column(db.Text)
    confidence = db.Column(db.Float)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<FaceData {self.personnel.full_name} - {self.filename}>"


class ActivityLog(db.Model):
    __tablename__ = "activity_log"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ActivityLog {self.title}>"


class PendingAttendance(db.Model):
    __tablename__ = "pending_attendance"

    id = db.Column(db.Integer, primary_key=True)
    personnel_id = db.Column(db.Integer, db.ForeignKey("personnel.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    attendance_type = db.Column(
        db.Enum("TIME_IN", "TIME_OUT", name="attendance_type_enum"), nullable=False
    )
    image_path = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.Text)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return (
            f"<PendingAttendance {self.personnel.full_name} - {self.attendance_type}>"
        )
