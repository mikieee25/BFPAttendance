#!/usr/bin/env python3
"""
manage/cleanup_db_columns.py
────────────────────────────
Audits every table in the live database against the SQLAlchemy models defined
in models.py and reports (or drops) any columns that are present in the database
but no longer declared in the models.

Usage
-----
    # Dry-run — just show what would be removed (safe, default)
    python manage/cleanup_db_columns.py

    # Actually drop orphaned columns after per-column confirmation
    python manage/cleanup_db_columns.py --drop

    # Drop without asking per column (still asks once before starting)
    python manage/cleanup_db_columns.py --drop --yes

Exit codes
----------
    0  clean run (no orphans found, or all requested actions succeeded)
    1  one or more errors occurred
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# ── path setup ────────────────────────────────────────────────────────────────
MANAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = MANAGE_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Pretty-print helpers
# ─────────────────────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[31m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
DIM    = "\033[2m"


def _c(colour: str, text: str) -> str:
    """Wrap text in ANSI colour codes (no-op when stdout is not a tty)."""
    if not sys.stdout.isatty():
        return text
    return f"{colour}{text}{RESET}"


def header(text: str) -> None:
    bar = "─" * 70
    print(f"\n{_c(BOLD + CYAN, bar)}")
    print(f"{_c(BOLD + CYAN, '  ' + text)}")
    print(f"{_c(BOLD + CYAN, bar)}\n")


def ok(text: str) -> None:
    print(f"  {_c(GREEN, '✓')}  {text}")


def warn(text: str) -> None:
    print(f"  {_c(YELLOW, '!')}  {text}")


def err(text: str) -> None:
    print(f"  {_c(RED, '✗')}  {text}")


def info(text: str) -> None:
    print(f"  {_c(CYAN, '·')}  {text}")


def dim(text: str) -> None:
    print(f"     {_c(DIM, text)}")


# ─────────────────────────────────────────────────────────────────────────────
# DB connection (raw pymysql — no Flask needed for the audit phase)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_db_url(url: str) -> dict:
    """Parse mysql+pymysql://user:pass@host[:port]/dbname into a kwargs dict."""
    stripped = url.replace("mysql+pymysql://", "").replace("mysql://", "")
    userinfo, rest = stripped.split("@", 1)
    host_part, database = rest.split("/", 1)

    user = password = ""
    if ":" in userinfo:
        user, password = userinfo.split(":", 1)
    else:
        user = userinfo

    host = host_part
    port = 3306
    if ":" in host_part:
        host, port_str = host_part.rsplit(":", 1)
        port = int(port_str)

    return dict(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        autocommit=False,
    )


