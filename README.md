# BFP Sorsogon Attendance Management System

A web-based attendance management system for the Bureau of Fire Protection (BFP) Sorsogon Province. The system provides role-based access for multiple stations, personnel management, automated face recognition attendance capture, and reporting tools.

---

## Table of Contents

- [System Overview](#system-overview)
- [Technology Stack](#technology-stack)
- [Directory Structure](#directory-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [Windows](#windows)
  - [Linux](#linux)
  - [macOS](#macos)
- [Environment Configuration](#environment-configuration)
- [Database Setup](#database-setup)
- [Running the Application](#running-the-application)
- [Management Scripts](#management-scripts)
- [User Roles](#user-roles)
- [Face Recognition](#face-recognition)
- [API Reference](#api-reference)
- [Security](#security)

---

## System Overview

The system is built on Flask and supports five station accounts (Admin, Central, Talisay, Bacon, Abuyog). Each station manages its own personnel. Attendance can be recorded automatically via face recognition or submitted manually for admin approval.

### Core Features

**User and Access Management**
- Five station-based accounts with role-based access control
- Admin account can create, deactivate, and delete station accounts
- Kiosk mode for dedicated attendance capture terminals
- Session enforcement: deactivated accounts are logged out immediately

**Personnel Management**
- Add and manage personnel records including rank, name, and station assignment
- Upload profile photos and register face images for automated recognition
- Multiple face samples per person improve recognition accuracy

**Attendance Tracking**
- Automated face recognition using YOLO v11 with optional InsightFace backend
- Liveness detection to reject photo or video spoofing attempts
- Manual attendance submission with photo evidence for admin review
- Time-in and time-out tracking with working hours calculation
- Automatic status assignment: Present, Late, or Absent
- Configurable work start time and attendance cooldown period

**Dashboard and Reports**
- Real-time attendance statistics (Present, Late, Absent counts)
- Weekly and monthly attendance trend charts
- Per-station and system-wide report generation
- Export to Excel and CSV formats

**Kiosk Mode**
- Standalone attendance capture interface for shared terminals
- Restricted to attendance and auth endpoints only

**Pending Approvals**
- Personnel submit attendance photos when face recognition is unavailable
- Admin reviews, approves, or rejects submissions with full audit trail

---

## Technology Stack

**Backend**
- Python 3.11.14
- Flask (web framework)
- SQLAlchemy + PyMySQL (ORM and MySQL driver)
- Flask-Login (session management)
- Flask-WTF (forms and CSRF protection)
- Flask-Limiter (rate limiting)
- Waitress or Gunicorn (production WSGI server)

**Database**
- MySQL 5.7 or 8.x

**Computer Vision / AI**
- YOLO v11 (`yolov11n-face.pt`) — primary face detection model
- InsightFace + ONNX Runtime — optional enhanced backend (RetinaFace + ArcFace embeddings)
- OpenCV — image processing and frame capture
- PyTorch + TorchVision — deep learning runtime
- SciPy — liveness detection signal analysis
- NumPy, Pillow — numerical and image utilities

**Frontend**
- Bootstrap 5
- Chart.js
- DataTables
- Font Awesome
- Vanilla JavaScript

**Reporting**
- Pandas, OpenPyXL — Excel/CSV export
- ReportLab, Matplotlib — PDF and chart generation

---

## Directory Structure

```
BFPAttendance/
├── app.py                          # Application factory and entry point
├── models.py                       # SQLAlchemy models and enums
├── utils.py                        # Shared utility functions
├── requirements.txt                # Production Python dependencies
├── .env                            # Local environment variables (not committed)
├── .env.example                    # Environment variable template
├── .python-version                 # Pinned Python version: 3.11.14
├── bfp_attendance.log              # Rotating application log
├── face_rec_module/
│   ├── face_service.py             # Face detection, recognition, and liveness logic
│   └── yolov11n-face.pt            # YOLO v11 face detection model weights
├── routes/
│   ├── api.py                      # JSON API endpoints (attendance capture, health check)
│   ├── attendance.py               # Attendance management views
│   ├── auth.py                     # Login and logout
│   ├── dashboard.py                # Dashboard and statistics
│   ├── kiosk.py                    # Kiosk terminal interface
│   ├── pending.py                  # Pending approval workflow
│   ├── personnel.py                # Personnel CRUD
│   ├── profile.py                  # User profile and password management
│   └── reports.py                  # Report generation and export
├── manage/
│   ├── manage.py                   # Interactive management console
│   ├── backup_database.py          # Database backup and restore
│   ├── clean_attendance.py         # Clear attendance records only
│   ├── clean_database.py           # Clear all data (destructive)
│   ├── clean_personnel.py          # Clear personnel data, preserve admin
│   ├── generate_fake_data.py       # Generate test data with Filipino localization
│   ├── migrate_kiosk_onleave.py    # Schema migration for kiosk and leave fields
│   ├── config.py                   # Shared config for management scripts
│   └── requirements-dev.txt        # Extra dependencies for management scripts
├── templates/
│   ├── base.html
│   ├── auth/
│   ├── dashboard/
│   ├── personnel/
│   ├── attendance/
│   ├── kiosk/
│   ├── reports/
│   ├── pending/
│   ├── profile/
│   └── errors/
└── static/
    ├── images/
    │   ├── face_data/              # Registered face images (auto-created)
    │   └── attendance_temp/        # Temporary attendance captures (auto-created)
    ├── favicon/
    └── uploads/
```

---

## Prerequisites

The following must be installed before setting up the application.

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11.14 | Pinned in `.python-version`. Other 3.11.x may work. |
| MySQL Server | 5.7 or 8.x | Must be running and accessible |
| Git | Any recent | For cloning the repository |
| Webcam | — | Required for live face recognition capture |
| MySQL client tools | Matching server version | Required only if using backup scripts |

---

## Installation

### Windows

**1. Install Python 3.11**

Download Python 3.11.x from https://www.python.org/downloads/windows/ and run the installer. During installation, check "Add Python to PATH".

Verify the installation:

```
python --version
```

**2. Install MySQL Server**

Download MySQL Community Server 8.x from https://dev.mysql.com/downloads/mysql/ and follow the installer. Note the root password you set during setup.

**3. Clone the repository**

```
git clone <repository-url>
cd BFPAttendance
```

**4. Create a virtual environment**

```
python -m venv .venv
.venv\Scripts\activate
```

You should see `(.venv)` at the start of your prompt.

**5. Install dependencies**

```
pip install -r requirements.txt
```

PyTorch, OpenCV, and the YOLO/InsightFace packages are large. This may take several minutes depending on your connection.

**6. Configure the environment**

Copy the example environment file and edit it with your values:

```
copy .env.example .env
notepad .env
```

At minimum, set `DATABASE_URL` and `SECRET_KEY`. See [Environment Configuration](#environment-configuration) for all options.

**7. Set up the database**

In MySQL, create the database:

```
mysql -u root -p -e "CREATE DATABASE bfp_sorsogon_attendance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

Run the application once to create all tables automatically (SQLAlchemy handles schema creation):

```
python app.py
```

Stop it after the tables are created, then configure your admin account (see [Database Setup](#database-setup)).

**8. Run the application**

For development:

```
python app.py
```

For production using Waitress (included in requirements):

```
waitress-serve --host=0.0.0.0 --port=5000 app:create_app
```

---

### Linux

These instructions apply to Debian/Ubuntu-based distributions. Adjust package manager commands for other distributions (e.g., `dnf` for Fedora, `pacman` for Arch).

**1. Install system dependencies**

```
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev \
    mysql-server mysql-client \
    libmysqlclient-dev pkg-config \
    libgl1-mesa-glx libglib2.0-0 \
    build-essential git
```

The `libgl1-mesa-glx` and `libglib2.0-0` packages are required by OpenCV.

**2. Start and secure MySQL**

```
sudo systemctl start mysql
sudo systemctl enable mysql
sudo mysql_secure_installation
```

**3. Clone the repository**

```
git clone <repository-url>
cd BFPAttendance
```

**4. Create a virtual environment**

```
python3.11 -m venv .venv
source .venv/bin/activate
```

**5. Install dependencies**

```
pip install --upgrade pip
pip install -r requirements.txt
```

If `mysqlclient` fails to build, ensure `libmysqlclient-dev` and `pkg-config` are installed (step 1 above).

**6. Configure the environment**

```
cp .env.example .env
nano .env
```

Set `DATABASE_URL`, `SECRET_KEY`, and any other values relevant to your setup.

**7. Set up the database**

```
sudo mysql -u root -p -e "CREATE DATABASE bfp_sorsogon_attendance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

Then run the app once to initialize the schema:

```
python app.py
```

**8. Run the application**

Development:

```
python app.py
```

Production with Gunicorn:

```
gunicorn -w 1 -b 0.0.0.0:5000 "app:create_app()"
```

Note: Use a single worker (`-w 1`) because face recognition models are loaded into memory and are not safe to share across forked processes.

For long-running deployments, manage the process with `systemd` or `supervisor`.

---

### macOS

**1. Install Homebrew (if not installed)**

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**2. Install Python 3.11 and MySQL**

```
brew install python@3.11 mysql git
```

Start MySQL:

```
brew services start mysql
mysql_secure_installation
```

**3. Clone the repository**

```
git clone <repository-url>
cd BFPAttendance
```

**4. Create a virtual environment**

```
python3.11 -m venv .venv
source .venv/bin/activate
```

**5. Install dependencies**

```
pip install --upgrade pip
pip install -r requirements.txt
```

On Apple Silicon (M1/M2/M3), PyTorch and OpenCV install pre-built wheels for `arm64`. If you encounter issues, check that you are using the native arm64 Python and not an x86 version via Rosetta.

**6. Configure the environment**

```
cp .env.example .env
nano .env
```

**7. Set up the database**

```
mysql -u root -p -e "CREATE DATABASE bfp_sorsogon_attendance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

Run the app once to create the schema:

```
python app.py
```

**8. Run the application**

Development:

```
python app.py
```

Production with Gunicorn:

```
gunicorn -w 1 -b 0.0.0.0:5000 "app:create_app()"
```

---

## Environment Configuration

Copy `.env.example` to `.env` and fill in the values below. All variables are optional unless marked as required.

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes (production) | None | Flask session signing key. Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | Yes | `mysql+pymysql://root:@localhost/bfp_sorsogon_attendance` | Full MySQL connection string |
| `AUTO_CREATE_ADMIN` | No | `false` | Set to `true` to bootstrap an admin user on first startup |
| `DEFAULT_ADMIN_USERNAME` | No | `admin` | Admin username (used only when `AUTO_CREATE_ADMIN=true`) |
| `DEFAULT_ADMIN_EMAIL` | No | `admin@bfp.gov.ph` | Admin email (used only when `AUTO_CREATE_ADMIN=true`) |
| `DEFAULT_ADMIN_PASSWORD` | Conditional | None | Required when `AUTO_CREATE_ADMIN=true`. Must be set explicitly. |
| `DEFAULT_STATION_PASSWORD` | No | — | Default password for auto-created station accounts |
| `PRELOAD_FACE_MODELS` | No | `true` | Load YOLO weights at startup to reduce first-capture delay |
| `USE_INSIGHTFACE` | No | `false` | Use InsightFace (RetinaFace + ArcFace) instead of YOLO for detection and embedding |
| `FACE_DETECTION_CONFIDENCE` | No | `0.3` | Minimum YOLO confidence score for a face to be considered detected |
| `FACE_RECOGNITION_THRESHOLD` | No | `0.35` | Cosine similarity threshold for face identity matching |
| `WORK_START_TIME` | No | `08:00` | Official work start time for late/on-time classification |
| `ATTENDANCE_COOLDOWN` | No | `5` | Minimum seconds between attendance records for the same person |
| `LIVENESS_TEXTURE_THRESHOLD` | No | `0.6` | Texture analysis sensitivity for liveness detection |
| `LIVENESS_MIN_MOTION` | No | `0.001` | Minimum frame motion to classify as live |
| `LIVENESS_MAX_MOTION` | No | `0.15` | Maximum motion threshold (above this is likely noise/spoofing) |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## Database Setup

### First-Time Bootstrap (Recommended)

Set the following in `.env` before the first run:

```
AUTO_CREATE_ADMIN=true
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_EMAIL=admin@bfp.gov.ph
DEFAULT_ADMIN_PASSWORD=<choose-a-strong-password>
```

On startup, the application will create all tables and insert the admin user. The admin will be forced to change their password on first login. Remove or set `AUTO_CREATE_ADMIN=false` after the first run.

### Using the Management Console

For more control over the initial setup, use the interactive management console:

```
cd manage
pip install -r requirements-dev.txt
python manage.py
```

The console provides options to initialize the schema, create admin and station users, generate test data, and back up the database.

### Running Schema Migrations

When updating from an older version of the system, apply any pending migrations:

```
python manage/migrate_kiosk_onleave.py
```

Check the `manage/` directory for any migration scripts that have been added since your last update and run them in order.

---

## Running the Application

### Development

```
python app.py
```

The application starts on `http://0.0.0.0:5000` with debug mode enabled. Do not use this in production.

### Production — Windows (Waitress)

Waitress is a pure-Python WSGI server suitable for Windows:

```
waitress-serve --host=0.0.0.0 --port=5000 app:create_app
```

### Production — Linux / macOS (Gunicorn)

```
gunicorn -w 1 -b 0.0.0.0:5000 "app:create_app()"
```

Use a single worker. Face recognition models hold state in memory and are not fork-safe. If you need to handle higher concurrency, scale horizontally with multiple instances behind a reverse proxy (nginx or Caddy), each with a dedicated database connection and model instance.

### Accessing the Application

Open a browser and navigate to:

```
http://localhost:5000
```

---

## Management Scripts

All scripts are in the `manage/` directory. Install their dependencies first:

```
pip install -r manage/requirements-dev.txt
```

| Script | Purpose |
|---|---|
| `manage.py` | Interactive menu-driven console for all management tasks |
| `backup_database.py` | Create and restore MySQL database backups |
| `clean_attendance.py` | Delete attendance records while preserving personnel and face data |
| `clean_personnel.py` | Delete personnel records while preserving admin users |
| `clean_database.py` | Delete all data (destructive — use only in development) |
| `generate_fake_data.py` | Generate realistic test data using Filipino names and localization |
| `migrate_kiosk_onleave.py` | Add kiosk user type and on-leave attendance status columns |

These scripts are for development and administration only. Do not deploy them to production servers or use destructive scripts on live data without a backup.

---

## User Roles

| Role | Description |
|---|---|
| Admin | Full system access: manage all users, personnel, attendance, reports, and approvals |
| Station (Central, Talisay, Bacon, Abuyog) | Manage personnel and attendance for their assigned station only |
| Kiosk | Restricted to the attendance capture terminal; cannot access any other part of the system |

Station accounts are created by the Admin. Kiosk accounts are created per station and tied to a physical terminal.

---

## Face Recognition

### Default Backend: YOLO v11

The model file `face_rec_module/yolov11n-face.pt` is loaded at startup (if `PRELOAD_FACE_MODELS=true`). Face embeddings are computed using a secondary encoder and compared against stored personnel embeddings using cosine similarity.

### Optional Backend: InsightFace

InsightFace provides higher accuracy using RetinaFace for detection and ArcFace for embeddings. To enable it:

1. Ensure `insightface` and `onnxruntime` are installed (included in `requirements.txt`).
2. Set `USE_INSIGHTFACE=true` in `.env`.

InsightFace downloads model weights on first use. An internet connection is required for the initial load.

### Liveness Detection

The system applies texture and motion analysis to the captured frame to detect whether the person in front of the camera is physically present or presenting a photo or video. The sensitivity is controlled by `LIVENESS_TEXTURE_THRESHOLD`, `LIVENESS_MIN_MOTION`, and `LIVENESS_MAX_MOTION` in the environment configuration.

### Face Registration

Each personnel record can have multiple face images registered. More samples across different lighting conditions and angles improve recognition accuracy. Images are stored in `static/images/face_data/` and are never exposed publicly.

---

## API Reference

All API endpoints are under `/api/`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Returns database connectivity and face model status as JSON |
| POST | `/api/capture_attendance` | Submit a frame for face recognition and record attendance |
| POST | `/api/capture_attendance_enhanced` | Same as above using the InsightFace backend if enabled |

Rate limiting applies to all API endpoints. The default limit is 1,000 requests per day and 200 per hour per IP address.

---

## Security

- **CSRF Protection**: All form submissions are protected by Flask-WTF CSRF tokens.
- **Password Hashing**: Passwords are hashed using Werkzeug's `generate_password_hash` (PBKDF2-SHA256).
- **Session Management**: Flask-Login handles session cookies. Deactivated accounts are logged out on the next request.
- **Rate Limiting**: Flask-Limiter applies per-IP rate limits to prevent brute force and API abuse.
- **File Upload Validation**: Uploaded images are validated by type and size (16 MB maximum).
- **Liveness Detection**: Attendance capture rejects static images and video replay attacks.
- **Secret Key Enforcement**: The application refuses to start in production mode without a `SECRET_KEY` set in the environment.

---

## Logging

The application writes logs to `bfp_attendance.log` with rotation at 5 MB, keeping 5 backup files. Logs are also written to stdout. The log level is controlled by the `LOG_LEVEL` environment variable.

---

## License

This project is developed for the Bureau of Fire Protection Sorsogon Province.

---

Bureau of Fire Protection — Sorsogon Province
Attendance Management System