# BFP Attendance System - Management Scripts

This directory contains development and management scripts for the BFP Attendance System. These scripts are **NOT** part of the web application and are intended for development, testing, and database administration purposes only.

## 🚀 Quick Start

1. **Install additional dependencies:**

   ```bash
   pip install -r requirements-dev.txt
   ```

2. **Run the management console:**
   ```bash
   python manage.py
   ```

## 📋 Available Scripts

### 🏠 Main Console

- **`manage.py`** - Interactive management console with menu-driven interface

### 🗄️ Database Management

- **`migrate_database.py`** - Database schema creation, migration, and initialization
- **`migrate_user_status_and_attendance_constraint.py`** - Adds `user.is_active` and attendance uniqueness constraint
- **`migrate_add_indexes.py`** - Adds performance indexes for common queries
- **`backup_database.py`** - Database backup and restore operations
- **`clean_database.py`** - Clean all database data (⚠️ **DESTRUCTIVE**)
- **`clean_personnel.py`** - Clean personnel data only (preserves admin users)
- **`clean_attendance.py`** - Clean attendance records only (preserves personnel and face data)

### 🎭 Data Generation

- **`generate_fake_data.py`** - Generate realistic fake data for testing
  - Uses Filipino names and localization (PH)
  - Creates 30 personnel per station by default
  - Generates 90 days of attendance history
  - Creates face data entries and activity logs

### ⚙️ Configuration

- **`config.py`** - Base configuration and utility functions for all scripts

## 🎯 Common Use Cases

### Fresh Database Setup

```bash
python manage.py
# Choose option 2: Initialize fresh database
```

### Generate Test Data

```bash
python generate_fake_data.py
# Or use manage.py option 7
```

### Clean Development Data

```bash
python clean_personnel.py  # Keeps admin users
# Or
python clean_database.py   # Removes everything
```

### Backup Before Major Changes

```bash
python backup_database.py
# Or use manage.py option 3
```

## ⚠️ Important Warnings

### 🔴 DESTRUCTIVE OPERATIONS

- **`clean_database.py`** - Deletes ALL data
- **`clean_personnel.py`** - Deletes all personnel and related data
- **Database restore** - Replaces current database

### 🔐 Security Notes

- Scripts create default passwords: `admin123` and `station123`
- **ALWAYS** change default passwords in production
- These scripts should **NEVER** be deployed to production servers

### 📊 Data Considerations

- Fake data uses Filipino names and Philippine localization
- Generated attendance follows realistic patterns (work hours, weekends off)
- Face data entries are placeholder (no actual face encodings)

## 🛠️ Individual Script Usage

### Database Migration

```bash
python migrate_database.py
# Options:
# 1. Check database status
# 2. Initialize fresh database
# 3. Create schema only
# 4. Create admin user
# 5. Create station users
```

```bash
python migrate_user_status_and_attendance_constraint.py
```

### Fake Data Generation

```bash
python generate_fake_data.py
# Options:
# 1. Standard dataset (30 personnel/station)
# 2. Custom count
# 3. Show current data
```

### Database Backup

```bash
python backup_database.py
# Options:
# 1. Create backup
# 2. List backups
# 3. Restore from backup
# 4. Cleanup old backups
```

## 🔧 Technical Details

### Database Configuration

Scripts read database configuration from:

1. `DATABASE_URL` environment variable
2. Default: `mysql+pymysql://root:@localhost/bfp_sorsogon_attendance`

### Generated Data Structure

- **Stations**: Central, Talisay, Bacon, Abuyog
- **Personnel per station**: 30 (configurable)
- **Ranks**: Fire Officer I-III, Senior Fire Officer I-IV, Chief Fire Officer, Fire Chief
- **Attendance history**: 90 days (configurable)
- **Face data**: 2-4 entries per personnel

### File Structure

```
manage/
├── config.py              # Base configuration
├── manage.py              # Main console
├── migrate_database.py    # Schema management
├── migrate_user_status_and_attendance_constraint.py  # User status + attendance constraint migration
├── migrate_add_indexes.py # Performance indexes
├── backup_database.py     # Backup/restore
├── clean_database.py      # Data cleaning
├── clean_personnel.py     # Personnel cleaning
├── generate_fake_data.py  # Fake data generation
├── requirements-dev.txt   # Additional dependencies
├── README.md             # This file
└── backups/              # Backup files (auto-created)
```

## 🚨 Troubleshooting

### Common Issues

1. **Import Errors**

   ```bash
   pip install -r requirements-dev.txt
   ```

2. **Database Connection Errors**

   - Check MySQL server is running
   - Verify database credentials
   - Ensure database exists

3. **mysqldump/mysql not found**

   - Install MySQL client tools
   - Add MySQL bin to PATH

4. **Permission Errors**
   - Check MySQL user permissions
   - Ensure write access to backup directory

### Dependencies

- **Required**: flask, flask-sqlalchemy, pymysql
- **Optional**: faker (for fake data), colorama (better colors)
- **System**: mysql client tools (for backups)

## 📝 Development Notes

### Adding New Scripts

1. Import from `config.py` for consistent formatting
2. Use the provided color/print functions
3. Follow the error handling patterns
4. Add to main menu in `manage.py`

### Database Schema Changes

1. Update models in main application
2. Test with `migrate_database.py`
3. Update fake data generation if needed
4. Create migration scripts for production

## 🔒 Security Reminders

- ❌ **Never** include these scripts in production deployments
- ❌ **Never** use default passwords in production
- ❌ **Never** run destructive scripts on production data
- ✅ **Always** backup before major operations
- ✅ **Always** test scripts on development data first
- ✅ **Always** change default credentials after initialization

---

**For production database operations, use proper database migration tools and follow your organization's change management procedures.**
