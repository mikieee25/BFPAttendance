#!/usr/bin/env python3
"""
Migration script for:
1) user.is_active column
2) attendance unique constraint on (personnel_id, date)

Run:
    python manage/migrate_user_status_and_attendance_constraint.py
"""

import sys
from pathlib import Path

from sqlalchemy import text

# Add project and manage directories to path
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
sys.path.insert(0, str(CURRENT_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config import (  # noqa: E402
    create_app,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
)
from models import db  # noqa: E402

app = create_app()


def _column_exists(table_name: str, column_name: str) -> bool:
    result = db.session.execute(text(f"SHOW COLUMNS FROM `{table_name}`"))
    return column_name in [row[0] for row in result.fetchall()]


def _constraint_exists(table_name: str, constraint_name: str) -> bool:
    result = db.session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM information_schema.table_constraints
            WHERE table_schema = DATABASE()
              AND table_name = :table_name
              AND constraint_name = :constraint_name
            """
        ),
        {"table_name": table_name, "constraint_name": constraint_name},
    )
    return result.scalar() > 0


def _find_duplicate_attendance():
    result = db.session.execute(
        text(
            """
            SELECT personnel_id, date, COUNT(*) AS cnt
            FROM attendance
            GROUP BY personnel_id, date
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC, personnel_id ASC, date ASC
            """
        )
    )
    return result.fetchall()


def migrate():
    with app.app_context():
        try:
            print_info("Checking user.is_active column...")
            if not _column_exists("user", "is_active"):
                db.session.execute(
                    text(
                        "ALTER TABLE `user` ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"
                    )
                )
                db.session.commit()
                print_success("Added `user.is_active` column")
            else:
                print_info("`user.is_active` already exists")

            updated = db.session.execute(
                text("UPDATE `user` SET is_active = TRUE WHERE is_active IS NULL")
            )
            if updated.rowcount > 0:
                db.session.commit()
                print_success(f"Normalized {updated.rowcount} user rows with NULL is_active")

            constraint_name = "uq_attendance_personnel_date"
            print_info(f"Checking attendance constraint `{constraint_name}`...")
            if _constraint_exists("attendance", constraint_name):
                print_info(f"Constraint `{constraint_name}` already exists")
                return

            duplicates = _find_duplicate_attendance()
            if duplicates:
                print_error(
                    "Cannot add unique constraint because duplicate attendance rows exist."
                )
                print_warning("Resolve duplicates first, then rerun this script.")
                for row in duplicates[:20]:
                    print(
                        f"  personnel_id={row.personnel_id}, date={row.date}, duplicates={row.cnt}"
                    )
                if len(duplicates) > 20:
                    print_warning(f"... and {len(duplicates) - 20} more duplicate groups")
                return

            db.session.execute(
                text(
                    "ALTER TABLE attendance ADD CONSTRAINT uq_attendance_personnel_date UNIQUE (personnel_id, date)"
                )
            )
            db.session.commit()
            print_success("Added attendance unique constraint (personnel_id, date)")

        except Exception as e:
            db.session.rollback()
            print_error(f"Migration failed: {e}")
            raise


if __name__ == "__main__":
    print_header("MIGRATION: USER STATUS + ATTENDANCE UNIQUE CONSTRAINT")
    migrate()
