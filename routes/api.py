from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from datetime import datetime
import os
import base64
import numpy as np
import cv2
import logging

from models import Attendance, AttendanceStatus, Personnel, db
from sqlalchemy import text
from utils import handle_api_exception, json_error
from face_rec_module.face_service import (
    process_base64_image,
    recognize_face,
    load_face_database,
    process_attendance,
    register_face,
    get_yolo_model,
    analyze_liveness,
    extract_face_embeddings,
    to_native_types,
)

# Set up logger
logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)


@api_bp.route("/personnel")
@login_required
def get_personnel():
    """Get personnel list for current user's station"""
    if current_user.is_admin:
        personnel = Personnel.query.all()
    else:
        personnel = Personnel.query.filter_by(station_id=current_user.id).all()

    data = []
    for p in personnel:
        data.append(
            {
                "id": p.id,
                "full_name": p.full_name,
                "rank": p.rank,
                "station": p.station.station_name,
                "image_path": p.image_path,
            }
        )

    return jsonify({"personnel": data})


@api_bp.route("/attendance/capture", methods=["POST"])
@login_required
def capture_attendance():
    """API endpoint for capturing attendance via face recognition"""
    try:
        data = request.get_json()
        image_data = data.get("image")

        if not image_data:
            return jsonify({"success": False, "error": "No image provided"}), 400

        # Process the image and extract face (with liveness detection)
        face_embedding, face_metadata, temp_path = process_base64_image(
            image_data, enable_liveness=True
        )

        if face_metadata and face_metadata.get("liveness_failed"):
            liveness_details = to_native_types(
                face_metadata.get("liveness_details", {})
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Liveness detection failed. Please use a live camera feed, not a photo or video.",
                        "liveness_details": liveness_details,
                    }
                ),
                400,
            )

        if face_embedding is None:
            return (
                jsonify({"success": False, "error": "No face detected in the image"}),
                400,
            )

        # Load face database for current station
        station_id = None if current_user.is_admin else current_user.id
        face_database = load_face_database(station_id)

        if not face_database:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "No personnel registered in the face database",
                    }
                ),
                400,
            )

        # Recognize face
        threshold = current_app.config.get("FACE_RECOGNITION_THRESHOLD", 0.6)
        recognized_id, confidence = recognize_face(
            face_embedding, face_database, threshold
        )

        if recognized_id is None:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Face not recognized. Please ensure you are registered in the system.",
                    }
                ),
                400,
            )

        # Process attendance
        result = process_attendance(recognized_id, confidence, image_data)

        # Clean up temp file
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

        if isinstance(result, dict) and result.get("success"):
            result["enhanced_liveness"] = False
        return jsonify(result)

    except Exception as e:
        return handle_api_exception(e)