def get_connection():
    import pymysql
    url = os.environ.get(
        "DATABASE_URL",
        "mysql+pymysql://root:@localhost/bfp_sorsogon_attendance",
    )
    kwargs = _parse_db_url(url)
    info(f"Connecting → {kwargs['user']}@{kwargs['host']}:{kwargs['port']}/{kwargs['database']}")
    return pymysql.connect(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Model introspection (via SQLAlchemy metadata — no DB connection needed)
# ─────────────────────────────────────────────────────────────────────────────

def get_model_columns() -> dict[str, set[str]]:
    """
    Returns {table_name: {col_name, ...}} for every SQLAlchemy model in
    models.py, using the ORM metadata (not the live DB).
    """
    # We import models inside a minimal Flask app context so that db.metadata
    # is fully populated without actually connecting to MySQL.
    from flask import Flask
    import sqlalchemy as sa

    app = Flask(__name__, instance_relative_config=False)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "audit-only"
    app.config["WTF_CSRF_ENABLED"] = False

    # Patch away any heavy startup work (face models, etc.)
    import unittest.mock as mock
    with mock.patch("face_rec_module.face_service.cleanup_old_attendance_images"):
        from models import db as _db
        _db.init_app(app)
        with app.app_context():
            _db.create_all()   # creates tables in in-memory SQLite
            result: dict[str, set[str]] = {}
            for table_name, table in _db.metadata.tables.items():
                result[table_name] = {col.name for col in table.columns}

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Live DB introspection
# ─────────────────────────────────────────────────────────────────────────────

def get_db_columns(cursor) -> dict[str, set[str]]:
    """Returns {table_name: {col_name, ...}} from the live MySQL database."""
    cursor.execute("SHOW TABLES")
    tables = [row[0] for row in cursor.fetchall()]

    result: dict[str, set[str]] = {}
    for table in tables:
        cursor.execute(f"SHOW COLUMNS FROM `{table}`")
        result[table] = {row[0] for row in cursor.fetchall()}

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Audit logic
# ─────────────────────────────────────────────────────────────────────────────

def audit(
    db_cols: dict[str, set[str]],
    model_cols: dict[str, set[str]],
) -> dict[str, dict[str, set[str]]]:
    """
    Returns a per-table diff report:
        {
            table_name: {
                "orphaned": {cols in DB but NOT in model},
                "phantom":  {cols in model but NOT in DB},
            }
        }
    Tables that exist only in the DB (no corresponding model) are flagged too.
    """
    report: dict[str, dict[str, set[str]]] = {}

    all_tables = set(db_cols) | set(model_cols)

    for table in sorted(all_tables):
        db_set    = db_cols.get(table, set())
        model_set = model_cols.get(table, set())

        orphaned = db_set - model_set    # in DB, not in model  → candidates to drop
        phantom  = model_set - db_set   # in model, not in DB  → schema out of date

        if orphaned or phantom:
            report[table] = {"orphaned": orphaned, "phantom": phantom}

    return report


# ─────────────────────────────────────────────────────────────────────────────
# Drop helpers
# ─────────────────────────────────────────────────────────────────────────────

_PROTECTED_COLUMNS: set[str] = set()
"""
Columns that should never be dropped even if they appear orphaned.
Add any column names here as a safeguard.
"""


def drop_column(cursor, conn, table: str, column: str) -> bool:
    """Issues ALTER TABLE … DROP COLUMN and commits. Returns True on success."""
    sql = f"ALTER TABLE `{table}` DROP COLUMN `{column}`"
    try:
        cursor.execute(sql)
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        err(f"Failed to drop `{table}`.`{column}`: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit (and optionally drop) database columns not defined in models.py.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop orphaned columns after confirmation (default: dry-run only).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip per-column confirmation prompts when used with --drop.",
    )
    args = parser.parse_args()

    # ── header ────────────────────────────────────────────────────────────────
    header("BFP Attendance System — DB Column Cleanup")
    if args.drop:
        warn("Running in DROP mode — orphaned columns will be removed from the database.")
    else:
        info("Running in DRY-RUN mode — no changes will be made (pass --drop to remove).")

    errors = 0

    # ── collect model column map ───────────────────────────────────────────────
    print()
    info("Reading SQLAlchemy model definitions …")
    try:
        model_cols = get_model_columns()
    except Exception as exc:
        err(f"Could not load models: {exc}")
        logger.exception("model load error")
        return 1

    ok(f"Models loaded — {len(model_cols)} table(s) defined")
    for t, cols in sorted(model_cols.items()):
        dim(f"{t}: {', '.join(sorted(cols))}")

    # ── collect live DB column map ─────────────────────────────────────────────
    print()
    info("Inspecting live database …")
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        db_cols = get_db_columns(cursor)
    except Exception as exc:
        err(f"Database connection failed: {exc}")
        logger.exception("db connection error")
        return 1

    ok(f"Database read — {len(db_cols)} table(s) found")
    for t, cols in sorted(db_cols.items()):
        dim(f"{t}: {', '.join(sorted(cols))}")

    # ── diff ───────────────────────────────────────────────────────────────────
    print()
    info("Comparing …")
    report = audit(db_cols, model_cols)

    if not report:
        header("Result: database is clean ✓")
        ok("Every column in the database matches the SQLAlchemy models.")
        ok("Nothing to remove.")
        cursor.close()
        conn.close()
        return 0

    # ── print report ──────────────────────────────────────────────────────────
    header(f"Differences found in {len(report)} table(s)")

    orphaned_total = 0
    phantom_total  = 0

    for table, diff in sorted(report.items()):
        orphaned = diff["orphaned"]
        phantom  = diff["phantom"]

        print(f"  {_c(BOLD, table)}")

        if orphaned:
            orphaned_total += len(orphaned)
            for col in sorted(orphaned):
                tag = _c(RED, "[ORPHANED]")
                note = _c(DIM, "← in DB, not in model")
                prot = _c(YELLOW, " [PROTECTED — will not drop]") if col in _PROTECTED_COLUMNS else ""
                print(f"    {tag}  {col}{prot}  {note}")

        if phantom:
            phantom_total += len(phantom)
            for col in sorted(phantom):
                tag  = _c(YELLOW, "[PHANTOM] ")
                note = _c(DIM, "← in model, not in DB (run migrations)")
                print(f"    {tag}  {col}  {note}")

        print()

    print(f"  {_c(BOLD, 'Summary')}")
    info(f"Orphaned columns (in DB, not in model) : {_c(RED, str(orphaned_total))}")
    info(f"Phantom  columns (in model, not in DB) : {_c(YELLOW, str(phantom_total))}")

    if phantom_total:
        print()
        warn("Phantom columns mean the live database is behind the models.")
        warn("Run the appropriate migration script(s) to add them.")

    # ── optional drop phase ───────────────────────────────────────────────────
    if not args.drop:
        print()
        info("Dry-run complete. Re-run with --drop to remove orphaned columns.")
        cursor.close()
        conn.close()
        return 0 if orphaned_total == 0 else 0  # dry-run always exits 0

    if orphaned_total == 0:
        print()
        ok("No orphaned columns to drop.")
        cursor.close()
        conn.close()
        return 0

    # Collect drop candidates (exclude protected)
    to_drop: list[tuple[str, str]] = []
    for table, diff in sorted(report.items()):
        for col in sorted(diff["orphaned"]):
            if col not in _PROTECTED_COLUMNS:
                to_drop.append((table, col))

    if not to_drop:
        print()
        ok("All orphaned columns are protected — nothing to drop.")
        cursor.close()
        conn.close()
        return 0

    # ── safety confirmation ───────────────────────────────────────────────────
    print()
    warn(f"About to DROP {len(to_drop)} column(s) from the live database.")
    warn("This action is IRREVERSIBLE. Take a backup first if you haven't already.")
    print()

    if not args.yes:
        try:
            answer = input("  Type  yes  to proceed: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            warn("Cancelled.")
            cursor.close()
            conn.close()
            return 0

        if answer != "yes":
            warn("Cancelled — no changes made.")
            cursor.close()
            conn.close()
            return 0

    # ── execute drops ─────────────────────────────────────────────────────────
    header("Dropping orphaned columns")
    dropped = 0

    for table, col in to_drop:
        if not args.yes:
            try:
                ans = input(f"  DROP `{table}`.`{col}`? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                warn("Interrupted — stopping.")
                break
            if ans != "y":
                dim(f"Skipped `{table}`.`{col}`")
                continue

        success = drop_column(cursor, conn, table, col)
        if success:
            ok(f"Dropped  `{table}`.`{col}`")
            dropped += 1
        else:
            errors += 1

    # ── final summary ─────────────────────────────────────────────────────────
    print()
    header("Done")
    ok(f"Columns dropped : {dropped}")
    if errors:
        err(f"Errors          : {errors}")
    if dropped < len(to_drop):
        info(f"Skipped         : {len(to_drop) - dropped - errors}")

    cursor.close()
    conn.close()
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
