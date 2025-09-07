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


def run_script(script_name):
    """Run a management script"""
    try:
        script_path = Path(__file__).parent / script_name

        if not script_path.exists():
            print_error(f"Script not found: {script_name}")
            return False

        print_info(f"Running {script_name}...")
        print("=" * 60)

        # Run the script using the current Python interpreter
        result = subprocess.run([sys.executable, str(script_path)], check=False)

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
    print("  4. Migrate/Update database schema")

    print(f"\n{Colors.WARNING}Data Management:{Colors.ENDC}")
    print("  5. Clean all database data")
    print("  6. Clean personnel data only")
    print("  7. Generate fake data for testing")

    print(f"\n{Colors.OKCYAN}Utilities:{Colors.ENDC}")
    print("  8. List all available scripts")
    print("  9. Show this menu")
    print("  0. Exit")

    print(
        f"\n{Colors.BOLD}💡 Tip:{Colors.ENDC} These scripts are for development/testing only!"
    )
    print(
        f"{Colors.WARNING}⚠️  Warning: Data cleaning operations cannot be undone!{Colors.ENDC}"
    )


def list_available_scripts():
    """List all available management scripts"""
    print_header("AVAILABLE MANAGEMENT SCRIPTS")

    scripts = [
        ("config.py", "Base configuration and utilities"),
        ("migrate_database.py", "Database schema creation and migration"),
        ("backup_database.py", "Database backup and restore"),
        ("clean_database.py", "Clean all database data"),
        ("clean_personnel.py", "Clean personnel data only"),
        ("generate_fake_data.py", "Generate fake data for testing"),
        ("manage.py", "This main management console"),
    ]

    print_info("Management scripts in this directory:")
    for script, description in scripts:
        script_path = Path(__file__).parent / script
        status = "✓" if script_path.exists() else "✗"
        print(f"  {status} {script:<25} - {description}")

    print(f"\n{Colors.OKBLUE}Usage:{Colors.ENDC}")
    print("  python manage.py              - Run this management console")
    print("  python script_name.py         - Run individual script directly")

    print(f"\n{Colors.WARNING}Requirements:{Colors.ENDC}")
    print("  • Python 3.7+")
    print("  • Flask and dependencies")
    print("  • MySQL/MariaDB server")
    print("  • mysqldump/mysql client tools (for backups)")
    print("  • faker library (for fake data generation)")


def check_requirements():
    """Check if required dependencies are available"""
    print_info("Checking requirements...")

    # Check Python modules
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

    # Check requirements
    if not check_requirements():
        print_error("Please install missing dependencies before continuing.")
        return

    while True:
        try:
            print()  # Add spacing
            show_menu()
            choice = input(
                f"\n{Colors.BOLD}Enter your choice (0-9): {Colors.ENDC}"
            ).strip()

            if choice == "1":
                run_script("migrate_database.py")
            elif choice == "2":
                print_info(
                    "This will initialize a fresh database with schema and default users."
                )
                if input("Continue? (y/N): ").lower() in ["y", "yes"]:
                    run_script("migrate_database.py")
            elif choice == "3":
                run_script("backup_database.py")
            elif choice == "4":
                run_script("migrate_database.py")
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
                list_available_scripts()
            elif choice == "9":
                continue  # Just show menu again
            elif choice == "0":
                print_success("Goodbye!")
                break
            else:
                print_error("Invalid choice. Please try again.")

            if choice != "9":
                input(f"\n{Colors.OKCYAN}Press Enter to continue...{Colors.ENDC}")

        except KeyboardInterrupt:
            print_warning("\nExiting...")
            break
        except Exception as e:
            print_error(f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    main()
