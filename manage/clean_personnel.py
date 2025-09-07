#!/usr/bin/env python3
"""
Clean Users/Personnel Script
Removes all personnel and related data while keeping admin users intact.
"""
import sys
from config import (
    get_app_context,
    db,
    User,
    Personnel,
    Attendance,
    FaceData,
    ActivityLog,
    PendingAttendance,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_header,
    confirm_action,
)


def clean_personnel_data():
    """Remove all personnel and their related data"""
    try:
        with get_app_context():
            print_header("CLEANING PERSONNEL DATA")

            # Show current record counts
            print_info("Current database status:")
            total_users = User.query.count()
            admin_users = User.query.filter_by(is_admin=True).count()
            non_admin_users = total_users - admin_users
            personnel_count = Personnel.query.count()
            attendance_count = Attendance.query.count()
            face_data_count = FaceData.query.count()
            pending_count = PendingAttendance.query.count()

            print(
                f"  Total Users: {total_users} (Admin: {admin_users}, Non-Admin: {non_admin_users})"
            )
            print(f"  Personnel: {personnel_count}")
            print(f"  Attendance: {attendance_count}")
            print(f"  Face Data: {face_data_count}")
            print(f"  Pending Attendance: {pending_count}")

            if personnel_count == 0:
                print_info("No personnel data to clean.")
                return True

            # Confirm action
            if not confirm_action(
                "This will delete ALL personnel and related data. Admin users will be preserved. Continue?"
            ):
                print_warning("Operation cancelled.")
                return False

            print_info("Starting personnel data cleanup...")

            # Delete in proper order (considering foreign key constraints)
            cleanup_operations = [
                (
                    PendingAttendance,
                    "Pending Attendance",
                    lambda: PendingAttendance.query.delete(),
                ),
                (Attendance, "Attendance Records", lambda: Attendance.query.delete()),
                (FaceData, "Face Data", lambda: FaceData.query.delete()),
                (Personnel, "Personnel Records", lambda: Personnel.query.delete()),
                (
                    User,
                    "Non-Admin Users",
                    lambda: User.query.filter_by(is_admin=False).delete(),
                ),
            ]

            for model, name, delete_func in cleanup_operations:
                count_before = (
                    model.query.count()
                    if model != User
                    else User.query.filter_by(is_admin=False).count()
                )
                if count_before > 0:
                    delete_func()
                    print_success(f"Deleted {count_before} {name}")
                else:
                    print_info(f"No {name} to delete")

            # Clean activity logs related to deleted users (keep admin activity logs)
            # First, get all remaining user IDs (should be only admins)
            remaining_user_ids = [user.id for user in User.query.all()]

            # Delete activity logs that don't belong to remaining users
            deleted_logs = ActivityLog.query.filter(
                ~ActivityLog.user_id.in_(remaining_user_ids)
            ).delete(synchronize_session="fetch")
            if deleted_logs > 0:
                print_success(f"Deleted {deleted_logs} orphaned Activity Log records")

            # Commit changes
            db.session.commit()
            print_success("Personnel data cleanup completed successfully!")

            # Verify cleanup
            print_info("\nVerifying cleanup:")
            remaining_users = User.query.count()
            remaining_admin = User.query.filter_by(is_admin=True).count()
            remaining_personnel = Personnel.query.count()
            remaining_attendance = Attendance.query.count()
            remaining_face_data = FaceData.query.count()
            remaining_pending = PendingAttendance.query.count()

            print(
                f"  Remaining Users: {remaining_users} (All should be admins: {remaining_admin})"
            )
            print(f"  Remaining Personnel: {remaining_personnel}")
            print(f"  Remaining Attendance: {remaining_attendance}")
            print(f"  Remaining Face Data: {remaining_face_data}")
            print(f"  Remaining Pending Attendance: {remaining_pending}")

            if (
                remaining_personnel == 0
                and remaining_attendance == 0
                and remaining_face_data == 0
            ):
                print_success("✓ All personnel data successfully removed")
                print_success(f"✓ {remaining_admin} admin user(s) preserved")
            else:
                print_warning("⚠ Warning: Some personnel data may still remain")

            return True

    except Exception as e:
        print_error(f"Error during personnel cleanup: {str(e)}")
        try:
            db.session.rollback()
        except:
            pass
        return False


def list_admin_users():
    """List all admin users that will be preserved"""
    try:
        with get_app_context():
            print_info("Admin users that will be preserved:")
            admin_users = User.query.filter_by(is_admin=True).all()

            if not admin_users:
                print_warning("No admin users found!")
                return

            for user in admin_users:
                print(f"  - {user.username} ({user.email}) - {user.station_name}")

    except Exception as e:
        print_error(f"Error listing admin users: {str(e)}")


def main():
    """Main function"""
    print_header("BFP ATTENDANCE SYSTEM - PERSONNEL DATA CLEANER")

    print("This script will clean all personnel and related data.")
    print("Admin users and their activity logs will be preserved.")
    print("⚠️  WARNING: This action cannot be undone!")

    # Show admin users that will be preserved
    list_admin_users()

    print("\nOptions:")
    print("1. Clean all personnel data (preserve admin users)")
    print("2. Show current data counts only")
    print("3. Cancel")

    try:
        choice = input("\nEnter your choice (1-3): ").strip()

        if choice == "1":
            clean_personnel_data()
        elif choice == "2":
            with get_app_context():
                print_info("\nCurrent database status:")
                print(f"  Total Users: {User.query.count()}")
                print(f"  Admin Users: {User.query.filter_by(is_admin=True).count()}")
                print(f"  Personnel: {Personnel.query.count()}")
                print(f"  Attendance: {Attendance.query.count()}")
                print(f"  Face Data: {FaceData.query.count()}")
                print(f"  Pending Attendance: {PendingAttendance.query.count()}")
        elif choice == "3":
            print_warning("Operation cancelled.")
        else:
            print_error("Invalid choice. Operation cancelled.")

    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user.")
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    main()
