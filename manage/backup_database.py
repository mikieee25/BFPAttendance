#!/usr/bin/env python3
"""
Database Backup Script
Creates SQL dumps of the database for backup purposes.
"""
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from config import (
    print_success,
    print_error,
    print_warning,
    print_info,
    print_header,
    confirm_action,
)


def get_database_config():
    """Get database configuration from environment or use defaults"""
    db_url = os.environ.get(
        "DATABASE_URL", "mysql+pymysql://root:@localhost/bfp_sorsogon_attendance"
    )

    # Parse database URL
    if "mysql" in db_url:
        # Extract components from URL like: mysql+pymysql://user:password@host:port/database
        parts = db_url.replace("mysql+pymysql://", "").split("/")
        db_name = parts[-1]

        auth_host = parts[0]
        if "@" in auth_host:
            auth, host = auth_host.split("@")
            if ":" in auth:
                user, password = auth.split(":", 1)
            else:
                user, password = auth, ""
        else:
            host, user, password = auth_host, "root", ""

        if ":" in host:
            host, port = host.split(":")
        else:
            port = "3306"

        return {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": db_name,
        }

    return None


def create_backup_directory():
    """Create backup directory if it doesn't exist"""
    backup_dir = Path(__file__).parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    return backup_dir


def backup_database():
    """Create a database backup using mysqldump"""
    try:
        print_header("DATABASE BACKUP")

        # Get database configuration
        db_config = get_database_config()
        if not db_config:
            print_error("Could not parse database configuration")
            return False

        print_info(f"Backing up database: {db_config['database']}")
        print_info(f"Host: {db_config['host']}:{db_config['port']}")
        print_info(f"User: {db_config['user']}")

        # Create backup directory
        backup_dir = create_backup_directory()

        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"bfp_attendance_backup_{timestamp}.sql"
        backup_path = backup_dir / backup_filename

        # Build mysqldump command
        cmd = [
            "mysqldump",
            f"--host={db_config['host']}",
            f"--port={db_config['port']}",
            f"--user={db_config['user']}",
        ]

        # Add password if provided
        if db_config["password"]:
            cmd.append(f"--password={db_config['password']}")

        # Add backup options
        cmd.extend(
            [
                "--single-transaction",
                "--routines",
                "--triggers",
                "--add-drop-table",
                "--complete-insert",
                db_config["database"],
            ]
        )

        print_info(f"Creating backup: {backup_filename}")

        # Execute mysqldump
        with open(backup_path, "w", encoding="utf-8") as backup_file:
            try:
                result = subprocess.run(
                    cmd,
                    stdout=backup_file,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True,
                )

                # Check if backup file was created and has content
                if backup_path.exists() and backup_path.stat().st_size > 0:
                    file_size = backup_path.stat().st_size / (1024 * 1024)  # MB
                    print_success(f"Backup created successfully!")
                    print_info(f"File: {backup_path}")
                    print_info(f"Size: {file_size:.2f} MB")
                    return True
                else:
                    print_error("Backup file was not created or is empty")
                    return False

            except subprocess.CalledProcessError as e:
                print_error(f"mysqldump failed: {e.stderr}")
                # Clean up empty backup file
                if backup_path.exists():
                    backup_path.unlink()
                return False

    except FileNotFoundError:
        print_error("mysqldump command not found. Please install MySQL client tools.")
        print_info("On Windows: Install MySQL Command Line Tools")
        print_info("On Ubuntu/Debian: sudo apt install mysql-client")
        print_info("On macOS: brew install mysql-client")
        return False
    except Exception as e:
        print_error(f"Error creating backup: {str(e)}")
        return False


