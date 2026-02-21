"""
Migration script: Add ON_LEAVE to AttendanceStatus enum and is_kiosk column to User table.

Run with:
    python migrate_kiosk_onleave.py
"""

import os
import sys
import logging

from dotenv import load_dotenv
import pymysql

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_connection():
    db_url = os.environ.get(
        "DATABASE_URL",
        "mysql+pymysql://root:@localhost/bfp_sorsogon_attendance",
    )
    # Parse mysql+pymysql://user:pass@host/dbname
    stripped = db_url.replace("mysql+pymysql://", "")
    userinfo, rest = stripped.split("@", 1)
    host_and_db = rest.split("/", 1)
    host = host_and_db[0]
    database = host_and_db[1] if len(host_and_db) > 1 else ""

    if ":" in userinfo:
        user, password = userinfo.split(":", 1)
    else:
        user = userinfo
        password = ""

    # Handle host:port
    port = 3306
    if ":" in host:
        host, port_str = host.rsplit(":", 1)
        port = int(port_str)

    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        autocommit=False,
    )


def run_migration():
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # ------------------------------------------------------------------ #
        # 1. Add ON_LEAVE to the attendance.status ENUM column                #
        # ------------------------------------------------------------------ #
        logger.info("Checking attendance.status column definition …")

        cursor.execute(
            """
            SELECT COLUMN_TYPE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'attendance'
              AND COLUMN_NAME  = 'status'
            """
        )
        row = cursor.fetchone()
        if row is None:
            logger.warning("Column attendance.status not found – skipping.")
        else:
            col_type: str = row[0]  # e.g. "enum('PRESENT','LATE','ABSENT')"
            if "ON_LEAVE" in col_type:
                logger.info("  ON_LEAVE already present in enum – skipping.")
            else:
                logger.info("  Adding ON_LEAVE to attendance.status enum …")
                cursor.execute(
                    """
                    ALTER TABLE attendance
                    MODIFY COLUMN status
                        ENUM('PRESENT','LATE','ABSENT','ON_LEAVE')
                        NULL
                    """
                )
                logger.info("  Done.")

        # ------------------------------------------------------------------ #
        # 2. Add is_kiosk column to the user table                            #
        # ------------------------------------------------------------------ #
        logger.info("Checking user.is_kiosk column …")

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'user'
              AND COLUMN_NAME  = 'is_kiosk'
            """
        )
        (count,) = cursor.fetchone()
        if count:
            logger.info("  is_kiosk column already exists – skipping.")
        else:
            logger.info("  Adding is_kiosk column to user table …")
            cursor.execute(
                """
                ALTER TABLE `user`
                ADD COLUMN is_kiosk TINYINT(1) NOT NULL DEFAULT 0
                    AFTER is_active
                """
            )
            logger.info("  Done.")

        conn.commit()
        logger.info("Migration completed successfully.")

    except Exception as exc:
        conn.rollback()
        logger.error("Migration failed: %s", exc)
        sys.exit(1)

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    run_migration()
