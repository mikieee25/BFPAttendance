# BFP Sorsogon Attendance Management System

A comprehensive web-based attendance management system for the Bureau of Fire Protection (BFP) Sorsogon Province, featuring face recognition technology for automated attendance tracking.

## Features

### 🔐 User Management

- **5 Station Accounts**: Admin, Central, Talisay, Bacon, Abuyog
- **Role-based Access Control**: Admin can create/delete accounts, stations manage their personnel
- **Secure Authentication**: Password-protected login with session management

### 👥 Personnel Management

- **Complete Personnel Records**: First Name, Last Name, Rank, Station assignment
- **Face Recognition Registration**: Multiple face images per personnel for improved accuracy
- **Profile Management**: Upload profile pictures and manage personal information

### 📊 Dashboard

- **Real-time Clock**: Display current date and time
- **Quick Statistics**: Today's attendance summary (Present, Late, Absent)
- **Interactive Charts**: Weekly and monthly attendance trends
- **Recent Activity**: Latest attendance records

### ⏰ Attendance Tracking

- **Face Recognition**: Automated attendance capture using AI-powered face detection
- **Manual Entry**: Manual attendance recording for special cases
- **Time In/Out**: Complete attendance tracking with working hours calculation
- **Status Management**: Automatic status assignment (Present, Late, Absent)

### 📈 Reports

- **Attendance Summary**: Detailed attendance reports with filters
- **Monthly Trends**: Visual representation of attendance patterns
- **Station Comparison**: Compare attendance across different stations (Admin only)
- **Export Functionality**: Export reports to Excel/CSV formats

### ⏳ Pending Approval

- **Manual Submissions**: Personnel can submit attendance photos for admin approval
- **Admin Review**: Approve or reject pending attendance requests
- **Audit Trail**: Complete history of all attendance actions

### 👤 Profile Management

- **User Settings**: Update profile information and change passwords
- **Activity Logs**: Track user activities and system actions
- **Admin Tools**: System management tools for administrators

## Technology Stack

### Backend

- **Flask**: Python web framework
- **SQLAlchemy**: Database ORM
- **MySQL**: Database management system
- **Flask-Login**: User session management
- **Flask-WTF**: Form handling and CSRF protection

### Frontend

- **Bootstrap 5**: Responsive UI framework
- **Font Awesome**: Icon library
- **DataTables**: Advanced table functionality
- **Chart.js**: Interactive charts and graphs
- **JavaScript**: Client-side interactivity

### AI/Computer Vision

- **YOLO v11**: Face detection model
- **OpenCV**: Image processing
- **PyTorch**: Deep learning framework
- **NumPy**: Numerical computations

## Installation

### Prerequisites

- Python 3.8 or higher
- MySQL Server
- Webcam (for face recognition)

### Setup Instructions

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd BFPAttendance
   ```

2. **Create virtual environment**

   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # or
   source .venv/bin/activate  # Linux/macOS
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Setup MySQL Database**

   - Create a database named `bfp_sorsogon_attendance`
   - Import the provided SQL file: `bfp_sorsogon_attendance.sql`
   - Update database connection in `.env` file

5. **Configure Environment**

   - Copy `.env.example` to `.env`
   - Update configuration values as needed

6. **Run the application**

   ```bash
   python app.py
   ```

   Or use the provided batch file:

   ```bash
   run.bat
   ```

7. **Access the application**
   - Open your browser and go to `http://localhost:5000`
   - Default admin credentials:
     - Username: `admin`
     - Password: `admin123`

## Configuration

### Environment Variables

- `SECRET_KEY`: Flask secret key for session security
- `DATABASE_URL`: MySQL connection string
- `FACE_DETECTION_CONFIDENCE`: Minimum confidence for face detection (0.5)
- `FACE_RECOGNITION_THRESHOLD`: Face recognition similarity threshold (0.75)
- `WORK_START_TIME`: Official work start time (08:00)
- `ATTENDANCE_COOLDOWN`: Minimum seconds between attendance records (60)

### Directory Structure

```
BFPAttendance/
├── app.py                 # Main Flask application
├── models.py              # Database models
├── requirements.txt       # Python dependencies
├── run.bat               # Windows startup script
├── .env                  # Environment configuration
├── face_recognition/     # Face recognition module
│   ├── __init__.py
│   ├── face_service.py   # Face recognition logic
│   └── yolov11n-face.pt  # YOLO face detection model
├── routes/               # Flask blueprints
│   ├── auth.py          # Authentication routes
│   ├── dashboard.py     # Dashboard routes
│   ├── personnel.py     # Personnel management
│   ├── attendance.py    # Attendance tracking
│   ├── reports.py       # Report generation
│   ├── pending.py       # Pending approvals
│   ├── profile.py       # User profile management
│   └── api.py           # API endpoints
├── templates/            # HTML templates
│   ├── base.html        # Base template
│   ├── auth/            # Authentication templates
│   ├── dashboard/       # Dashboard templates
│   ├── personnel/       # Personnel templates
│   ├── attendance/      # Attendance templates
│   ├── reports/         # Report templates
│   ├── pending/         # Pending approval templates
│   ├── profile/         # Profile templates
│   └── errors/          # Error page templates
└── static/              # Static files
    ├── images/          # Image assets
    ├── favicon/         # Favicon files
    └── uploads/         # User uploaded files
```

## Usage

### For Administrators

1. **System Setup**: Create station accounts and manage users
2. **Personnel Management**: Add personnel across all stations
3. **Approval Process**: Review and approve manual attendance submissions
4. **System Reports**: Generate comprehensive attendance reports
5. **System Maintenance**: Use admin tools for system management

### For Station Users

1. **Personnel Management**: Add, edit, and manage station personnel
2. **Face Registration**: Register personnel faces for automated attendance
3. **Attendance Tracking**: Capture attendance using face recognition
4. **Report Generation**: View station-specific attendance reports

### For Personnel

1. **Face Recognition**: Use the attendance capture system for automatic check-in/out
2. **Manual Submission**: Submit attendance photos for approval when needed

## Security Features

- **CSRF Protection**: All forms protected against cross-site request forgery
- **Rate Limiting**: API endpoints protected against abuse
- **Password Hashing**: Secure password storage using Werkzeug
- **Session Management**: Secure session handling with Flask-Login
- **File Upload Security**: Secure file handling with type validation

## Support

For technical support or feature requests, please contact the development team.

## License

This project is developed for the Bureau of Fire Protection Sorsogon Province.

---

**Bureau of Fire Protection**  
**Sorsogon Province**  
**Attendance Management System v1.0**
