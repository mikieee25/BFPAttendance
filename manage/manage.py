#!/usr/bin/env python3
"""
Main Management Script
Central menu for all database management operations.
"""
import sys
import subprocess
from pathlib import Path
from config import (
    print_success,
    print_error,
    print_warning,
    print_info,
    print_header,
    Colors,
)


def run_script(script_name, extra_args=None):
    """Run a management script"""
    try:
        script_path = Path(__file__).parent / script_name

        if not script_path.exists():
            print_error(f"Script not found: {script_name}")
            return False

        print_info(f"Running {script_name}...")
        print("=" * 60)

        cmd = [sys.executable, str(script_path)]
        if extra_args:
            cmd.extend(extra_args)

        result = subprocess.run(cmd, check=False)

        print("=" * 60)
        if result.returncode == 0:
            print_success(f"{script_name} completed successfully")
        else:
            print_warning(f"{script_name} exited with code {result.returncode}")

        return result.returncode == 0

    except Exception as e:
        print_error(f"Error running {script_name}: {str(e)}")
        return False


def show_menu():
    """Display the main management menu"""
    print_header("BFP ATTENDANCE SYSTEM - MANAGEMENT CONSOLE")

    print(f"{Colors.OKBLUE}Database Management:{Colors.ENDC}")
    print("  1. Check database status")
    print("  2. Initialize fresh database")
    print("  3. Create database backup")
    print("  4. Run latest migration (kiosk + ON_LEAVE)")

    print(f"\n{Colors.WARNING}Data Management:{Colors.ENDC}")
    print("  5. Clean all database data")
    print("  6. Clean personnel data only")
    print("  7. Generate fake data for testing")
    print("  8. Clean attendance records only")

    print(f"\n{Colors.OKCYAN}Maintenance:{Colors.ENDC}")
    print("  9. Audit DB columns vs models (dry-run)")
    print(" 10. Audit + DROP orphaned DB columns")
    print(" 11. List all available scripts")
    print("  0. Exit")

    print(
        f"\n{Colors.BOLD}💡 Tip:{Colors.ENDC} Run individual scripts directly for full options."
    )
    print(
        f"{Colors.WARNING}⚠️  Warning: Data cleaning and DROP operations cannot be undone!{Colors.ENDC}"
    )


def list_available_scripts():
    """List all available management scripts"""
    print_header("AVAILABLE MANAGEMENT SCRIPTS")

    scripts = [
        ("config.py",                   "Base configuration and utilities"),
        ("migrate_kiosk_onleave.py",     "Add ON_LEAVE status + is_kiosk column (latest migration)"),
        ("backup_database.py",           "Database backup and restore"),
        ("clean_database.py",            "Clean ALL database data"),
        ("clean_personnel.py",           "Clean personnel data only"),
        ("clean_attendance.py",          "Clean attendance records only"),
        ("generate_fake_data.py",        "Generate fake data for testing"),
        ("cleanup_db_columns.py",        "Audit / drop DB columns not in models"),
        ("manage.py",                    "This main management console"),
    ]

    print_info("Management scripts in this directory:")
    for script, description in scripts:
        script_path = Path(__file__).parent / script
        status = "✓" if script_path.exists() else "✗"
        print(f"  {status} {script:<40} - {description}")

    print(f"\n{Colors.OKBLUE}Usage:{Colors.ENDC}")
    print("  python manage/manage.py                        — interactive console")
    print("  python manage/cleanup_db_columns.py            — dry-run audit")
    print("  python manage/cleanup_db_columns.py --drop     — drop with confirmation")
    print("  python manage/migrate_kiosk_onleave.py         — run latest migration")


def check_requirements():
    """Check if required dependencies are available"""
    print_info("Checking requirements...")

    required_modules = ["flask", "flask_sqlalchemy", "pymysql"]
    optional_modules = ["faker"]

    missing_required = []
    missing_optional = []

    for module in required_modules:
        try:
            __import__(module)
            print_success(f"✓ {module}")
        except ImportError:
            missing_required.append(module)
            print_error(f"✗ {module} (required)")

    for module in optional_modules:
        try:
            __import__(module)
            print_success(f"✓ {module}")
        except ImportError:
            missing_optional.append(module)
            print_warning(f"⚠ {module} (optional)")

    if missing_required:
        print_error(f"Missing required modules: {', '.join(missing_required)}")
        print_info("Install with: pip install " + " ".join(missing_required))
        return False

    if missing_optional:
        print_warning(f"Missing optional modules: {', '.join(missing_optional)}")
        print_info("Install with: pip install " + " ".join(missing_optional))

    print_success("All required dependencies are available!")
    return True


def main():
    """Main function"""
    print_header("BFP ATTENDANCE SYSTEM MANAGEMENT CONSOLE")

    if not check_requirements():
        print_error("Please install missing dependencies before continuing.")
        return

    while True:
        try:
            print()
            show_menu()
            choice = input(
                f"\n{Colors.BOLD}Enter your choice (0-11): {Colors.ENDC}"
            ).strip()

            if choice == "1":
                run_script("migrate_kiosk_onleave.py")  # also prints DB status via migration checks
            elif choice == "2":
                print_info("This will initialize a fresh database with schema and default users.")
                if input("Continue? (y/N): ").lower() in ["y", "yes"]:
                    # Use Flask's db.create_all via a quick inline call
                    try:
                        import importlib, os, sys
                        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
                        from app import create_app
                        from models import db
                        app = create_app()
                        with app.app_context():
                            db.create_all()
                        print_success("Database schema created / verified.")
                    except Exception as exc:
                        print_error(f"Failed: {exc}")
            elif choice == "3":
                run_script("backup_database.py")
            elif choice == "4":
                run_script("migrate_kiosk_onleave.py")
            elif choice == "5":
                print_warning("This will delete ALL data from the database!")
                if input("Are you sure? (y/N): ").lower() in ["y", "yes"]:
                    run_script("clean_database.py")
            elif choice == "6":
                print_warning("This will delete all personnel and related data!")
                if input("Are you sure? (y/N): ").lower() in ["y", "yes"]:
                    run_script("clean_personnel.py")
            elif choice == "7":
                run_script("generate_fake_data.py")
            elif choice == "8":
                print_warning("This will delete attendance records (personnel/face data kept).")
                if input("Continue? (y/N): ").lower() in ["y", "yes"]:
                    run_script("clean_attendance.py")
            elif choice == "9":
                run_script("cleanup_db_columns.py")
            elif choice == "10":
                print_warning("This will DROP columns from the live database that are not in the models.")
                print_warning("Take a backup first! (option 3)")
                if input("Proceed to column cleanup with --drop? (y/N): ").lower() in ["y", "yes"]:
                    run_script("cleanup_db_columns.py", extra_args=["--drop"])
            elif choice == "11":
                list_available_scripts()
            elif choice == "0":
                print_success("Goodbye!")
                break
            else:
                print_error("Invalid choice. Please try again.")
                continue

            input(f"\n{Colors.OKCYAN}Press Enter to continue...{Colors.ENDC}")

        except KeyboardInterrupt:
            print_warning("\nExiting...")
            break
        except Exception as e:
            print_error(f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    main()
