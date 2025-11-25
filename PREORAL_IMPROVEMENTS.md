# Pre-Oral Defense Improvements

This document summarizes the improvements made based on the pre-oral defense panel feedback.

## Summary of Changes

### 1. ✅ Removed All Charts/Graphs

**Reason:** Panel recommended removing unnecessary graphs as they were not needed.

**Changes Made:**

- Removed Chart.js code from `templates/dashboard/index.html`
- Removed chart data generation from `routes/dashboard.py` (weekly_data and monthly_data)
- Dashboard now shows only essential statistics cards

### 2. ✅ Improved Reports Page with Date Filters

**Reason:** Reports page needed filtering by week, month, year, and custom date range.

**Changes Made:**

- Updated `templates/reports/index.html` with:
  - Quick filter buttons: "This Week", "This Month", "This Year"
  - Custom date range picker with start and end date inputs
  - Station filter dropdown for admins
- Added stations context to `routes/reports.py`

### 3. ✅ Replaced Delete with Archive (Soft Delete)

**Reason:** Personnel records should never be permanently deleted, only archived.

**Changes Made:**

- Added `is_active` field to Personnel model
- Updated `routes/personnel.py`:
  - `index()` now filters by `is_active=True` by default
  - `delete()` renamed to `archive()` - sets `is_active=False`
  - Added `restore()` endpoint for restoring archived personnel
  - `api_data()` shows status badges and appropriate action buttons
- Updated `templates/personnel/index.html` with Archive/Restore buttons
- Updated `templates/personnel/edit.html` with archive functionality

### 4. ✅ Added Shift Schedule Fields

**Reason:** Need to track personnel shift schedules (start time, end time, shifting status).

**Changes Made:**

- Added new fields to Personnel model in `models.py`:
  - `shift_start_time` - When shift starts (e.g., 08:00)
  - `shift_end_time` - When shift ends (e.g., 17:00)
  - `is_shifting` - Boolean flag for 15-day rotation schedule
  - `shift_start_date` - When shifting schedule started

### 5. ✅ Implemented 15-Day Shift Rotation

**Reason:** Some personnel work 15 days on, 15 days off rotation.

**Changes Made:**

- Added `is_on_duty()` method to Personnel model
- Method calculates if personnel is on-duty based on:
  - `is_shifting` flag
  - `shift_start_date`
  - Current date (calculates which 15-day period)
- Non-shifting personnel are always considered on-duty

### 6. ✅ Updated Personnel Forms

**Reason:** UI needed to support the new shift schedule fields.

**Changes Made:**

- Updated `templates/personnel/add.html` with Shift Schedule section:
  - Shift Start Time input
  - Shift End Time input
  - 15-Day Shifting toggle switch
  - Shift Start Date input
- Updated `templates/personnel/edit.html` with same fields
- Updated `routes/personnel.py` to handle new fields

### 7. ✅ Enhanced Liveness Detection

**Reason:** Panel noted that the system still detected faces from photos - needed better anti-spoofing.

**Changes Made:**

- Enhanced `face_rec_module/face_service.py`:
  - **Blink Detection:** Uses Eye Aspect Ratio (EAR) to detect natural blinking
  - **Head Movement Detection:** Tracks face bounding box changes across frames
  - **Enhanced Motion Detection:** Uses optical flow analysis
  - **Multi-check Security:** Requires multiple checks to pass for liveness
- Updated `analyze_liveness()` to combine all detection methods
- Added new API endpoint `/api/attendance/capture/enhanced` for multi-frame capture
- Updated `templates/attendance/capture.html`:
  - Captures 12 frames over ~2 seconds
  - Progress bar shows capture status
  - Enhanced security info card
  - Detailed liveness failure feedback

### 8. ✅ Optional InsightFace Integration

**Reason:** Panel asked for better face detection.

**Changes Made:**

- Added optional InsightFace support in `face_service.py`:
  - RetinaFace for state-of-the-art face detection
  - ArcFace for superior face embeddings (512-dimensional)
  - Better handling of angles, lighting, partial occlusion
- Added `USE_INSIGHTFACE` config flag in `app.py`
- Updated `requirements.txt` with optional InsightFace dependencies

## Database Migration Required

Run the migration script to add new fields:

```bash
cd manage
python migrate_add_shift_fields.py
```

This adds:

- `is_active` (BOOLEAN, default TRUE)
- `shift_start_time` (TIME, nullable)
- `shift_end_time` (TIME, nullable)
- `is_shifting` (BOOLEAN, default FALSE)
- `shift_start_date` (DATE, nullable)

## Optional: Enable InsightFace

For even better face detection accuracy:

1. Install dependencies:

```bash
pip install insightface onnxruntime
# Or for GPU: pip install insightface onnxruntime-gpu
```

2. Enable in environment:

```bash
export USE_INSIGHTFACE=true
```

Or add to `.env` file:

```
USE_INSIGHTFACE=true
```

## Testing the Changes

### Test Liveness Detection

1. Go to Attendance > Capture
2. Click "Capture Attendance"
3. System captures 12 frames over 2 seconds
4. Progress bar shows capture status
5. Try with a photo - should fail with detailed liveness report

### Test Shift Schedule

1. Go to Personnel > Add Personnel
2. Set shift times and enable "15-Day Shifting"
3. Set a shift start date
4. Save and verify in edit view

### Test Archive/Restore

1. Go to Personnel list
2. Click Edit on a personnel
3. Click "Archive" button
4. Personnel moves to archived list
5. Use filter to show archived and click "Restore"

### Test Reports Filters

1. Go to Reports page
2. Click "This Week", "This Month", "This Year" buttons
3. Test custom date range
4. Test station filter (admin only)

---

**All improvements implemented as per pre-oral defense panel feedback.**