@api_bp.route("/attendance/capture/enhanced", methods=["POST"])
@login_required
def capture_attendance_enhanced():
    """Enhanced API endpoint for capturing attendance with multi-frame liveness detection.
    
    This endpoint accepts multiple frames for comprehensive liveness detection including:
    - Blink detection (requires ~10 frames)
    - Head movement analysis
    - Motion-based liveness detection
    - Texture analysis
    
    Request JSON format:
    {
        "frames": ["base64_image1", "base64_image2", ...],  // Multiple frames (recommended: 10-15)
        "main_image": "base64_image"  // The primary image to use for recognition
    }
    """
    try:
        from flask import current_app
        import uuid
        
        data = request.get_json()
        frames_data = data.get("frames", [])
        main_image_data = data.get("main_image") or (frames_data[-1] if frames_data else None)
        
        if not main_image_data:
            return json_error("No image provided", 400)
        
        if len(frames_data) < 3:
            # Fall back to standard single-image processing if not enough frames
            logger.warning("Not enough frames for enhanced liveness, falling back to standard processing")
            return capture_attendance()
        
        # Convert all frames to numpy arrays and detect faces
        frames = []
        bboxes = []
        model = get_yolo_model()
        
        try:
            face_detection_confidence = current_app.config.get("FACE_DETECTION_CONFIDENCE", 0.5)
        except RuntimeError:
            face_detection_confidence = 0.5
        
        for frame_data in frames_data:
            try:
                # Remove data URL header if present
                if "," in frame_data:
                    frame_data = frame_data.split(",")[1]
                
                # Decode base64 image
                image_bytes = base64.b64decode(frame_data)
                nparr = np.frombuffer(image_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if img is not None:
                    # Detect face in frame
                    results = model(img, conf=face_detection_confidence)
                    
                    if len(results) > 0 and len(results[0].boxes) > 0:
                        boxes = results[0].boxes
                        confidences = boxes.conf.cpu().numpy()
                        max_idx = np.argmax(confidences)
                        bbox = boxes.xyxy[max_idx].cpu().numpy().astype(int)
                        
                        frames.append(img)
                        bboxes.append(bbox)
            except Exception as e:
                logger.warning(f"Error processing frame: {e}")
                continue
        
        if len(frames) < 3:
            return jsonify({
                "success": False, 
                "error": "Could not detect face in enough frames. Please ensure your face is visible and well-lit."
            }), 400
        
        # Use the last frame as the main image for recognition
        main_img = frames[-1]
        main_bbox = bboxes[-1]
        
        # Perform enhanced liveness detection with all collected data
        logger.info(f"=== Starting Enhanced Liveness Detection with {len(frames)} frames ===")
        
        is_live, liveness_details = analyze_liveness(
            main_img, 
            main_bbox, 
            previous_frames=frames[:-1],  # All frames except the last one
            previous_bboxes=bboxes[:-1]   # Corresponding bboxes
        )
        
        logger.info(f"=== Liveness Result: {'LIVE' if is_live else 'FAKE/PHOTO'} ===")
        
        if not is_live:
            logger.warning("❌ ENHANCED LIVENESS DETECTION FAILED - Possible spoofing attempt detected!")
            liveness_details = to_native_types(liveness_details)
            logger.warning(f"Liveness details: {liveness_details}")
            return jsonify({
                "success": False,
                "error": "Liveness detection failed. Please use a live camera feed, ensure you blink naturally, and keep your head slightly moving.",
                "liveness_details": liveness_details,
            }), 400
        
        logger.info("✓ ENHANCED LIVENESS DETECTION PASSED - Live person detected")
        
        # Extract face and embedding from main image
        x1, y1, x2, y2 = main_bbox
        face = main_img[y1:y2, x1:x2]
        
        # Save temp file for embedding extraction
        temp_filename = f"temp_{uuid.uuid4()}.jpg"
        try:
            temp_folder = current_app.config["TEMP_ATTENDANCE_FOLDER"]
        except RuntimeError:
            temp_folder = "static/images/attendance_temp"
        
        temp_path = os.path.join(temp_folder, temp_filename)
        os.makedirs(temp_folder, exist_ok=True)
        cv2.imwrite(temp_path, face)
        
        # Extract face embedding
        face_embedding, face_metadata = extract_face_embeddings(temp_path)
        
        if face_embedding is None:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            return jsonify({
                "success": False, 
                "error": "Could not extract face features. Please ensure your face is clearly visible."
            }), 400
        
        # Load face database for current station
        station_id = None if current_user.is_admin else current_user.id
        face_database = load_face_database(station_id)
        
        if not face_database:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            return jsonify({
                "success": False,
                "error": "No personnel registered in the face database",
            }), 400
        
        # Recognize face
        try:
            threshold = current_app.config.get("FACE_RECOGNITION_THRESHOLD", 0.6)
        except RuntimeError:
            threshold = 0.6
            
        recognized_id, confidence = recognize_face(face_embedding, face_database, threshold)
        
        if recognized_id is None:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            return jsonify({
                "success": False,
                "error": "Face not recognized. Please ensure you are registered in the system.",
            }), 400
        
        # Process attendance
        result = process_attendance(recognized_id, confidence, main_image_data)
        if isinstance(result, dict) and result.get("success"):
            result["enhanced_liveness"] = True
        
        # Add liveness details to result
        if result.get("success"):
            result["liveness_details"] = to_native_types(liveness_details)
            result["enhanced_liveness"] = True
        
        # Clean up temp file
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in enhanced attendance capture: {e}")
        return handle_api_exception(e)


@api_bp.route("/face/register/<int:personnel_id>", methods=["POST"])
@login_required
def register_personnel_face(personnel_id):
    """API endpoint for registering personnel face data"""
    try:
        personnel = Personnel.query.get_or_404(personnel_id)

        # Check access
        if not current_user.is_admin and personnel.station_id != current_user.id:
            return jsonify({"success": False, "error": "Access denied"}), 403

        data = request.get_json()
        images = data.get("images", [])

        if not images:
            return jsonify({"success": False, "error": "No images provided"}), 400

        # Register faces
        result = register_face(personnel_id, images)
        return jsonify(result)

    except Exception as e:
        return handle_api_exception(e)


@api_bp.route("/health")
def health_check():
    """Basic health check for DB connectivity and model readiness."""
    status = {
        "ok": True,
        "database": "ok",
        "models": {},
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    # Database check
    try:
        db.session.execute(text("SELECT 1"))
    except Exception as exc:
        status["ok"] = False
        status["database"] = f"error: {exc}"

    # Model checks
    try:
        get_yolo_model()
        status["models"]["yolo"] = "ok"
    except Exception as exc:
        status["ok"] = False
        status["models"]["yolo"] = f"error: {exc}"

    try:
        if current_app.config.get("USE_INSIGHTFACE", False):
            app = get_insightface_app()
            status["models"]["insightface"] = "ok" if app else "disabled"
        else:
            status["models"]["insightface"] = "disabled"
    except Exception as exc:
        status["ok"] = False
        status["models"]["insightface"] = f"error: {exc}"

    return jsonify(status), (200 if status["ok"] else 503)


@api_bp.route("/stats/dashboard")
@login_required
def dashboard_stats():
    """Get real-time dashboard statistics"""
    today = datetime.now().date()

    # Base query for personnel under current user's station
    if current_user.is_admin:
        personnel_query = Personnel.query
        attendance_query = Attendance.query
    else:
        personnel_query = Personnel.query.filter_by(station_id=current_user.id)
        attendance_query = Attendance.query.join(Personnel).filter(
            Personnel.station_id == current_user.id
        )

    total_personnel = personnel_query.count()
    today_attendance = attendance_query.filter(Attendance.date == today).all()
    present_today = len(
        [
            a
            for a in today_attendance
            if a.status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]
        ]
    )
    absent_today = total_personnel - present_today
    late_today = len(
        [a for a in today_attendance if a.status == AttendanceStatus.LATE]
    )

    return jsonify(
        {
            "total_personnel": total_personnel,
            "present_today": present_today,
            "absent_today": absent_today,
            "late_today": late_today,
            "attendance_rate": (
                (present_today / total_personnel * 100) if total_personnel > 0 else 0
            ),
        }
    )


@api_bp.route("/time")
@login_required
def get_current_time():
    """Get current time for dashboard clock"""
    current_time = datetime.now()
    return jsonify(
        {
            "time": current_time.strftime("%H:%M:%S"),
            "date": current_time.strftime("%A, %B %d, %Y"),
            "timestamp": current_time.isoformat(),
        }
    )


@api_bp.route("/personnel/<int:personnel_id>/attendance")
@login_required
def get_personnel_attendance(personnel_id):
    """Get attendance history for a specific personnel"""
    personnel = Personnel.query.get_or_404(personnel_id)

    # Check access
    if not current_user.is_admin and personnel.station_id != current_user.id:
        return jsonify({"error": "Access denied"}), 403

    attendance_records = (
        Attendance.query.filter_by(personnel_id=personnel_id)
        .order_by(Attendance.date.desc())
        .limit(30)
        .all()
    )

    data = []
    for record in attendance_records:
        data.append(
            {
                "date": record.date.strftime("%Y-%m-%d"),
                "time_in": (
                    record.time_in.strftime("%H:%M:%S") if record.time_in else None
                ),
                "time_out": (
                    record.time_out.strftime("%H:%M:%S") if record.time_out else None
                ),
                "status": record.status.value if record.status else None,
                "work_hours": record.work_hours,
            }
        )

    return jsonify({"attendance": data})

