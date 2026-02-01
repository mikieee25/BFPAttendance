#!/usr/bin/env python3
"""
Simple Database Migration Script
Adds new fields and indexes without requiring full app dependencies
"""

import os
import sys
from datetime import datetime


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


def get_db_connection():
    """Get database connection from environment or defaults"""
    import pymysql

    # Parse DATABASE_URL if exists
    db_url = os.environ.get(
        "DATABASE_URL", "mysql+pymysql://root:@localhost/bfp_sorsogon_attendance"
    )

    # Simple parsing (mysql+pymysql://user:pass@host/dbname)
    if "mysql" in db_url:
        parts = db_url.replace("mysql+pymysql://", "").split("@")
        if len(parts) == 2:
            user_pass = parts[0].split(":")
            host_db = parts[1].split("/")

            user = user_pass[0] if len(user_pass) > 0 else "root"
            password = user_pass[1] if len(user_pass) > 1 else ""
            host = host_db[0] if len(host_db) > 0 else "localhost"
            database = host_db[1] if len(host_db) > 1 else "bfp_sorsogon_attendance"
        else:
            # Defaults
            user = "root"
            password = ""
            host = "localhost"
            database = "bfp_sorsogon_attendance"
    else:
        user = "root"
        password = ""
        host = "localhost"
        database = "bfp_sorsogon_attendance"

    print_info(f"Connecting to database: {database} on {host}")

    connection = pymysql.connect(
        host=host,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )

    return connection


def column_exists(cursor, table, column):
    """Check if column exists in table"""
    cursor.execute(f"SHOW COLUMNS FROM {table} LIKE '{column}'")
    return cursor.fetchone() is not None


def index_exists(cursor, table, index_name):
    """Check if index exists in table"""
    cursor.execute(f"SHOW INDEX FROM {table} WHERE Key_name = '{index_name}'")
    return cursor.fetchone() is not None


def migrate_database():
    """Apply database migrations"""
    try:
        print_header("BFP Sorsogon Attendance System - Database Migration")
        print_info(
            f"Migration started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Get database connection
        connection = get_db_connection()
        cursor = connection.cursor()

        changes_made = []

        # Migration 1: Add must_change_password to User table
        print_info("\n[1/3] Checking User table for must_change_password field...")

        if not column_exists(cursor, "user", "must_change_password"):
            print_info("Adding must_change_password column to user table...")
            try:
                cursor.execute(
                    "ALTER TABLE user ADD COLUMN must_change_password TINYINT(1) DEFAULT 0"
                )
                connection.commit()
                print_success("Added must_change_password field to User table")
                changes_made.append("Added must_change_password field to User table")
            except Exception as e:
                print_error(f"Failed to add must_change_password: {e}")
                connection.rollback()
        else:
            print_success("must_change_password field already exists")

        # Migration 2: Add indexes to Attendance table
        print_info("\n[2/3] Checking Attendance table indexes...")

        indexes_to_create = [
            ("idx_attendance_lookup", "personnel_id, date"),
            ("idx_attendance_date", "date"),
            ("idx_attendance_status", "status"),
        ]

        for index_name, columns in indexes_to_create:
            if not index_exists(cursor, "attendance", index_name):
                print_info(f"Creating index {index_name}...")
                try:
                    cursor.execute(
                        f"CREATE INDEX {index_name} ON attendance ({columns})"
                    )
                    connection.commit()
                    print_success(f"Created index: {index_name}")
                    changes_made.append(f"Created index: {index_name}")
                except Exception as e:
                    print_error(f"Failed to create index {index_name}: {e}")
                    connection.rollback()
            else:
                print_success(f"Index {index_name} already exists")

        # Migration 3: Verify changes
        print_info("\n[3/3] Verifying migrations...")

        # Verify must_change_password field
        if column_exists(cursor, "user", "must_change_password"):
            print_success("Verified: must_change_password field exists")
        else:
            print_error("Verification failed: must_change_password field missing")

        # Verify indexes
        for index_name, _ in indexes_to_create:
            if index_exists(cursor, "attendance", index_name):
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

        cursor.close()
        connection.close()

        return True

    except Exception as e:
        print_error(f"\nMigration failed: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


def rollback_migration():
    """Rollback migration changes"""
    try:
        print_header("Rolling Back Database Migration")

        response = input(
            "Are you sure you want to rollback? This will remove the new fields and indexes. (yes/no): "
        )
        if response.lower() != "yes":
            print_info("Rollback cancelled")
            return False

        # Get database connection
        connection = get_db_connection()
        cursor = connection.cursor()

        # Remove must_change_password field
        print_info("Checking must_change_password field...")
        if column_exists(cursor, "user", "must_change_password"):
            print_info("Removing must_change_password field...")
            try:
                cursor.execute("ALTER TABLE user DROP COLUMN must_change_password")
                connection.commit()
                print_success("Removed must_change_password field")
            except Exception as e:
                print_error(f"Failed to remove must_change_password: {e}")
                connection.rollback()

        # Remove indexes
        print_info("Removing indexes...")
        indexes_to_remove = [
            "idx_attendance_lookup",
            "idx_attendance_date",
            "idx_attendance_status",
        ]

        for index_name in indexes_to_remove:
            if index_exists(cursor, "attendance", index_name):
                print_info(f"Removing index {index_name}...")
                try:
                    cursor.execute(f"DROP INDEX {index_name} ON attendance")
                    connection.commit()
                    print_success(f"Removed index: {index_name}")
                except Exception as e:
                    print_error(f"Failed to remove index {index_name}: {e}")
                    connection.rollback()

        print_success("\nRollback completed!")

        cursor.close()
        connection.close()

        return True

    except Exception as e:
        print_error(f"\nRollback failed: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print_header("BFP Sorsogon Database Migration Tool")

    # Check if pymysql is available
    try:
        import pymysql
    except ImportError:
        print_error("PyMySQL is required for this script")
        print_info("Install it with: pip install pymysql")
        sys.exit(1)

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        success = rollback_migration()
    else:
        print_info("Running migration...")
        print_info("To rollback, run: python migrate_db_simple.py rollback\n")
        success = migrate_database()

    sys.exit(0 if success else 1)