def list_backups():
    """List all available backups"""
    try:
        backup_dir = Path(__file__).parent / "backups"

        if not backup_dir.exists():
            print_info("No backup directory found.")
            return

        backup_files = list(backup_dir.glob("*.sql"))

        if not backup_files:
            print_info("No backup files found.")
            return

        print_info("Available backups:")
        for backup_file in sorted(backup_files, reverse=True):
            file_size = backup_file.stat().st_size / (1024 * 1024)  # MB
            modified_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
            print(
                f"  {backup_file.name} ({file_size:.2f} MB) - {modified_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )

    except Exception as e:
        print_error(f"Error listing backups: {str(e)}")


def restore_database(backup_file=None):
    """Restore database from backup"""
    try:
        print_header("DATABASE RESTORE")

        # List available backups
        backup_dir = Path(__file__).parent / "backups"
        if not backup_dir.exists():
            print_error("No backup directory found.")
            return False

        backup_files = list(backup_dir.glob("*.sql"))
        if not backup_files:
            print_error("No backup files found.")
            return False

        # If no specific backup file provided, let user choose
        if not backup_file:
            print_info("Available backups:")
            for i, backup_file in enumerate(sorted(backup_files, reverse=True), 1):
                file_size = backup_file.stat().st_size / (1024 * 1024)  # MB
                modified_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
                print(
                    f"  {i}. {backup_file.name} ({file_size:.2f} MB) - {modified_time.strftime('%Y-%m-%d %H:%M:%S')}"
                )

            try:
                choice = int(input("\nSelect backup to restore (number): ")) - 1
                if 0 <= choice < len(backup_files):
                    backup_file = sorted(backup_files, reverse=True)[choice]
                else:
                    print_error("Invalid selection.")
                    return False
            except ValueError:
                print_error("Invalid input.")
                return False

        # Confirm restore
        if not confirm_action(
            f"This will REPLACE the current database with backup: {backup_file.name}. Continue?"
        ):
            print_warning("Restore cancelled.")
            return False

        # Get database configuration
        db_config = get_database_config()
        if not db_config:
            print_error("Could not parse database configuration")
            return False

        # Build mysql command
        cmd = [
            "mysql",
            f"--host={db_config['host']}",
            f"--port={db_config['port']}",
            f"--user={db_config['user']}",
        ]

        # Add password if provided
        if db_config["password"]:
            cmd.append(f"--password={db_config['password']}")

        cmd.append(db_config["database"])

        print_info(f"Restoring from: {backup_file.name}")

        # Execute mysql restore
        with open(backup_file, "r", encoding="utf-8") as backup_file_handle:
            try:
                result = subprocess.run(
                    cmd,
                    stdin=backup_file_handle,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True,
                )

                print_success("Database restored successfully!")
                return True

            except subprocess.CalledProcessError as e:
                print_error(f"mysql restore failed: {e.stderr}")
                return False

    except Exception as e:
        print_error(f"Error restoring database: {str(e)}")
        return False


def cleanup_old_backups(keep_count=10):
    """Remove old backup files, keeping only the specified number"""
    try:
        backup_dir = Path(__file__).parent / "backups"

        if not backup_dir.exists():
            print_info("No backup directory found.")
            return

        backup_files = sorted(
            backup_dir.glob("*.sql"), key=lambda x: x.stat().st_mtime, reverse=True
        )

        if len(backup_files) <= keep_count:
            print_info(f"Only {len(backup_files)} backups found, no cleanup needed.")
            return

        files_to_delete = backup_files[keep_count:]

        print_info(
            f"Removing {len(files_to_delete)} old backup(s), keeping {keep_count} most recent..."
        )

        for backup_file in files_to_delete:
            backup_file.unlink()
            print_success(f"Deleted: {backup_file.name}")

        print_success(f"Cleanup completed. {keep_count} backups retained.")

    except Exception as e:
        print_error(f"Error cleaning up backups: {str(e)}")


def main():
    """Main function"""
    print_header("BFP ATTENDANCE SYSTEM - DATABASE BACKUP MANAGER")

    print("Database backup and restore utility.")
    print("\nOptions:")
    print("1. Create new backup")
    print("2. List existing backups")
    print("3. Restore from backup")
    print("4. Cleanup old backups")
    print("5. Cancel")

    try:
        choice = input("\nEnter your choice (1-5): ").strip()

        if choice == "1":
            backup_database()
        elif choice == "2":
            list_backups()
        elif choice == "3":
            restore_database()
        elif choice == "4":
            try:
                keep_count = int(
                    input("How many recent backups to keep (default 10)? ") or "10"
                )
                cleanup_old_backups(keep_count)
            except ValueError:
                print_error("Invalid number entered.")
        elif choice == "5":
            print_warning("Operation cancelled.")
        else:
            print_error("Invalid choice. Operation cancelled.")

    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user.")
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    main()
