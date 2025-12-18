"""
Database Migration Script for BFP Attendance System
Adds shift_duration_days column to the personnel table for custom rotation schedules.

Run this script to update your database schema:
    python manage/migrate_add_shift_duration.py

This migration adds:
- shift_duration_days: Integer field for custom shift duration (default 15)
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app import create_app
from models import db

# Create the Flask app
app = create_app()


def migrate():
    """Add shift_duration_days column to personnel table."""
    with app.app_context():
        try:
            # Check if column already exists
            result = db.session.execute(text("SHOW COLUMNS FROM personnel"))
            existing_columns = [row[0] for row in result.fetchall()]

            if "shift_duration_days" not in existing_columns:
                print("✓ Adding 'shift_duration_days' column...")
                db.session.execute(
                    text(
                        "ALTER TABLE personnel ADD COLUMN shift_duration_days INT DEFAULT 15"
                    )
                )
                db.session.commit()
                print("✅ Migration completed successfully!")

                # Update existing shifting personnel to have default 15 days
                result = db.session.execute(
                    text(
                        "UPDATE personnel SET shift_duration_days = 15 WHERE is_shifting = TRUE AND shift_duration_days IS NULL"
                    )
                )
                if result.rowcount > 0:
                    db.session.commit()
                    print(
                        f"✓ Updated {result.rowcount} existing shifting personnel with default 15-day duration"
                    )
            else:
                print(
                    "○ 'shift_duration_days' column already exists - no migration needed"
                )

        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Migration failed: {str(e)}")
            raise


if __name__ == "__main__":
    print("=" * 50)
    print("BFP Attendance System - Database Migration")
    print("Adding shift_duration_days field")
    print("=" * 50)
    print()
    migrate()
    print()
    print("=" * 50)
