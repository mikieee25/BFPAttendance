#!/usr/bin/env python3
"""
Clean Attendance Script
Removes attendance-related records while preserving personnel and face data.
"""

import logging
import os
import shutil
from pathlib import Path
from sqlalchemy import or_
from flask import has_app_context

from config import (
    ActivityLog,
    Attendance,
    PendingAttendance,
    confirm_action,
    db,
    get_app_context,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
)

logger = logging.getLogger(__name__)


def _cleanup_attendance_images():
    """Delete temporary attendance image folders and files."""
    temp_root = Path(__file__).resolve().parent.parent / "static" / "images" / "attendance_temp"
    legacy_root = Path(__file__).resolve().parent.parent / "static" / "images" / "attendance_images_temp"

    deleted_items = 0
    for root in [temp_root, legacy_root]:
        if not root.exists():
            continue
        for item in root.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
                deleted_items += 1
            except Exception as exc:
                logger.warning("Failed deleting %s: %s", item, exc)
    return deleted_items


def clean_attendance_data(clean_logs: bool = True, clean_images: bool = True):
    """Remove attendance and pending attendance records for repeatable testing."""
    try:
        with get_app_context():
            print_header("CLEANING ATTENDANCE DATA")

            attendance_count = Attendance.query.count()
            pending_count = PendingAttendance.query.count()
            print_info(f"Current Attendance records: {attendance_count}")
            print_info(f"Current Pending Attendance records: {pending_count}")

            if clean_logs:
                attendance_log_count = ActivityLog.query.filter(
                    or_(
                        ActivityLog.title.ilike("%attendance%"),
                        ActivityLog.description.ilike("%attendance%"),
                    )
                ).count()
                print_info(f"Attendance-related Activity Logs: {attendance_log_count}")

            if not confirm_action(
                "This will delete attendance records (and optionally attendance logs/images). Continue?"
            ):
                print_warning("Operation cancelled.")
                return False

            deleted_attendance = Attendance.query.delete()
            deleted_pending = PendingAttendance.query.delete()
            print_success(f"Deleted {deleted_attendance} Attendance record(s)")
            print_success(f"Deleted {deleted_pending} Pending Attendance record(s)")

            deleted_logs = 0
            if clean_logs:
                deleted_logs = ActivityLog.query.filter(
                    or_(
                        ActivityLog.title.ilike("%attendance%"),
                        ActivityLog.description.ilike("%attendance%"),
                    )
                ).delete(synchronize_session=False)
                print_success(f"Deleted {deleted_logs} attendance-related Activity Log record(s)")

            db.session.commit()

            deleted_images = 0
            if clean_images:
                deleted_images = _cleanup_attendance_images()
                print_success(f"Deleted {deleted_images} attendance image file(s)/folder(s)")

            print_info("Verification:")
            print(f"  Attendance: {Attendance.query.count()}")
            print(f"  Pending Attendance: {PendingAttendance.query.count()}")
            if clean_logs:
                remaining_logs = ActivityLog.query.filter(
                    or_(
                        ActivityLog.title.ilike("%attendance%"),
                        ActivityLog.description.ilike("%attendance%"),
                    )
                ).count()
                print(f"  Attendance Logs: {remaining_logs}")

            print_success("Attendance cleanup completed.")
            return True

    except Exception as e:
        print_error(f"Error cleaning attendance data: {str(e)}")
        try:
            if has_app_context():
                db.session.rollback()
        except Exception as rollback_error:
            logger.error("Rollback failed: %s", rollback_error)
        return False


def main():
    """Main function."""
    print_header("BFP ATTENDANCE SYSTEM - ATTENDANCE CLEANER")
    print("Use this to reset attendance for repeat testing.")
    print("Personnel and face registration are preserved.")
    print("\nOptions:")
    print("1. Clean attendance + pending + attendance logs + attendance images")
    print("2. Clean attendance + pending only")
    print("3. Show current attendance counts")
    print("4. Cancel")

    try:
        choice = input("\nEnter your choice (1-4): ").strip()
        if choice == "1":
            clean_attendance_data(clean_logs=True, clean_images=True)
        elif choice == "2":
            clean_attendance_data(clean_logs=False, clean_images=False)
        elif choice == "3":
            with get_app_context():
                print_info(f"Attendance: {Attendance.query.count()}")
                print_info(f"Pending Attendance: {PendingAttendance.query.count()}")
        elif choice == "4":
            print_warning("Operation cancelled.")
        else:
            print_error("Invalid choice. Operation cancelled.")
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user.")
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    main()
