#!/usr/bin/env python3
"""
Database Migration Script
Adds new fields and indexes to existing database without losing data
"""

import logging
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def print_header(text):
    """Print a formatted header"""
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80 + "\n")


def print_success(text):
    """Print success message"""
    print(f"✓ {text}")


def print_error(text):
    """Print error message"""
    print(f"✗ {text}")


def print_info(text):
    """Print info message"""
    print(f"ℹ {text}")


def migrate_database():
    """Apply database migrations"""
    try:
        # Import app and database
        from app import create_app
        from models import db

        app = create_app()

        with app.app_context():
            print_header("BFP Sorsogon Attendance System - Database Migration")
            print_info(
                f"Migration started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            # Get database engine
            engine = db.engine
            inspector = db.inspect(engine)

            # Track changes
            changes_made = []

            # Migration 1: Add must_change_password to User table
            print_info("\n[1/3] Checking User table for must_change_password field...")
            user_columns = [col["name"] for col in inspector.get_columns("user")]

            if "must_change_password" not in user_columns:
                print_info("Adding must_change_password column to user table...")
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            db.text(
                                "ALTER TABLE user ADD COLUMN must_change_password BOOLEAN DEFAULT FALSE"
                            )
                        )
                        conn.commit()
                    print_success("Added must_change_password field to User table")
                    changes_made.append(
                        "Added must_change_password field to User table"
                    )
                except Exception as e:
                    print_error(f"Failed to add must_change_password: {e}")
            else:
                print_success("must_change_password field already exists")

            # Migration 2: Add indexes to Attendance table
            print_info("\n[2/3] Checking Attendance table indexes...")
            attendance_indexes = inspector.get_indexes("attendance")
            existing_index_names = [idx["name"] for idx in attendance_indexes]

            indexes_to_create = [
                ("idx_attendance_lookup", ["personnel_id", "date"]),
                ("idx_attendance_date", ["date"]),
                ("idx_attendance_status", ["status"]),
            ]

            for index_name, columns in indexes_to_create:
                if index_name not in existing_index_names:
                    print_info(f"Creating index {index_name}...")
                    try:
                        columns_str = ", ".join(columns)
                        with engine.connect() as conn:
                            conn.execute(
                                db.text(
                                    f"CREATE INDEX {index_name} ON attendance ({columns_str})"
                                )
                            )
                            conn.commit()
                        print_success(f"Created index: {index_name}")
                        changes_made.append(f"Created index: {index_name}")
                    except Exception as e:
                        print_error(f"Failed to create index {index_name}: {e}")
                else:
                    print_success(f"Index {index_name} already exists")

            # Migration 3: Verify changes
            print_info("\n[3/3] Verifying migrations...")

            # Verify must_change_password field
            user_columns_after = [col["name"] for col in inspector.get_columns("user")]
            if "must_change_password" in user_columns_after:
                print_success("Verified: must_change_password field exists")
            else:
                print_error("Verification failed: must_change_password field missing")

            # Verify indexes
            attendance_indexes_after = inspector.get_indexes("attendance")
            existing_index_names_after = [
                idx["name"] for idx in attendance_indexes_after
            ]

            for index_name, _ in indexes_to_create:
                if index_name in existing_index_names_after:
                    print_success(f"Verified: Index {index_name} exists")
                else:
                    print_error(f"Verification failed: Index {index_name} missing")

            # Summary
            print_header("Migration Summary")
            if changes_made:
                print_info("Changes applied:")
                for change in changes_made:
                    print(f"  • {change}")
            else:
                print_info("No changes needed - database is already up to date")

            print_success("\nMigration completed successfully!")
            print_info(
                f"Migration finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            return True

    except Exception as e:
        print_error(f"\nMigration failed: {str(e)}")
        logger.exception("Migration error details:")
        return False


def rollback_migration():
    """Rollback migration changes (if needed)"""
    try:
        from app import create_app
        from models import db

        app = create_app()

        with app.app_context():
            print_header("Rolling Back Database Migration")

            response = input(
                "Are you sure you want to rollback? This will remove the new fields and indexes. (yes/no): "
            )
            if response.lower() != "yes":
                print_info("Rollback cancelled")
                return False

            engine = db.engine
            inspector = db.inspect(engine)

            # Remove must_change_password field
            print_info("Removing must_change_password field...")
            user_columns = [col["name"] for col in inspector.get_columns("user")]

            if "must_change_password" in user_columns:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            db.text("ALTER TABLE user DROP COLUMN must_change_password")
                        )
                        conn.commit()
                    print_success("Removed must_change_password field")
                except Exception as e:
                    print_error(f"Failed to remove must_change_password: {e}")

            # Remove indexes
            print_info("Removing indexes...")
            attendance_indexes = inspector.get_indexes("attendance")
            existing_index_names = [idx["name"] for idx in attendance_indexes]

            indexes_to_remove = [
                "idx_attendance_lookup",
                "idx_attendance_date",
                "idx_attendance_status",
            ]

            for index_name in indexes_to_remove:
                if index_name in existing_index_names:
                    try:
                        with engine.connect() as conn:
                            conn.execute(
                                db.text(f"DROP INDEX {index_name} ON attendance")
                            )
                            conn.commit()
                        print_success(f"Removed index: {index_name}")
                    except Exception as e:
                        print_error(f"Failed to remove index {index_name}: {e}")

            print_success("\nRollback completed!")
            return True

    except Exception as e:
        print_error(f"\nRollback failed: {str(e)}")
        logger.exception("Rollback error details:")
        return False


if __name__ == "__main__":
    print_header("BFP Sorsogon Database Migration Tool")

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        success = rollback_migration()
    else:
        print_info("Running migration...")
        print_info("To rollback, run: python migrate_db.py rollback\n")
        success = migrate_database()

    sys.exit(0 if success else 1)
