#!/usr/bin/env python3
"""
Clean Database Script
Removes all entries from the database while keeping the structure intact.
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


def clean_all_tables():
    """Remove all data from all tables"""
    try:
        with get_app_context():
            print_header("CLEANING ALL DATABASE TABLES")

            # Show current record counts
            print_info("Current database status:")
            print(f"  Users: {User.query.count()}")
            print(f"  Personnel: {Personnel.query.count()}")
            print(f"  Attendance: {Attendance.query.count()}")
            print(f"  Face Data: {FaceData.query.count()}")
            print(f"  Activity Logs: {ActivityLog.query.count()}")
            print(f"  Pending Attendance: {PendingAttendance.query.count()}")

            # Confirm action
            if not confirm_action(
                "This will delete ALL data from the database. Continue?"
            ):
                print_warning("Operation cancelled.")
                return False

            print_info("Starting database cleanup...")

            # Delete in proper order (considering foreign key constraints)
            tables_to_clean = [
                (PendingAttendance, "Pending Attendance"),
                (Attendance, "Attendance"),
                (FaceData, "Face Data"),
                (ActivityLog, "Activity Logs"),
                (Personnel, "Personnel"),
                (User, "Users"),
            ]

            for model, name in tables_to_clean:
                count = model.query.count()
                if count > 0:
                    model.query.delete()
                    print_success(f"Deleted {count} {name} records")
                else:
                    print_info(f"No {name} records to delete")

            # Commit changes
            db.session.commit()
            print_success("Database cleanup completed successfully!")

            # Verify cleanup
            print_info("\nVerifying cleanup:")
            total_records = sum(
                [
                    User.query.count(),
                    Personnel.query.count(),
                    Attendance.query.count(),
                    FaceData.query.count(),
                    ActivityLog.query.count(),
                    PendingAttendance.query.count(),
                ]
            )

            if total_records == 0:
                print_success("✓ All tables are now empty")
            else:
                print_warning(f"⚠ Warning: {total_records} records still remain")

            return True

    except Exception as e:
        print_error(f"Error during database cleanup: {str(e)}")
        try:
            db.session.rollback()
        except:
            pass
        return False


def reset_auto_increment():
    """Reset auto-increment counters for all tables"""
    try:
        with get_app_context():
            print_info("Resetting auto-increment counters...")

            tables = [
                "user",
                "personnel",
                "attendance",
                "face_data",
                "activity_log",
                "pending_attendance",
            ]

            for table in tables:
                try:
                    db.session.execute(f"ALTER TABLE {table} AUTO_INCREMENT = 1")
                    print_success(f"Reset auto-increment for {table}")
                except Exception as e:
                    print_warning(
                        f"Could not reset auto-increment for {table}: {str(e)}"
                    )

            db.session.commit()
            print_success("Auto-increment reset completed!")

    except Exception as e:
        print_error(f"Error resetting auto-increment: {str(e)}")


def main():
    """Main function"""
    print_header("BFP ATTENDANCE SYSTEM - DATABASE CLEANER")

    print("This script will completely clean the database.")
    print("⚠️  WARNING: This action cannot be undone!")
    print("\nOptions:")
    print("1. Clean all data and reset auto-increment")
    print("2. Clean all data only")
    print("3. Cancel")

    try:
        choice = input("\nEnter your choice (1-3): ").strip()

        if choice == "1":
            if clean_all_tables():
                reset_auto_increment()
        elif choice == "2":
            clean_all_tables()
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
