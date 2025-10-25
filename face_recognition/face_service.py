# Face Recognition Service for BFP Sorsogon Attendance System
# Handles face detection, encoding, recognition, and attendance processing using YOLO and OpenCV

# Standard library imports
import os
import uuid
import json
import base64
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any

# Computer vision and machine learning libraries
import cv2
import torch
import numpy as np
from ultralytics import YOLO

# Flask framework imports
from flask import current_app

# Database imports
from sqlalchemy import or_
from models import db, Personnel, FaceData, Attendance, AttendanceStatus, User

# Set up logger
logger = logging.getLogger(__name__)

# Global model instance
yolo_model = None

# Face database cache to avoid repeated database queries
_face_db_cache: Optional[Dict[int, Dict[str, Any]]] = None
_face_db_cache_time: Optional[datetime] = None
_face_db_cache_ttl: int = 300  # Cache TTL in seconds (5 minutes)

# Configuration constants
MAX_IMAGE_SIZE_MB: int = 10
MAX_IMAGE_SIZE_BYTES: int = MAX_IMAGE_SIZE_MB * 1024 * 1024


def get_yolo_model() -> YOLO:
    """Load and return the YOLO face detection model.

    Uses Flask app context to store model, avoiding global variables and memory leaks.
    Falls back to global variable if app context is not available.

    Returns:
        YOLO: YOLO model instance for face detection
    """
    global yolo_model

    # Try to use app context if available
    try:
        if not hasattr(current_app, "yolo_model") or current_app.yolo_model is None:
            model_path = current_app.config["YOLO_MODEL_PATH"]
            device = current_app.config.get("TORCH_DEVICE", "cpu")

            logger.info(f"PyTorch version: {torch.__version__}")
            logger.info(f"CUDA available: {torch.cuda.is_available()}")
            logger.info(f"Loading YOLO model on device: {device}")

            # Ensure PyTorch uses the configured device
            if device == "cpu":
                torch.set_default_device("cpu")

            # Initialize model with specific device setting
            model = YOLO(model_path)
            model.to(device)

            # Store in app context
            current_app.yolo_model = model
            logger.info(f"YOLO model loaded successfully on {device}")

        return current_app.yolo_model

    except RuntimeError:
        # No app context available, use global variable
        if yolo_model is None:
            logger.warning("No app context available, using global YOLO model")
            # This should only happen during testing or initialization
            model_path = os.environ.get(
                "YOLO_MODEL_PATH", "face_recognition/yolov11n-face.pt"
            )
            yolo_model = YOLO(model_path)
            yolo_model.cpu()

        return yolo_model


