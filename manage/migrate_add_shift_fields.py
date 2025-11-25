"""
Database Migration Script for BFP Attendance System
Adds new columns to the personnel table for shift scheduling and soft delete functionality.

Run this script to update your database schema:
    python manage/migrate_add_shift_fields.py

This migration adds:
- is_active: Boolean field for soft delete (default True)
- shift_start_time: Time field for shift start
- shift_end_time: Time field for shift end
- is_shifting: Boolean field for 15-day rotation schedule
- shift_start_date: Date field for when shift cycle started
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
    """Add new columns to personnel table."""
    with app.app_context():
        try:
            # Check if columns already exist
            result = db.session.execute(text("SHOW COLUMNS FROM personnel"))
            existing_columns = [row[0] for row in result.fetchall()]
            
            migrations_needed = []
            
            # Check and add is_active column
            if 'is_active' not in existing_columns:
                migrations_needed.append(
                    "ALTER TABLE personnel ADD COLUMN is_active BOOLEAN DEFAULT TRUE"
                )
                print("✓ Will add 'is_active' column")
            else:
                print("○ 'is_active' column already exists")
            
            # Check and add shift_start_time column
            if 'shift_start_time' not in existing_columns:
                migrations_needed.append(
                    "ALTER TABLE personnel ADD COLUMN shift_start_time TIME NULL"
                )
                print("✓ Will add 'shift_start_time' column")
            else:
                print("○ 'shift_start_time' column already exists")
            
            # Check and add shift_end_time column
            if 'shift_end_time' not in existing_columns:
                migrations_needed.append(
                    "ALTER TABLE personnel ADD COLUMN shift_end_time TIME NULL"
                )
                print("✓ Will add 'shift_end_time' column")
            else:
                print("○ 'shift_end_time' column already exists")
            
            # Check and add is_shifting column
            if 'is_shifting' not in existing_columns:
                migrations_needed.append(
                    "ALTER TABLE personnel ADD COLUMN is_shifting BOOLEAN DEFAULT FALSE"
                )
                print("✓ Will add 'is_shifting' column")
            else:
                print("○ 'is_shifting' column already exists")
            
            # Check and add shift_start_date column
            if 'shift_start_date' not in existing_columns:
                migrations_needed.append(
                    "ALTER TABLE personnel ADD COLUMN shift_start_date DATE NULL"
                )
                print("✓ Will add 'shift_start_date' column")
            else:
                print("○ 'shift_start_date' column already exists")
            
            # Execute migrations
            if migrations_needed:
                print(f"\nExecuting {len(migrations_needed)} migration(s)...")
                for sql in migrations_needed:
                    db.session.execute(text(sql))
                db.session.commit()
                print("\n✅ Migration completed successfully!")
            else:
                print("\n✅ No migrations needed - all columns already exist.")
            
            # Update existing records to have is_active = True
            result = db.session.execute(
                text("UPDATE personnel SET is_active = TRUE WHERE is_active IS NULL")
            )
            if result.rowcount > 0:
                db.session.commit()
                print(f"✓ Updated {result.rowcount} personnel records to active status")
            
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Migration failed: {str(e)}")
            raise


if __name__ == "__main__":
    print("=" * 50)
    print("BFP Attendance System - Database Migration")
    print("Adding shift schedule and soft delete fields")
    print("=" * 50)
    print()
    migrate()
    print()
    print("=" * 50)
