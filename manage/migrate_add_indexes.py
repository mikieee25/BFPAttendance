#!/usr/bin/env python3
"""
Add performance indexes for key tables.
"""

import logging
from sqlalchemy import text

from config import db, get_app_context, print_error, print_header, print_info, print_success, print_warning

logger = logging.getLogger(__name__)


def _index_exists(table_name: str, index_name: str) -> bool:
    result = db.session.execute(
        text(
            """
            SELECT COUNT(1)
            FROM information_schema.statistics
            WHERE table_schema = DATABASE()
              AND table_name = :table_name
              AND index_name = :index_name
            """
        ),
        {"table_name": table_name, "index_name": index_name},
    )
    return result.scalar() > 0


def _create_index(table_name: str, index_name: str, column_name: str) -> None:
    if _index_exists(table_name, index_name):
        print_info(f"Index already exists: {index_name}")
        return
    db.session.execute(
        text(f"CREATE INDEX {index_name} ON {table_name} ({column_name})")
    )
    print_success(f"Created index: {index_name}")


def main():
    print_header("ADDING PERFORMANCE INDEXES")
    try:
        with get_app_context():
            _create_index("activity_log", "idx_activity_log_timestamp", "timestamp")
            _create_index("pending_attendance", "idx_pending_attendance_date", "date")
            _create_index("personnel", "idx_personnel_station_id", "station_id")
            db.session.commit()
            print_success("Index migration completed.")
    except Exception as exc:
        db.session.rollback()
        print_error(f"Index migration failed: {exc}")
        logger.exception("Index migration failed")


if __name__ == "__main__":
    main()