def validate_base64_image(base64_image: str) -> Tuple[bool, Optional[str]]:
    """Validate base64 image data before processing.

    Checks for:
    - Size limits (10MB max)
    - Valid base64 format
    - Valid image format

    Args:
        base64_image: Base64 encoded image string

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    try:
        # Remove data URL header if present
        if "," in base64_image:
            base64_image = base64_image.split(",")[1]

        # Check if base64 string is valid
        try:
            image_bytes = base64.b64decode(base64_image, validate=True)
        except Exception as e:
            return False, f"Invalid base64 format: {str(e)}"

        # Check size limit
        if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
            size_mb = len(image_bytes) / (1024 * 1024)
            return (
                False,
                f"Image too large: {size_mb:.2f}MB (max {MAX_IMAGE_SIZE_MB}MB)",
            )

        # Verify it's a valid image format
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return False, "Invalid image format"
        except Exception as e:
            return False, f"Cannot decode image: {str(e)}"

        return True, None

    except Exception as e:
        logger.error(f"Error validating base64 image: {e}")
        return False, f"Validation error: {str(e)}"


def extract_face_embeddings(
    image_path: str,
) -> Tuple[Optional[List[float]], Optional[Dict[str, Any]]]:
    """Extract face embeddings from an image file.

    Detects faces using YOLO model and creates a normalized embedding vector
    for face recognition comparison.

    Args:
        image_path: Path to the image file

    Returns:
        Tuple of (embedding_list, metadata_dict) or (None, None) if no face detected
    """
    try:
        model = get_yolo_model()

        # Load and validate image
        img = cv2.imread(image_path)
        if img is None:
            logger.warning(f"Could not read image: {image_path}")
            return None, None

        # Run YOLO face detection
        results = model(
            img, conf=current_app.config.get("FACE_DETECTION_CONFIDENCE", 0.5)
        )
        if len(results) == 0 or len(results[0].boxes) == 0:
            logger.debug(f"No faces detected in image: {image_path}")
            return None, None

        # Select the face with highest confidence
        boxes = results[0].boxes
        confidences = boxes.conf.cpu().numpy()
        max_idx = np.argmax(confidences)

        # Extract bounding box coordinates and confidence score
        bbox = boxes.xyxy[max_idx].cpu().numpy().astype(int)
        confidence = float(confidences[max_idx])

        # Crop face region from original image
        face = img[bbox[1] : bbox[3], bbox[0] : bbox[2]]

        # Create standardized face embedding for comparison
        # Resize to consistent dimensions for uniform comparison
        face_resized = cv2.resize(face, (128, 128))

        # Convert to grayscale to reduce dimensionality and improve consistency
        face_gray = cv2.cvtColor(face_resized, cv2.COLOR_BGR2GRAY)

        # Create embedding by flattening pixel values
        embedding = face_gray.flatten().astype(float)

        # Normalize embedding vector for consistent comparison
        if np.linalg.norm(embedding) > 0:
            embedding = embedding / np.linalg.norm(embedding)

        # Return embedding as Python list with metadata
        return embedding.tolist(), {
            "bbox": bbox.tolist(),
            "confidence": float(confidence),
        }

    except Exception as e:
        logger.error(f"Error extracting face embeddings: {e}")
        return None, None


def compare_embeddings(
    emb1: List[float], emb2: List[float], threshold: float = 0.75
) -> Tuple[float, bool]:
    """Compare two face embeddings using cosine similarity.

    Args:
        emb1: First face embedding
        emb2: Second face embedding
        threshold: Similarity threshold for match determination

    Returns:
        Tuple of (similarity_score, is_match_boolean)
    """
    try:
        # Convert to flattened numpy arrays
        emb1 = np.array(emb1).flatten()
        emb2 = np.array(emb2).flatten()

        # Make sure they're the same shape
        if emb1.shape != emb2.shape:
            logger.warning(
                f"Embedding shapes don't match: {emb1.shape} vs {emb2.shape}"
            )
            return 0.0, False

        # Compute cosine similarity
        dot_product = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)

        # Avoid division by zero
        if norm1 == 0 or norm2 == 0:
            return 0.0, False

        similarity = float(dot_product / (norm1 * norm2))

        # Determine if it's a match based on threshold
        is_match = bool(similarity >= threshold)

        return similarity, is_match

    except Exception as e:
        logger.error(f"Error comparing embeddings: {e}")
        return 0.0, False


def clear_face_database_cache() -> None:
    """Clear the face database cache.

    Should be called after:
    - New personnel registered
    - Face data added/removed
    - Personnel deleted
    """
    global _face_db_cache, _face_db_cache_time
    _face_db_cache = None
    _face_db_cache_time = None
    logger.info("Face database cache cleared")


def load_face_database(
    station_id: Optional[int] = None, force_refresh: bool = False
) -> Dict[int, Dict[str, Any]]:
    """Load all face embeddings from database for recognition.

    Uses caching to avoid repeated database queries. Cache expires after 5 minutes.

    Args:
        station_id: Limit to specific station. None for all stations.
        force_refresh: Force reload from database, ignoring cache

    Returns:
        Dictionary mapping personnel_id to their face data and embeddings
    """
    global _face_db_cache, _face_db_cache_time

    # Check if we can use cached data
    if (
        not force_refresh
        and _face_db_cache is not None
        and _face_db_cache_time is not None
    ):
        cache_age = (datetime.now() - _face_db_cache_time).total_seconds()
        if cache_age < _face_db_cache_ttl:
            logger.debug(f"Using cached face database (age: {cache_age:.1f}s)")
            # If station_id filter is needed, apply it to cached data
            if station_id is not None:
                return {
                    k: v
                    for k, v in _face_db_cache.items()
                    if Personnel.query.get(k)
                    and Personnel.query.get(k).station_id == station_id
                }
            return _face_db_cache.copy()

    # Load from database
    logger.info("Loading face database from database")
    try:
        face_database = {}

        # Query face data
        query = FaceData.query

        # If station_id is provided, filter by station
        if station_id is not None:
            query = query.join(Personnel).filter(Personnel.station_id == station_id)

        face_data_entries = query.all()

        for entry in face_data_entries:
            try:
                # Parse embedding from JSON string
                embedding = json.loads(entry.embedding) if entry.embedding else None

                if embedding:
                    # Initialize entry if not exists
                    if entry.personnel_id not in face_database:
                        personnel = Personnel.query.get(entry.personnel_id)
                        face_database[entry.personnel_id] = {
                            "name": personnel.full_name,
                            "embeddings": [],
                        }

                    # Add embedding to database
                    face_database[entry.personnel_id]["embeddings"].append(embedding)
            except Exception as e:
                logger.error(f"Error processing face data entry {entry.id}: {e}")
                continue

        # Update cache (only if no station filter, to cache all data)
        if station_id is None:
            _face_db_cache = face_database.copy()
            _face_db_cache_time = datetime.now()
            logger.info(f"Face database cached ({len(face_database)} personnel)")

        return face_database

    except Exception as e:
        logger.error(f"Error loading face database: {e}")
        return {}


def recognize_face(
    face_embedding: List[float],
    face_database: Dict[int, Dict[str, Any]],
    threshold: Optional[float] = None,
) -> Tuple[Optional[int], float]:
    """Identify a person by comparing face embedding against database.

    Args:
        face_embedding: Face embedding to identify
        face_database: Database of known face embeddings
        threshold: Recognition threshold. Uses config default if None.

    Returns:
        Tuple of (personnel_id, confidence_score) or (None, 0) if no match
    """
    try:
        if face_embedding is None or not face_database:
            logger.warning("No face embedding or empty database")
            return None, 0

        # Use provided threshold or get from config
        if threshold is None:
            threshold = current_app.config.get("FACE_RECOGNITION_THRESHOLD", 0.75)

        max_similarity = 0
        recognized_id = None

        for personnel_id, data in face_database.items():
            if not data.get("embeddings"):
                continue

            # Compare with all embeddings for this person
            for db_embedding in data["embeddings"]:
                if db_embedding is None:
                    continue

                similarity, match = compare_embeddings(
                    face_embedding, db_embedding, threshold
                )

                if match and similarity > max_similarity:
                    max_similarity = similarity
                    recognized_id = personnel_id

        return recognized_id, max_similarity

    except Exception as e:
        logger.error(f"Error recognizing face: {e}")
        return None, 0


def process_attendance(
    personnel_id: int, confidence: float, base64_image: Optional[str] = None
) -> Dict[str, Any]:
    """Process attendance record for identified personnel.

    Handles time-in/time-out logic, cooldown periods, and duplicate prevention.
    Uses database locking to prevent race conditions.

    Args:
        personnel_id: ID of identified personnel
        confidence: Face recognition confidence score
        base64_image: Base64 encoded image for record keeping

    Returns:
        Dictionary with success status, action taken, and relevant data
    """
    try:
        # Get personnel data
        personnel = Personnel.query.get(personnel_id)
        if not personnel:
            return {"success": False, "error": "Personnel not found"}

        # Get current date and time
        today = datetime.now().date()
        current_time = datetime.now()

        # Define cooldown period
        cooldown_seconds = current_app.config.get("ATTENDANCE_COOLDOWN", 60)
        cooldown_period = timedelta(seconds=cooldown_seconds)

        # Use database locking to prevent race conditions
        # with_for_update() locks the row until transaction completes
        attendance = (
            Attendance.query.filter_by(personnel_id=personnel_id, date=today)
            .with_for_update()
            .first()
        )

        # Use database locking to prevent race conditions
        # with_for_update() locks the row until transaction completes
        attendance = (
            Attendance.query.filter_by(personnel_id=personnel_id, date=today)
            .with_for_update()
            .first()
        )

        # Check for any recent attendance within cooldown period
        if attendance:
            last_action_time = (
                attendance.time_out if attendance.time_out else attendance.time_in
            )
            if last_action_time:
                time_since_last_action = current_time - last_action_time

                if time_since_last_action < cooldown_period:
                    remaining_seconds = (
                        cooldown_period - time_since_last_action
                    ).total_seconds()
                    remaining_time = int(remaining_seconds)

                    return {
                        "success": True,
                        "action": "cooldown",
                        "personnel": {
                            "id": personnel.id,
                            "name": personnel.full_name,
                            "station": personnel.station.station_type.value,
                        },
                        "message": f"Please wait {remaining_time} seconds before recording attendance again",
                        "remaining_time": remaining_time,
                        "time_in": (
                            attendance.time_in.strftime("%I:%M:%S %p")
                            if attendance.time_in
                            else None
                        ),
                        "time_out": (
                            attendance.time_out.strftime("%I:%M:%S %p")
                            if attendance.time_out
                            else None
                        ),
                    }

        # If attendance record exists for today
        if attendance:
            # If time_out is not recorded yet, already have time-in
            if attendance.time_out is None:
                # Person already signed in for today
                return {
                    "success": True,
                    "action": "already_recorded",
                    "personnel": {
                        "id": personnel.id,
                        "name": personnel.full_name,
                        "station": personnel.station.station_type.value,
                    },
                    "message": "You have already recorded your time-in for today",
                    "time_in": (
                        attendance.time_in.strftime("%I:%M:%S %p")
                        if attendance.time_in
                        else None
                    ),
                    "time_out": None,
                }
            else:
                # Already completed attendance for the day (both time-in and time-out)
                return {
                    "success": True,
                    "action": "already_recorded",
                    "personnel": {
                        "id": personnel.id,
                        "name": personnel.full_name,
                        "station": personnel.station.station_type.value,
                    },
                    "time_in": (
                        attendance.time_in.strftime("%I:%M:%S %p")
                        if attendance.time_in
                        else None
                    ),
                    "time_out": (
                        attendance.time_out.strftime("%I:%M:%S %p")
                        if attendance.time_out
                        else None
                    ),
                }
        else:
            # Create new attendance record (time_in)
            # Parse work start time from config
            work_start_str = current_app.config.get("WORK_START_TIME", "08:00")
            hour, minute = map(int, work_start_str.split(":"))
            work_start_time = (
                datetime.now()
                .replace(hour=hour, minute=minute, second=0, microsecond=0)
                .time()
            )

            # Determine status based on time
            status = (
                AttendanceStatus.LATE
                if current_time.time() > work_start_time
                else AttendanceStatus.PRESENT
            )

            # Save the image if provided
            image_path = None
            if base64_image:
                image_path = save_attendance_image(
                    personnel.id, base64_image, "time_in"
                )

            # Create new attendance record
            new_attendance = Attendance(
                personnel_id=personnel_id,
                date=today,
                time_in=current_time,
                status=status,
                confidence_score=confidence,
                time_in_image=image_path,
            )

            db.session.add(new_attendance)
            db.session.commit()

            return {
                "success": True,
                "action": "time_in",
                "personnel": {
                    "id": personnel.id,
                    "name": personnel.full_name,
                    "station": personnel.station.station_type.value,
                },
                "time": current_time.strftime("%I:%M:%S %p"),
                "status": status.value,
            }

    except Exception as e:
        logger.error(f"Error processing attendance: {e}")
        return {"success": False, "error": f"Error processing attendance: {str(e)}"}


def save_attendance_image(
    personnel_id: int, base64_image: str, prefix: str
) -> Optional[str]:
    """Save attendance capture image for record keeping.

    Args:
        personnel_id: ID of personnel
        base64_image: Base64 encoded image data
        prefix: Filename prefix (e.g., 'time_in', 'time_out')

    Returns:
        Relative path to saved image or None if failed
    """
    try:
        # Remove data URL header if present
        if "," in base64_image:
            base64_image = base64_image.split(",")[1]

        # Decode base64 image
        image_data = base64.b64decode(base64_image)

        # Get personnel info
        personnel = Personnel.query.get(personnel_id)
        if not personnel:
            return None

        # Create folder if not exists - using temp folder for attendance images
        # Ensure no spaces in the folder name to prevent path errors
        folder_name = f"{personnel.last_name}_{personnel.first_name}".replace(" ", "")
        folder_path = os.path.join(
            current_app.config["TEMP_ATTENDANCE_FOLDER"], folder_name
        )
        os.makedirs(folder_path, exist_ok=True)

        # Create filename with timestamp and date for easier cleanup identification
        today = datetime.now().date().strftime("%Y%m%d")
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"{prefix}_{today}_{timestamp}.jpg"
        file_path = os.path.join(folder_path, filename)

        # Save image
        with open(file_path, "wb") as f:
            f.write(image_data)

        # Return the relative path that can be used in templates
        # Convert backslashes to forward slashes for URL compatibility
        relative_path = os.path.join(
            "attendance_images_temp", folder_name, filename
        ).replace("\\", "/")
        return relative_path

    except Exception as e:
        logger.error(f"Error saving attendance image: {e}")
        return None


def process_base64_image(
    base64_image: str,
) -> Tuple[Optional[List[float]], Optional[Dict[str, Any]], Optional[str]]:
    """Process base64 image data for face detection and embedding extraction.

    Validates input, detects face, and extracts embeddings.

    Args:
        base64_image: Base64 encoded image data

    Returns:
        Tuple of (face_embedding, face_metadata, temp_file_path) or (None, None, None)
    """
    try:
        # Validate base64 image before processing
        is_valid, error_msg = validate_base64_image(base64_image)
        if not is_valid:
            logger.warning(f"Base64 image validation failed: {error_msg}")
            return None, None, None
        # Remove data URL header if present
        if "," in base64_image:
            base64_image = base64_image.split(",")[1]

        # Decode base64 image
        image_bytes = base64.b64decode(base64_image)

        # Convert to OpenCV format
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # Run YOLO detection
        model = get_yolo_model()
        results = model(
            img, conf=current_app.config.get("FACE_DETECTION_CONFIDENCE", 0.5)
        )

        # Check if faces are detected
        if len(results) == 0 or len(results[0].boxes) == 0:
            return None, None, None

        # Get the face with highest confidence
        boxes = results[0].boxes
        confidences = boxes.conf.cpu().numpy()
        max_idx = np.argmax(confidences)

        # Get bounding box and confidence
        bbox = boxes.xyxy[max_idx].cpu().numpy().astype(int)
        confidence = float(confidences[max_idx])

        # Extract face
        face = img[bbox[1] : bbox[3], bbox[0] : bbox[2]]

        # Create a unique filename for the face image
        temp_filename = f"temp_{uuid.uuid4()}.jpg"
        temp_path = os.path.join(
            current_app.config["TEMP_ATTENDANCE_FOLDER"], temp_filename
        )

        # Save the face image temporarily
        cv2.imwrite(temp_path, face)

        # Extract face embedding
        face_embedding, face_metadata = extract_face_embeddings(temp_path)

        return face_embedding, face_metadata, temp_path

    except Exception as e:
        logger.error(f"Error processing base64 image: {e}")
        return None, None, None


def register_face(personnel_id: int, base64_images: List[str]) -> Dict[str, Any]:
    """Register multiple face images for a personnel member.

    Processes multiple face photos to create embeddings for improved recognition accuracy.
    Clears face database cache after successful registration.

    Args:
        personnel_id: ID of personnel to register faces for
        base64_images: List of base64 encoded image data

    Returns:
        Dictionary with success status and number of images registered
    """
    try:
        # Get personnel data
        personnel = Personnel.query.get(personnel_id)
        if not personnel:
            logger.error(f"Personnel not found: {personnel_id}")
            return {"success": False, "error": "Personnel not found"}

        # Create folder for personnel if not exists - ensure no spaces in the folder name
        folder_name = f"{personnel.last_name}_{personnel.first_name}".replace(" ", "")
        folder_path = os.path.join(current_app.config["UPLOAD_FOLDER"], folder_name)
        logger.info(f"Creating folder: {folder_path}")
        os.makedirs(folder_path, exist_ok=True)

        registered_images = []

        # Process each image
        logger.info(f"Processing {len(base64_images)} images")
        for i, base64_image in enumerate(base64_images):
            try:
                # Process the base64 image
                logger.info(f"Processing image {i+1}")
                face_embedding, face_metadata, temp_path = process_base64_image(
                    base64_image
                )

                # If no face detected or error, skip
                if face_embedding is None or temp_path is None:
                    logger.warning(f"No face detected in image {i+1}")
                    continue

                # Create a filename for the face image
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{folder_name}_{i:04d}_{timestamp}.jpg"
                file_path = os.path.join(folder_path, filename)
                logger.info(f"Saving image to: {file_path}")

                # Move the temporary file to the permanent location
                if os.path.exists(temp_path):
                    # Copy instead of rename to avoid issues if the file exists
                    import shutil

                    shutil.copy2(temp_path, file_path)
                    os.remove(temp_path)
                    logger.info(f"Copied temp file to: {file_path}")
                else:
                    logger.warning(f"Temp file does not exist: {temp_path}")

                # Save face data to database
                logger.info(
                    f"Saving face data to database for personnel {personnel_id}"
                )
                face_data = FaceData(
                    personnel_id=personnel_id,
                    filename=filename,
                    embedding=json.dumps(face_embedding),
                    confidence=(
                        face_metadata.get("confidence") if face_metadata else None
                    ),
                )

                db.session.add(face_data)
                registered_images.append(filename)
                logger.info(f"Added face data for image {i+1}")

            except Exception as e:
                logger.error(f"Error registering face image {i}: {e}")
                # Clean up temporary file if exists
                if "temp_path" in locals() and temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)

        # Set profile image if not already set
        if len(registered_images) > 0:
            # Use the first successfully registered face image as profile photo
            best_face = registered_images[0]  # Just use the first one for now

            # Get the correct path format for static files
            relative_path = os.path.join(
                "images",
                "face_data",
                f"{personnel.last_name}_{personnel.first_name}".replace(" ", ""),
                best_face,
            ).replace("\\", "/")

            # Update the personnel's image path (always update, even if one already exists)
            logger.info(
                f"Setting profile image for {personnel.full_name}: {relative_path}"
            )
            personnel.image_path = relative_path

        # Commit all changes
        logger.info(
            f"Committing changes to database, {len(registered_images)} images registered"
        )
        db.session.commit()
        logger.info(f"Database commit successful")

        # Clear face database cache since we added new face data
        clear_face_database_cache()

        return {
            "success": True,
            "message": f"Successfully registered {len(registered_images)} face images",
            "registered_images": registered_images,
        }

    except Exception as e:
        logger.error(f"Error registering faces: {e}")
        db.session.rollback()
        return {"success": False, "error": f"Error registering faces: {str(e)}"}


def cleanup_old_attendance_images() -> None:
    """Clean up old attendance images to free disk space.

    Deletes attendance images older than the configured retention period.
    Should be called periodically (e.g., daily) via cron job or task scheduler.

    The retention period is configurable via ATTENDANCE_IMAGE_RETENTION_DAYS setting.
    """
    try:
        logger.info("Starting cleanup of old attendance images")

        # Get the retention period from config
        retention_days = current_app.config.get("ATTENDANCE_IMAGE_RETENTION_DAYS", 1)
        cutoff_date = datetime.now() - timedelta(days=retention_days)

        # Get the temporary attendance folder
        temp_folder = current_app.config.get("TEMP_ATTENDANCE_FOLDER")
        if not os.path.exists(temp_folder):
            logger.warning(f"Temp attendance folder does not exist: {temp_folder}")
            return

        deleted_count = 0

        # Iterate through all personnel folders in the temp folder
        for personnel_folder in os.listdir(temp_folder):
            personnel_path = os.path.join(temp_folder, personnel_folder)

            # Skip if not a directory
            if not os.path.isdir(personnel_path):
                # If it's a file at the root level, check if it's a temp file
                if os.path.isfile(personnel_path) and personnel_folder.startswith(
                    "temp_"
                ):
                    try:
                        # Get file creation time or modification time
                        file_time = datetime.fromtimestamp(
                            os.path.getmtime(personnel_path)
                        )
                        if file_time < cutoff_date:
                            os.remove(personnel_path)
                            deleted_count += 1
                            logger.debug(
                                f"Deleted old temporary file: {personnel_path}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Error processing temporary file {personnel_path}: {e}"
                        )
                continue

            # Check each file in the personnel folder
            for filename in os.listdir(personnel_path):
                file_path = os.path.join(personnel_path, filename)

                # Skip if not a file
                if not os.path.isfile(file_path):
                    continue

                # Check if it's a temp file (for face registration)
                if filename.startswith("temp_"):
                    try:
                        # Get file creation time or modification time
                        file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                        if file_time < cutoff_date:
                            os.remove(file_path)
                            deleted_count += 1
                            logger.debug(f"Deleted old temporary file: {file_path}")
                    except Exception as e:
                        logger.error(
                            f"Error processing temporary file {file_path}: {e}"
                        )
                    continue

                # Parse the date from the filename (format: prefix_YYYYMMDD_HHMMSS.jpg)
                try:
                    # Extract date part from filename (expects format like time_in_20240515_123045.jpg)
                    parts = filename.split("_")
                    if len(parts) >= 3:
                        date_str = parts[-2]  # Get the date part (YYYYMMDD)
                        if len(date_str) == 8:  # Ensure it's a valid date format
                            file_date = datetime.strptime(date_str, "%Y%m%d")

                            # Delete if older than retention period
                            if file_date < cutoff_date:
                                os.remove(file_path)
                                deleted_count += 1
                                logger.debug(
                                    f"Deleted old attendance image: {file_path}"
                                )
                except Exception as e:
                    logger.error(f"Error parsing date from filename {filename}: {e}")
                    continue

            # Remove empty personnel folders
            try:
                if os.path.exists(personnel_path) and not os.listdir(personnel_path):
                    os.rmdir(personnel_path)
                    logger.debug(f"Removed empty personnel folder: {personnel_path}")
            except Exception as e:
                logger.error(f"Error removing empty folder {personnel_path}: {e}")

        logger.info(
            f"Attendance image cleanup complete. Deleted {deleted_count} old images."
        )

    except Exception as e:
        logger.error(f"Error during attendance image cleanup: {e}")
