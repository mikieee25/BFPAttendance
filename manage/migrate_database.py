#!/usr/bin/env python3
"""
Database Migration Script
Handles database schema creation, updates, and migrations.
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
    StationType,
    AttendanceStatus,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_header,
    confirm_action,
)
from werkzeug.security import generate_password_hash


def create_database_schema():
    """Create all database tables"""
    try:
        with get_app_context():
            print_header("CREATING DATABASE SCHEMA")

            print_info("Creating database tables...")

            # Create all tables
            db.create_all()

            print_success("Database schema created successfully!")

            # Show created tables
            print_info("Created tables:")
            tables = db.engine.table_names()
            for table in tables:
                print(f"  ✓ {table}")

            return True

    except Exception as e:
        print_error(f"Error creating database schema: {str(e)}")
        return False


def drop_database_schema():
    """Drop all database tables"""
    try:
        with get_app_context():
            print_header("DROPPING DATABASE SCHEMA")

            if not confirm_action(
                "This will DROP ALL TABLES and DELETE ALL DATA. Continue?"
            ):
                print_warning("Operation cancelled.")
                return False

            print_info("Dropping all database tables...")

            # Drop all tables
            db.drop_all()

            print_success("Database schema dropped successfully!")
            return True

    except Exception as e:
        print_error(f"Error dropping database schema: {str(e)}")
        return False


def recreate_database_schema():
    """Drop and recreate all database tables"""
    try:
        with get_app_context():
            print_header("RECREATING DATABASE SCHEMA")

            if not confirm_action(
                "This will DROP ALL TABLES, DELETE ALL DATA, and recreate the schema. Continue?"
            ):
                print_warning("Operation cancelled.")
                return False

            print_info("Dropping existing tables...")
            db.drop_all()
            print_success("Tables dropped")

            print_info("Creating new tables...")
            db.create_all()
            print_success("Tables created")

            print_success("Database schema recreated successfully!")
            return True

    except Exception as e:
        print_error(f"Error recreating database schema: {str(e)}")
        return False


def create_default_admin():
    """Create default admin user"""
    try:
        with get_app_context():
            print_info("Creating default admin user...")

            # Check if admin already exists
            existing_admin = User.query.filter_by(is_admin=True).first()
            if existing_admin:
                print_warning(f"Admin user already exists: {existing_admin.username}")
                return True

            # Create default admin
            admin_user = User(
                username="admin",
                email="admin@bfp-sorsogon.gov.ph",
                password=generate_password_hash("admin123"),  # Default password
                station_type=StationType.CENTRAL,
                is_admin=True,
            )

            db.session.add(admin_user)
            db.session.commit()

            print_success("Default admin user created!")
            print_info("Username: admin")
            print_info("Password: admin123")
            print_warning("⚠️  Please change the default password after first login!")

            return True

    except Exception as e:
        print_error(f"Error creating default admin: {str(e)}")
        return False


def create_station_users():
    """Create default station users"""
    try:
        with get_app_context():
            print_info("Creating default station users...")

            users_created = 0

            for station_type in StationType:
                # Skip if station user already exists
                existing_user = User.query.filter_by(
                    station_type=station_type, is_admin=False
                ).first()
                if existing_user:
                    print_info(
                        f"Station user already exists for {station_type.value}: {existing_user.username}"
                    )
                    continue

                username = f"{station_type.value.lower()}_station"
                email = f"{station_type.value.lower()}@bfp-sorsogon.gov.ph"

                station_user = User(
                    username=username,
                    email=email,
                    password=generate_password_hash("station123"),
                    station_type=station_type,
                    is_admin=False,
                )

                db.session.add(station_user)
                users_created += 1
                print_success(f"Created station user: {username}")

            if users_created > 0:
                db.session.commit()
                print_success(f"Created {users_created} station user(s)")
                print_info("Default password for all station users: station123")
                print_warning("⚠️  Please change default passwords after first login!")
            else:
                print_info("All station users already exist")

            return True

    except Exception as e:
        print_error(f"Error creating station users: {str(e)}")
        return False


def initialize_fresh_database():
    """Initialize a completely fresh database"""
    try:
        with get_app_context():
            print_header("INITIALIZING FRESH DATABASE")

            print_info("This will create a fresh database with:")
            print("  • Database schema (all tables)")
            print("  • Default admin user")
            print("  • Default station users")

            if not confirm_action("Continue with fresh database initialization?"):
                print_warning("Operation cancelled.")
                return False

            # Step 1: Create schema
            print_info("\n1. Creating database schema...")
            db.create_all()
            print_success("Schema created")

            # Step 2: Create admin user
            print_info("\n2. Creating default admin user...")
            create_default_admin()

            # Step 3: Create station users
            print_info("\n3. Creating station users...")
            create_station_users()

            print_header("DATABASE INITIALIZATION COMPLETED")
            print_success("Fresh database initialized successfully!")

            # Show summary
            print_info("Database summary:")
            print(f"  Total users: {User.query.count()}")
            print(f"  Admin users: {User.query.filter_by(is_admin=True).count()}")
            print(f"  Station users: {User.query.filter_by(is_admin=False).count()}")

            print_info("\nDefault credentials:")
            print("  Admin - Username: admin, Password: admin123")
            print("  Stations - Password: station123")
            print_warning("⚠️  IMPORTANT: Change all default passwords!")

            return True

    except Exception as e:
        print_error(f"Error initializing database: {str(e)}")
        return False


def check_database_status():
    """Check current database status"""
    try:
        with get_app_context():
            print_header("DATABASE STATUS")

            # Check if tables exist
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()

            print_info(f"Database: {db.engine.url.database}")
            print_info(f"Tables found: {len(tables)}")

            if tables:
                print_info("Existing tables:")
                for table in tables:
                    print(f"  ✓ {table}")

                # Check data counts
                print_info("\nData counts:")
                try:
                    print(f"  Users: {User.query.count()}")
                    print(f"  Personnel: {Personnel.query.count()}")
                    print(f"  Attendance: {Attendance.query.count()}")
                    print(f"  Face Data: {FaceData.query.count()}")
                    print(f"  Activity Logs: {ActivityLog.query.count()}")
                    print(f"  Pending Attendance: {PendingAttendance.query.count()}")
                except Exception as e:
                    print_warning(f"Could not query data counts: {str(e)}")
            else:
                print_warning("No tables found. Database appears to be empty.")

            return True

    except Exception as e:
        print_error(f"Error checking database status: {str(e)}")
        return False


def main():
    """Main function"""
    print_header("BFP ATTENDANCE SYSTEM - DATABASE MIGRATION MANAGER")

    print("Database schema and migration utility.")
    print("\nOptions:")
    print("1. Check database status")
    print("2. Initialize fresh database (schema + default users)")
    print("3. Create database schema only")
    print("4. Create default admin user")
    print("5. Create station users")
    print("6. Drop database schema (⚠️  DANGER)")
    print("7. Recreate database schema (⚠️  DANGER)")
    print("8. Cancel")

    try:
        choice = input("\nEnter your choice (1-8): ").strip()

        if choice == "1":
            check_database_status()
        elif choice == "2":
            initialize_fresh_database()
        elif choice == "3":
            create_database_schema()
        elif choice == "4":
            create_default_admin()
        elif choice == "5":
            create_station_users()
        elif choice == "6":
            drop_database_schema()
        elif choice == "7":
            recreate_database_schema()
        elif choice == "8":
            print_warning("Operation cancelled.")
        else:
            print_error("Invalid choice. Operation cancelled.")

    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user.")
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    main()
