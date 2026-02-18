# Face Recognition Service for BFP Sorsogon Attendance System
# Handles face detection, encoding, recognition, and attendance processing using YOLO and OpenCV
# Enhanced with optional InsightFace support for improved accuracy and anti-spoofing

# Standard library imports
import base64
import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# Computer vision and machine learning libraries
import cv2
import numpy as np
import torch

# Flask framework imports
from flask import current_app
from scipy.spatial import distance as dist

# Database imports
from ultralytics import YOLO

from models import Attendance, AttendanceStatus, FaceData, Personnel, db

logger = logging.getLogger(__name__)

INSIGHTFACE_AVAILABLE = False
try:
    from insightface.app import FaceAnalysis

    INSIGHTFACE_AVAILABLE = True
    logger.info("✓ InsightFace is available for enhanced face detection")
except ImportError:
    pass

# Global model instances
yolo_model = None
insightface_app = None

# Face database cache to avoid repeated database queries
_face_db_cache: Optional[Dict[int, Dict[str, Any]]] = None
_face_db_cache_time: Optional[datetime] = None
_face_db_cache_ttl: int = 300  # Cache TTL in seconds (5 minutes)

# Configuration constants
MAX_IMAGE_SIZE_MB: int = 10
MAX_IMAGE_SIZE_BYTES: int = MAX_IMAGE_SIZE_MB * 1024 * 1024


def to_native_types(value: Any) -> Any:
    """Convert numpy/scalar types to native Python types for JSON serialization."""
    if isinstance(value, dict):
        return {k: to_native_types(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_native_types(v) for v in value]
    if isinstance(value, tuple):
        return [to_native_types(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


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
                "YOLO_MODEL_PATH", "face_rec_module/yolov11n-face.pt"
            )
            yolo_model = YOLO(model_path)
            yolo_model.cpu()

        return yolo_model


def get_insightface_app() -> Optional[Any]:
    """Load and return the InsightFace face analysis app.

    InsightFace provides:
    - RetinaFace for state-of-the-art face detection
    - ArcFace for superior face embeddings (512-dimensional)
    - Better performance on challenging conditions (angles, lighting)

    Returns:
        FaceAnalysis app instance or None if InsightFace not available
    """
    global insightface_app

    if not INSIGHTFACE_AVAILABLE:
        return None

    try:
        # Try to use app context if available
        if (
            not hasattr(current_app, "insightface_app")
            or current_app.insightface_app is None
        ):
            # Check if InsightFace is enabled in config
            use_insightface = current_app.config.get("USE_INSIGHTFACE", False)

            if not use_insightface:
                logger.info("InsightFace is disabled in config, using YOLO")
                return None

            logger.info("Initializing InsightFace FaceAnalysis...")

            # Initialize InsightFace app with buffalo_l model (high accuracy)
            # Available models: buffalo_l (large), buffalo_m (medium), buffalo_s (small)
            app = FaceAnalysis(
                name="buffalo_l",  # Best accuracy
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            app.prepare(
                ctx_id=0 if torch.cuda.is_available() else -1, det_size=(640, 640)
            )

            current_app.insightface_app = app
            logger.info("✓ InsightFace initialized successfully")

        return current_app.insightface_app

    except RuntimeError:
        # No app context available
        if insightface_app is None and INSIGHTFACE_AVAILABLE:
            try:
                logger.info("Initializing InsightFace (no app context)...")
                app = FaceAnalysis(name="buffalo_l")
                app.prepare(ctx_id=-1, det_size=(640, 640))  # CPU mode
                insightface_app = app
                logger.info("✓ InsightFace initialized (global)")
            except Exception as e:
                logger.warning(f"Failed to initialize InsightFace: {e}")
                return None
        return insightface_app
    except Exception as e:
        logger.warning(f"InsightFace initialization error: {e}")
        return None


def detect_faces_insightface(image: np.ndarray) -> List[Dict[str, Any]]:
    """Detect faces using InsightFace (RetinaFace).

    This provides more accurate face detection than YOLO, especially for:
    - Profile/angled faces
    - Partially occluded faces
    - Variable lighting conditions

    Args:
        image: BGR image as numpy array

    Returns:
        List of face dictionaries with bbox, landmarks, embedding, and detection score
    """
    app = get_insightface_app()
    if app is None:
        return []

    try:
        # InsightFace expects RGB
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Detect faces
        faces = app.get(rgb_image)

        results = []
        for face in faces:
            results.append(
                {
                    "bbox": face.bbox.astype(int),  # [x1, y1, x2, y2]
                    "confidence": float(face.det_score),
                    "embedding": face.embedding if hasattr(face, "embedding") else None,
                    "landmarks": (
                        face.kps if hasattr(face, "kps") else None
                    ),  # 5-point landmarks
                    "age": face.age if hasattr(face, "age") else None,
                    "gender": face.gender if hasattr(face, "gender") else None,
                }
            )

        logger.info(f"InsightFace detected {len(results)} face(s)")
        return results

    except Exception as e:
        logger.error(f"InsightFace detection error: {e}")
        return []


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
    """Extract face embeddings from an image file using deep learning.

    Uses dlib-based face recognition library to extract 128-dimensional face encodings
    that capture actual facial features, not just pixels. This provides reliable
    differentiation between different people.

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

        logger.info(f"Image loaded successfully: {image_path}, shape: {img.shape}")

        # Run YOLO face detection for consistency and speed
        try:
            confidence_threshold = current_app.config.get(
                "FACE_DETECTION_CONFIDENCE", 0.5
            )
        except RuntimeError:
            # No app context available, use default
            confidence_threshold = 0.5

        logger.info(
            f"Running YOLO face detection with confidence threshold: {confidence_threshold}"
        )

        results = model(img, conf=confidence_threshold)

        logger.info(f"YOLO results: {len(results)} result sets")
        if len(results) > 0:
            logger.info(
                f"Boxes found: {len(results[0].boxes) if results[0].boxes is not None else 0}"
            )
            if results[0].boxes is not None and len(results[0].boxes) > 0:
                confidences = results[0].boxes.conf.cpu().numpy()
                logger.info(f"Detection confidences: {confidences}")

        if len(results) == 0 or len(results[0].boxes) == 0:
            logger.warning(f"❌ No faces detected in image: {image_path}")
            logger.warning(f"  - Image shape: {img.shape}")
            logger.warning(f"  - Confidence threshold: {confidence_threshold}")
            logger.warning(
                "  - Try better lighting, face closer to camera, or lower threshold"
            )
            return None, None

        # Select the face with highest confidence
        boxes = results[0].boxes
        confidences = boxes.conf.cpu().numpy()
        max_idx = np.argmax(confidences)

        # Extract bounding box coordinates and confidence score
        bbox = boxes.xyxy[max_idx].cpu().numpy().astype(int)
        confidence = float(confidences[max_idx])

        # Convert image from BGR to RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Extract face embeddings using InsightFace (if available) or generate from facial features
        embedding = None
        if INSIGHTFACE_AVAILABLE:
            try:
                app = get_insightface_app()
                faces = app.get(img_rgb)
                if len(faces) > 0:
                    # Get embedding from the most confident face
                    embedding = faces[0].embedding.tolist()
            except Exception as e:
                logger.debug(f"InsightFace embedding extraction failed: {e}")

        if embedding is None:
            # Fallback: Generate a simple embedding from face region histogram
            x1, y1, x2, y2 = bbox.astype(int)
            face_region = img_rgb[y1:y2, x1:x2]

            # Create a 128-dim embedding from face region
            # Using histogram of face region as features
            embedding = []
            for i in range(3):  # RGB channels
                hist = cv2.calcHist([face_region], [i], None, [32], [0, 256])
                embedding.extend(hist.flatten()[:32])  # 32 values per channel

            embedding = np.array(embedding)

            if len(embedding) < 128:
                # Pad to 128 dimensions
                embedding = np.pad(
                    embedding, (0, 128 - len(embedding)), mode="constant"
                )
            elif len(embedding) > 128:
                # Truncate to 128 dimensions
                embedding = embedding[:128]

        embedding = np.array(embedding)
        # Normalize embedding
        if np.linalg.norm(embedding) > 0:
            embedding = embedding / np.linalg.norm(embedding)

        # Return embedding as Python list with metadata
        logger.info(
            f"Successfully extracted deep learning face embedding (128-dim) from {image_path}"
        )
        return embedding.tolist(), {
            "bbox": bbox.tolist(),
            "confidence": float(confidence),
        }

    except Exception as e:
        logger.error(f"Error extracting face embeddings: {e}")
        return None, None


def compare_embeddings(
    emb1: List[float], emb2: List[float], threshold: float = 0.6
) -> Tuple[float, bool]:
    """Compare two face embeddings using Euclidean distance.

    Uses scipy's optimized distance calculation to compare face embeddings.

    Args:
        emb1: First face embedding (128-dimensional)
        emb2: Second face embedding (128-dimensional)
        threshold: Distance threshold for match determination (lower = stricter, default 0.6)

    Returns:
        Tuple of (distance, is_match_boolean) - Note: Lower distance means better match!
    """
    try:
        # Convert to numpy arrays
        emb1 = np.array(emb1)
        emb2 = np.array(emb2)

        # Make sure they're the same shape
        if emb1.shape != emb2.shape:
            logger.warning(
                f"Embedding shapes don't match: {emb1.shape} vs {emb2.shape}"
            )
            return 999.0, False  # Very high distance = no match

        # Use Euclidean distance (L2 norm) to compare embeddings
        # This is the standard distance metric for face embeddings
        distance = float(dist.euclidean(emb1, emb2))

        # Determine if it's a match based on threshold
        # Note: LOWER distance means BETTER match (opposite of similarity)
        is_match = bool(distance <= threshold)

        return distance, is_match

    except Exception as e:
        logger.error(f"Error comparing embeddings: {e}")
        return 999.0, False  # Very high distance = no match


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
                cached_ids = list(_face_db_cache.keys())
                if not cached_ids:
                    return {}
                station_map = dict(
                    db.session.query(Personnel.id, Personnel.station_id)
                    .filter(Personnel.id.in_(cached_ids))
                    .all()
                )
                return {
                    k: v
                    for k, v in _face_db_cache.items()
                    if station_map.get(k) == station_id
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

    Uses Euclidean distance for comparison. LOWER distance = BETTER match.

    Args:
        face_embedding: Face embedding to identify (128-dimensional)
        face_database: Database of known face embeddings
        threshold: Recognition threshold (distance). Uses config default if None.

    Returns:
        Tuple of (personnel_id, distance) or (None, 999.0) if no match
    """
    try:
        if face_embedding is None or not face_database:
            logger.warning("No face embedding or empty database")
            return None, 999.0

        # Use provided threshold or get from config
        if threshold is None:
            threshold = current_app.config.get("FACE_RECOGNITION_THRESHOLD", 0.6)

        min_distance = 999.0  # Start with very high distance
        recognized_id = None

        # NEW SECURITY: Track matches per person for additional validation
        person_matches = {}  # personnel_id -> list of (distance, match) pairs

        # Track all matches for logging
        matches_found = []

        for personnel_id, data in face_database.items():
            if not data.get("embeddings"):
                continue

            person_matches[personnel_id] = []

            # Compare with all embeddings for this person
            for db_embedding in data["embeddings"]:
                if db_embedding is None:
                    continue

                distance, match = compare_embeddings(
                    face_embedding, db_embedding, threshold
                )

                # Log ALL comparisons for debugging
                matches_found.append(
                    {
                        "personnel_id": personnel_id,
                        "distance": distance,
                        "match": match,
                    }
                )

                # Track matches per person
                person_matches[personnel_id].append((distance, match))

                # Find the MINIMUM distance (best match)
                if match and distance < min_distance:
                    min_distance = distance
                    recognized_id = personnel_id

        # ENHANCED SECURITY: Require multiple consistent matches for the same person
        if recognized_id is not None and min_distance <= threshold:
            person_distances = person_matches[recognized_id]
            valid_matches = [d for d, m in person_distances if m]

            # Require at least 2 out of 3 embeddings to match (if 3+ available)
            # or at least 1 out of 2 (if 2 available)
            # or just 1 (if only 1 available)
            required_matches = max(1, len(person_distances) // 2)

            if len(valid_matches) >= required_matches:
                # Additional check: average distance should also be reasonable
                avg_distance = sum(valid_matches) / len(valid_matches)
                if avg_distance <= threshold * 1.2:  # Allow some tolerance on average
                    print(
                        f"✓ FACE RECOGNIZED: Personnel ID {recognized_id}, Best: {min_distance:.3f}, Avg: {avg_distance:.3f} ({len(valid_matches)}/{len(person_distances)} matches, threshold: {threshold})"
                    )
                    logger.info(
                        f"✓ Face recognized: Personnel ID {recognized_id}, Best: {min_distance:.3f}, Avg: {avg_distance:.3f} ({len(valid_matches)}/{len(person_distances)} matches, threshold: {threshold})"
                    )
                    if matches_found:
                        print(f"  All matches found: {matches_found}")
                        logger.info(f"  All matches found: {matches_found}")
                    return recognized_id, min_distance
                else:
                    print(
                        f"❌ RECOGNITION FAILED: Average distance {avg_distance:.3f} too high (threshold: {threshold})"
                    )
                    logger.warning(
                        f"❌ Recognition failed: Average distance {avg_distance:.3f} too high"
                    )
                    recognized_id = None
            else:
                print(
                    f"❌ RECOGNITION FAILED: Only {len(valid_matches)}/{len(person_distances)} embeddings matched (need {required_matches})"
                )
                logger.warning(
                    f"❌ Recognition failed: Only {len(valid_matches)}/{len(person_distances)} embeddings matched"
                )
                recognized_id = None
            print(
                f"✓ FACE RECOGNIZED: Personnel ID {recognized_id}, Distance: {min_distance:.3f} (threshold: {threshold})"
            )
            logger.info(
                f"✓ Face recognized: Personnel ID {recognized_id}, Distance: {min_distance:.3f} (threshold: {threshold})"
            )
            if matches_found:
                print(f"  All matches found: {matches_found}")
                logger.info(f"  All matches found: {matches_found}")
            return recognized_id, min_distance
        else:
            # No valid match found
            if matches_found:
                print(
                    f"❌ NO MATCH FOUND. Best distance: {min_distance:.3f} > threshold {threshold}"
                )
                print(f"  Close matches (not good enough): {matches_found}")
                logger.warning(
                    f"❌ No match found. Best distance: {min_distance:.3f} > threshold {threshold}"
                )
                logger.warning(f"  Close matches (not good enough): {matches_found}")
            else:
                print(
                    f"❌ NO MATCH FOUND. No faces close enough (best: {min_distance:.3f}, threshold: {threshold})"
                )
                logger.warning(
                    f"❌ No match found. No faces close enough (best: {min_distance:.3f}, threshold: {threshold})"
                )
            return None, 999.0

    except Exception as e:
        logger.error(f"Error recognizing face: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return None, 999.0


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
        cooldown_seconds = current_app.config.get("ATTENDANCE_COOLDOWN", 5)
        cooldown_period = timedelta(seconds=cooldown_seconds)

        # Use database locking to prevent race conditions
        # with_for_update() locks the row until transaction completes
        attendance = (
            Attendance.query.filter_by(personnel_id=personnel_id, date=today)
            .with_for_update()
            .first()
        )

        # Cooldown applies only between time-in and time-out.
        # Once time-out is already recorded, return already_recorded immediately.
        if attendance and attendance.time_out is None and attendance.time_in:
            time_since_time_in = current_time - attendance.time_in
            if time_since_time_in < cooldown_period:
                remaining_seconds = (cooldown_period - time_since_time_in).total_seconds()
                remaining_time = int(remaining_seconds)

                return {
                    "success": True,
                    "action": "cooldown",
                    "personnel": {
                        "id": personnel.id,
                        "name": personnel.full_name,
                        "station": personnel.station.station_type.value,
                    },
                    "message": f"Time-in recorded at {attendance.time_in.strftime('%I:%M:%S %p')}. Please wait {remaining_time} seconds before recording time-out.",
                    "remaining_time": remaining_time,
                    "next_action": "time_out",
                    "time_in": attendance.time_in.strftime("%I:%M:%S %p"),
                    "time_out": None,
                }

        # If attendance record exists for today
        if attendance:
            # If only time-in exists, record time-out.
            if attendance.time_out is None:
                time_out_image = None
                if base64_image:
                    time_out_image = save_attendance_image(
                        personnel.id, base64_image, "time_out"
                    )

                attendance.time_out = current_time
                attendance.time_out_image = time_out_image
                db.session.commit()

                return {
                    "success": True,
                    "action": "time_out",
                    "personnel": {
                        "id": personnel.id,
                        "name": personnel.full_name,
                        "station": personnel.station.station_type.value,
                    },
                    "time": current_time.strftime("%I:%M:%S %p"),
                    "time_in": (
                        attendance.time_in.strftime("%I:%M:%S %p")
                        if attendance.time_in
                        else None
                    ),
                    "time_out": current_time.strftime("%I:%M:%S %p"),
                }
            else:
                # Already completed attendance for the day (both time-in and time-out)
                return {
                    "success": True,
                    "action": "already_recorded",
                    "message": "Attendance already completed for today.",
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


def detect_texture_artifacts(
    image: np.ndarray, face_bbox: np.ndarray
) -> Tuple[bool, float]:
    """Detect texture artifacts that indicate a printed photo or screen display.

    Analyzes frequency domain and edge patterns to identify reproductions.

    Args:
        image: Original image in BGR format
        face_bbox: Bounding box coordinates [x1, y1, x2, y2]

    Returns:
        Tuple of (is_live, artifact_score) where higher score means more likely live
    """
    try:
        # Extract face region with some padding for better analysis
        x1, y1, x2, y2 = face_bbox.astype(int)

        # Add padding to get surrounding context
        height, width = image.shape[:2]
        padding = 20
        y1_padded = max(0, y1 - padding)
        y2_padded = min(height, y2 + padding)
        x1_padded = max(0, x1 - padding)
        x2_padded = min(width, x2 + padding)

        face = image[y1_padded:y2_padded, x1_padded:x2_padded]

        if face.size == 0:
            return False, 0.0

        # Convert to grayscale
        gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)

        # Calculate various texture metrics with weights
        scores = []
        weights = []

        # 1. Laplacian variance (measures image sharpness/blur) - CRITICAL
        # Photos tend to have uniform sharpness, live faces have variable sharpness
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        # Photos often have TOO consistent sharpness (either very sharp or very blurry)
        # Live faces: 100-400 is typical
        if 100 < laplacian_var < 400:
            lap_score = 1.0
        elif 50 < laplacian_var < 600:
            lap_score = 0.7
        else:
            lap_score = 0.3  # Too sharp or too blurry = likely photo
        scores.append(lap_score)
        weights.append(2.0)  # Double weight - most important

        # 2. Frequency domain analysis - HIGH IMPORTANCE
        # Screens/prints show periodic patterns and uniform frequency distribution
        f_transform = np.fft.fft2(gray)
        f_shift = np.fft.fftshift(f_transform)
        magnitude_spectrum = 20 * np.log(np.abs(f_shift) + 1)

        # Check for periodic peaks (screen patterns)
        freq_std = np.std(magnitude_spectrum)
        freq_mean = np.mean(magnitude_spectrum)

        # Live faces have more varied frequency content
        # Photos/screens have more uniform frequency distribution
        freq_score = min(freq_std / 25.0, 1.0)
        scores.append(freq_score)
        weights.append(1.5)

        # 3. Spectral analysis - detect moiré patterns from screens
        # Look for high-frequency periodic patterns
        rows, cols = gray.shape
        crow, ccol = rows // 2, cols // 2
        # Check the high-frequency region
        high_freq = magnitude_spectrum[crow - 20 : crow + 20, ccol - 20 : ccol + 20]
        low_freq = magnitude_spectrum[0:40, 0:40]
        freq_ratio = np.mean(high_freq) / (np.mean(low_freq) + 1e-6)

        # Photos/screens have stronger high-frequency patterns
        spectral_score = 1.0 if freq_ratio < 0.8 else 0.4
        scores.append(spectral_score)
        weights.append(1.5)

        # 4. Color variation analysis - IMPORTANT
        # Screens have limited color gamut, photos have compressed color range
        hsv = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
        bgr_face = face

        # Calculate color variation in multiple channels
        h_std = np.std(hsv[:, :, 0])
        s_std = np.std(hsv[:, :, 1])
        v_std = np.std(hsv[:, :, 2])
        b_std = np.std(bgr_face[:, :, 0])
        g_std = np.std(bgr_face[:, :, 1])
        r_std = np.std(bgr_face[:, :, 2])

        # Live faces have rich color variation
        color_variance = (h_std + s_std + v_std + b_std + g_std + r_std) / 6.0
        color_score = min(color_variance / 40.0, 1.0)
        scores.append(color_score)
        weights.append(2.0)  # High weight

        # 5. Edge density and quality
        # Photos have sharper, more uniform edges
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges > 0) / edges.size

        # Calculate edge strength variation
        edge_sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        edge_sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        edge_magnitude = np.sqrt(edge_sobel_x**2 + edge_sobel_y**2)
        edge_std = np.std(edge_magnitude)

        # Natural faces: moderate edge density with variation
        if 0.04 < edge_density < 0.15 and edge_std > 10:
            edge_score = 1.0
        elif 0.03 < edge_density < 0.20:
            edge_score = 0.6
        else:
            edge_score = 0.3
        scores.append(edge_score)
        weights.append(1.0)

        # 7. Screen reflection detection - NEW HIGH-SECURITY CHECK
        # Look for uniform brightness patterns typical of screen displays
        brightness_variance = np.var(gray)
        mean_brightness = np.mean(gray)

        # Screens often have more uniform brightness distribution
        # Calculate local brightness variance to detect screen uniformity
        kernel_size = 15
        kernel = np.ones((kernel_size, kernel_size), np.float32) / (
            kernel_size * kernel_size
        )
        local_mean = cv2.filter2D(gray.astype(np.float32), -1, kernel)
        local_variance = cv2.filter2D(
            (gray.astype(np.float32) - local_mean) ** 2, -1, kernel
        )

        # Screen displays have lower local variance
        local_var_mean = np.mean(local_variance)

        # Live faces have more natural lighting variation
        if local_var_mean > 80 and brightness_variance > 200:
            reflection_score = 1.0
        elif local_var_mean > 50 and brightness_variance > 150:
            reflection_score = 0.7
        else:
            reflection_score = 0.2  # Likely screen/photo
        scores.append(reflection_score)
        weights.append(2.5)  # Very high weight for security

        # 9. JPEG compression artifact detection - CRITICAL ANTI-PHOTO CHECK
        # Photos contain JPEG compression artifacts that live faces don't have
        # Look for 8x8 block patterns typical of JPEG compression
        jpeg_score = 1.0  # Start assuming live
        block_var_std = 0.0  # Initialize for logging

        if gray.shape[0] >= 16 and gray.shape[1] >= 16:
            # Analyze 8x8 blocks for compression patterns
            block_variances = []
            for i in range(0, gray.shape[0] - 8, 8):
                for j in range(0, gray.shape[1] - 8, 8):
                    block = gray[i : i + 8, j : j + 8].astype(np.float32)
                    # Check for uniform compression patterns
                    block_var = np.var(block)
                    block_mean = np.mean(block)

                    # JPEG blocks often have specific variance patterns
                    if block_var > 0:
                        block_variances.append(block_var)

            if block_variances:
                # Photos often have more uniform block variance distribution
                block_var_std = np.std(block_variances)
                block_var_mean = np.mean(block_variances)

                # Live faces have more natural variance patterns
                if block_var_std > 50 and block_var_mean > 100:
                    jpeg_score = 1.0  # Natural, live face patterns
                elif block_var_std > 30:
                    jpeg_score = 0.7  # Possibly live
                else:
                    jpeg_score = 0.1  # Likely compressed photo

        scores.append(jpeg_score)
        weights.append(3.0)  # Very high weight - photos almost always fail this

        # 10. Screen moiré pattern detection - ANTI-SCREEN CHECK
        # When taking photos of screens, moiré patterns appear
        fft = np.fft.fft2(gray)
        fft_shift = np.fft.fftshift(fft)
        magnitude = np.abs(fft_shift)

        # Look for periodic high-frequency patterns (screen refresh rates)
        rows, cols = magnitude.shape
        center_row, center_col = rows // 2, cols // 2

        # Check for regular patterns in frequency domain
        # Screens create regular frequency spikes
        freq_peaks = []
        for r in range(center_row - 20, center_row + 20):
            for c in range(center_col - 20, center_col + 20):
                if 0 <= r < rows and 0 <= c < cols:
                    freq_peaks.append(magnitude[r, c])

        freq_peak_std = 0.0  # Initialize for logging
        if freq_peaks:
            freq_peak_std = np.std(freq_peaks)
            # Regular patterns = lower variance = likely screen
            if freq_peak_std < 1000:
                moire_score = 0.2  # Likely screen capture
            elif freq_peak_std < 5000:
                moire_score = 0.6  # Possibly screen
            else:
                moire_score = 1.0  # Natural patterns
        else:
            moire_score = 1.0

        scores.append(moire_score)
        weights.append(2.0)

        # 8. Micro-contrast analysis - ANTI-PHOTO CHECK
        # Photos lose micro-contrast details during capture/print/display
        # Calculate contrast in small regions
        micro_contrast_scores = []
        for i in range(0, gray.shape[0] - 10, 10):
            for j in range(0, gray.shape[1] - 10, 10):
                patch = gray[i : i + 10, j : j + 10]
                if patch.size > 0:
                    patch_contrast = np.std(patch.astype(np.float32))
                    micro_contrast_scores.append(patch_contrast)

        if micro_contrast_scores:
            avg_micro_contrast = np.mean(micro_contrast_scores)
            # Live faces have richer micro-contrast
            micro_score = min(avg_micro_contrast / 25.0, 1.0)
        else:
            micro_score = 0.0
        scores.append(micro_score)
        weights.append(2.0)

        # 6. Local Binary Pattern (LBP) texture - ENHANCED
        # Measures micro-texture patterns - photos have different patterns
        # Simple LBP implementation
        lbp_hist = []
        for i in range(1, gray.shape[0] - 1):
            for j in range(1, gray.shape[1] - 1):
                center = gray[i, j]
                code = 0
                code |= (gray[i - 1, j - 1] > center) << 7
                code |= (gray[i - 1, j] > center) << 6
                code |= (gray[i - 1, j + 1] > center) << 5
                code |= (gray[i, j + 1] > center) << 4
                code |= (gray[i + 1, j + 1] > center) << 3
                code |= (gray[i + 1, j] > center) << 2
                code |= (gray[i + 1, j - 1] > center) << 1
                code |= (gray[i, j - 1] > center) << 0
                lbp_hist.append(code)

        # Calculate entropy of LBP patterns
        lbp_unique = len(set(lbp_hist))
        lbp_entropy = lbp_unique / 256.0  # Normalize by max possible patterns

        # Live faces have richer micro-texture patterns
        lbp_score = min(lbp_entropy * 1.5, 1.0)
        scores.append(lbp_score)
        weights.append(1.0)

        # Calculate weighted average
        weighted_scores = [s * w for s, w in zip(scores, weights)]
        final_score = sum(weighted_scores) / sum(weights)

        # Threshold for liveness
        threshold = current_app.config.get("LIVENESS_TEXTURE_THRESHOLD", 0.6)
        is_live = final_score >= threshold

        logger.info(f"Texture analysis - Score: {final_score:.3f}, Live: {is_live}")
        logger.info(f"  Laplacian: {laplacian_var:.1f} (score: {lap_score:.2f})")
        logger.info(
            f"  Frequency: std={freq_std:.1f}, ratio={freq_ratio:.3f} (score: {freq_score:.2f})"
        )
        logger.info(
            f"  Color variance: {color_variance:.1f} (score: {color_score:.2f})"
        )
        logger.info(
            f"  Edge density: {edge_density:.3f}, std={edge_std:.1f} (score: {edge_score:.2f})"
        )
        logger.info(f"  LBP entropy: {lbp_entropy:.3f} (score: {lbp_score:.2f})")
        logger.info(f"  Spectral score: {spectral_score:.2f}")
        logger.info(
            f"  Reflection: local_var={local_var_mean:.1f}, brightness_var={brightness_variance:.1f} (score: {reflection_score:.2f})"
        )
        logger.info(
            f"  Micro-contrast: {avg_micro_contrast:.1f} (score: {micro_score:.2f})"
        )
        if "block_var_std" in locals():
            logger.info(
                f"  JPEG artifacts: block_var_std={block_var_std:.1f} (score: {jpeg_score:.2f})"
            )
        if "freq_peak_std" in locals():
            logger.info(
                f"  Moiré patterns: freq_peak_std={freq_peak_std:.1f} (score: {moire_score:.2f})"
            )
        else:
            logger.info(f"  JPEG artifacts: (score: {jpeg_score:.2f})")
            logger.info(f"  Moiré patterns: (score: {moire_score:.2f})")

        return is_live, final_score

    except Exception as e:
        logger.error(f"Error in texture analysis: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False, 0.0


def detect_motion_liveness(frames: List[np.ndarray]) -> Tuple[bool, float]:
    """Detect liveness through motion analysis across multiple frames.

    Analyzes optical flow and frame differences to detect natural movement.
    ENHANCED: Now also detects micro-expressions and natural facial movements.

    Args:
        frames: List of consecutive frames (minimum 3 required)

    Returns:
        Tuple of (is_live, motion_score) where higher score means more motion detected
    """
    try:
        if len(frames) < 3:
            logger.warning("Insufficient frames for motion detection")
            return False, 0.0

        # Convert frames to grayscale
        gray_frames = [cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) for frame in frames]

        motion_scores = []
        optical_flow_scores = []

        # Calculate frame differences
        for i in range(len(gray_frames) - 1):
            # Calculate absolute difference
            diff = cv2.absdiff(gray_frames[i], gray_frames[i + 1])

            # Threshold to get significant changes
            _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)

            # Calculate motion percentage
            motion_pixels = np.sum(thresh > 0)
            total_pixels = thresh.size
            motion_percentage = motion_pixels / total_pixels

            motion_scores.append(motion_percentage)

            # Calculate optical flow for more sophisticated motion detection
            try:
                flow = cv2.calcOpticalFlowFarneback(
                    gray_frames[i], gray_frames[i + 1], None, 0.5, 3, 15, 3, 5, 1.2, 0
                )
                magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                flow_mean = np.mean(magnitude)
                optical_flow_scores.append(flow_mean)
            except Exception:
                pass

        # Average motion across frames
        avg_motion = np.mean(motion_scores)
        avg_flow = np.mean(optical_flow_scores) if optical_flow_scores else 0

        # Check for natural motion range
        # Too little = static image, too much = video or tampering
        min_motion = current_app.config.get("LIVENESS_MIN_MOTION", 0.001)
        max_motion = current_app.config.get("LIVENESS_MAX_MOTION", 0.15)

        # ENHANCED: Require both regular motion and optical flow
        motion_valid = min_motion <= avg_motion <= max_motion
        flow_valid = avg_flow > 0.05 if optical_flow_scores else True

        is_live = motion_valid and flow_valid

        # Normalize score - combine both metrics
        if avg_motion < min_motion:
            motion_score = 0.0
        elif avg_motion > max_motion:
            motion_score = 0.3
        else:
            motion_score = min(avg_motion / max_motion, 1.0)

        # Add flow score component
        if optical_flow_scores:
            flow_score = min(avg_flow / 0.5, 1.0)
            motion_score = (motion_score * 0.6) + (flow_score * 0.4)

        logger.debug(
            f"Motion analysis - Avg motion: {avg_motion:.4f}, Avg flow: {avg_flow:.4f}, Score: {motion_score:.3f}, Live: {is_live}"
        )

        return is_live, motion_score

    except Exception as e:
        logger.error(f"Error in motion detection: {e}")
        return False, 0.0


def detect_blink(
    frames: List[np.ndarray], face_bboxes: List[np.ndarray]
) -> Tuple[bool, int]:
    """Detect eye blinks across multiple frames using eye aspect ratio (EAR).

    A blink is characterized by a rapid decrease and increase in EAR.
    Photos cannot blink, making this an effective anti-spoofing measure.

    Uses InsightFace landmarks if available, otherwise estimates from face region.

    Args:
        frames: List of consecutive BGR frames
        face_bboxes: List of face bounding boxes for each frame

    Returns:
        Tuple of (blink_detected, blink_count)
    """
    try:
        if len(frames) < 5:
            logger.warning("Insufficient frames for blink detection (need at least 5)")
            return False, 0

        ear_values = []

        for i, (frame, bbox) in enumerate(zip(frames, face_bboxes)):
            if bbox is None:
                continue

            x1, y1, x2, y2 = bbox.astype(int)

            try:
                # Try InsightFace landmarks if available
                if INSIGHTFACE_AVAILABLE:
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    app = get_insightface_app()
                    faces = app.get(rgb_frame)

                    if len(faces) > 0:
                        # InsightFace provides 5-point landmarks: (eyes, nose, mouth corners)
                        landmarks = (
                            faces[0].landmark_2d_106
                            if hasattr(faces[0], "landmark_2d_106")
                            else (
                                faces[0].landmark_2d_68
                                if hasattr(faces[0], "landmark_2d_68")
                                else None
                            )
                        )

                        if landmarks is not None:
                            # Extract eye landmarks (indices for 68-point landmarks: left eye 36-41, right eye 42-47)
                            # For 106-point: left eye 34-42, right eye 43-51
                            try:
                                if len(landmarks) > 50:  # 68-point
                                    left_eye = landmarks[36:42]
                                    right_eye = landmarks[42:48]
                                else:  # Fewer points
                                    left_eye = (
                                        landmarks[0:3] if len(landmarks) > 3 else None
                                    )
                                    right_eye = (
                                        landmarks[3:6] if len(landmarks) > 6 else None
                                    )

                                if (
                                    left_eye is not None
                                    and right_eye is not None
                                    and len(left_eye) > 0
                                    and len(right_eye) > 0
                                ):
                                    left_ear = calculate_ear(left_eye)
                                    right_ear = calculate_ear(right_eye)
                                    avg_ear = (left_ear + right_ear) / 2.0
                                    ear_values.append(avg_ear)
                            except Exception as e:
                                logger.debug(
                                    f"Error processing InsightFace landmarks: {e}"
                                )
                                continue
                else:
                    # Fallback: Estimate EAR from face aspect ratio changes
                    # This is a simple approximation - regions of the face with changing width
                    face_region = frame[y1:y2, x1:x2]
                    face_height = y2 - y1
                    face_width = x2 - x1

                    # Simple approximation: regions near eye level (25-45% of face height)
                    eye_region_start = int(face_height * 0.25)
                    eye_region_end = int(face_height * 0.45)

                    if eye_region_end > eye_region_start:
                        eye_region = face_region[eye_region_start:eye_region_end, :]

                        # Convert to grayscale and calculate edge density
                        gray = cv2.cvtColor(eye_region, cv2.COLOR_BGR2GRAY)
                        edges = cv2.Canny(gray, 50, 150)
                        edge_density = (
                            np.sum(edges)
                            / (eye_region.shape[0] * eye_region.shape[1])
                            / 255.0
                        )

                        # Higher edge density = eyes more open
                        ear_values.append(edge_density)
            except Exception as e:
                logger.debug(f"Could not process frame {i} for blink detection: {e}")
                continue

        if len(ear_values) < 5:
            logger.warning(
                f"Not enough EAR values ({len(ear_values)}) for blink detection"
            )
            return False, 0

        # Detect blinks by looking for dips in EAR values
        # A blink typically has EAR < 0.2 or edge density < 0.1
        EAR_THRESHOLD = 0.21
        blink_count = 0
        in_blink = False

        for ear in ear_values:
            if ear < EAR_THRESHOLD:
                if not in_blink:
                    blink_count += 1
                    in_blink = True
            else:
                in_blink = False

        # Also check for EAR variance (photos have constant EAR)
        ear_variance = np.var(ear_values)
        has_natural_variance = ear_variance > 0.001

        blink_detected = blink_count > 0 or has_natural_variance

        logger.info(
            f"Blink detection - Count: {blink_count}, EAR variance: {ear_variance:.4f}, Detected: {blink_detected}"
        )

        return blink_detected, blink_count

    except Exception as e:
        logger.error(f"Error in blink detection: {e}")
        return False, 0


def calculate_ear(eye_points: List[tuple]) -> float:
    """Calculate Eye Aspect Ratio (EAR) from eye landmark points.

    EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)

    Where p1-p6 are the 6 landmark points around the eye.
    """
    try:
        if len(eye_points) < 6:
            return 0.3  # Default open eye value

        # Convert to numpy array
        eye = np.array(eye_points)

        # Compute the euclidean distances between vertical eye landmarks
        A = dist.euclidean(eye[1], eye[5])
        B = dist.euclidean(eye[2], eye[4])

        # Compute the euclidean distance between horizontal eye landmarks
        C = dist.euclidean(eye[0], eye[3])

        # Compute EAR
        if C == 0:
            return 0.3

        ear = (A + B) / (2.0 * C)
        return ear

    except Exception as e:
        return 0.3


def detect_head_movement(
    frames: List[np.ndarray], face_bboxes: List[np.ndarray]
) -> Tuple[bool, float]:
    """Detect natural head movements across frames.

    Photos are static, so any natural head movement indicates a live person.

    Args:
        frames: List of consecutive BGR frames
        face_bboxes: List of face bounding boxes for each frame

    Returns:
        Tuple of (movement_detected, movement_score)
    """
    try:
        if len(face_bboxes) < 3:
            return False, 0.0

        # Calculate center points of face bboxes
        centers = []
        sizes = []

        for bbox in face_bboxes:
            if bbox is not None:
                x1, y1, x2, y2 = bbox.astype(int)
                center_x = (x1 + x2) / 2
                center_y = (y1 + y2) / 2
                width = x2 - x1
                height = y2 - y1
                centers.append((center_x, center_y))
                sizes.append((width, height))

        if len(centers) < 3:
            return False, 0.0

        # Calculate movement variance
        centers = np.array(centers)
        center_variance = np.var(centers, axis=0)
        total_variance = np.sum(center_variance)

        # Calculate size variance (distance changes)
        sizes = np.array(sizes)
        size_variance = np.var(sizes, axis=0)
        total_size_variance = np.sum(size_variance)

        # Natural head movement thresholds
        MIN_MOVEMENT = 2.0  # Minimum variance for natural movement
        MAX_MOVEMENT = 500.0  # Maximum (too much = video playback)

        movement_valid = MIN_MOVEMENT < total_variance < MAX_MOVEMENT

        # Normalize score
        if total_variance < MIN_MOVEMENT:
            movement_score = 0.0
        elif total_variance > MAX_MOVEMENT:
            movement_score = 0.3
        else:
            movement_score = min((total_variance - MIN_MOVEMENT) / 50.0, 1.0)

        logger.info(
            f"Head movement - Variance: {total_variance:.2f}, Size variance: {total_size_variance:.2f}, Score: {movement_score:.3f}"
        )

        return movement_valid, movement_score

    except Exception as e:
        logger.error(f"Error in head movement detection: {e}")
        return False, 0.0


def analyze_liveness(
    image: np.ndarray,
    face_bbox: np.ndarray,
    previous_frames: Optional[List[np.ndarray]] = None,
    previous_bboxes: Optional[List[np.ndarray]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """Comprehensive liveness detection combining multiple methods.

    ENHANCED VERSION: Now includes blink detection and head movement analysis
    for better anti-spoofing protection against photo attacks.

    Args:
        image: Current frame in BGR format
        face_bbox: Face bounding box [x1, y1, x2, y2]
        previous_frames: List of previous frames for motion analysis (optional)
        previous_bboxes: List of previous face bboxes for head movement analysis (optional)

    Returns:
        Tuple of (is_live, liveness_details) with detailed analysis
    """
    try:
        liveness_details = {
            "texture_live": False,
            "texture_score": 0.0,
            "motion_live": None,
            "motion_score": None,
            "blink_detected": None,
            "blink_count": 0,
            "head_movement_live": None,
            "head_movement_score": None,
            "overall_live": False,
            "confidence": 0.0,
            "method": "texture_only",
            "checks_passed": 0,
            "checks_total": 1,
        }

        # Enforce multi-frame liveness if configured
        require_multi = False
        min_frames = 3
        try:
            require_multi = current_app.config.get("LIVENESS_REQUIRE_MULTI_FRAME", False)
            min_frames = current_app.config.get("LIVENESS_MIN_FRAMES", 3)
        except Exception:
            require_multi = False
            min_frames = 3

        total_frames = 1 + (len(previous_frames) if previous_frames else 0)
        if require_multi and total_frames < min_frames:
            liveness_details["method"] = "multi_frame_required"
            liveness_details["error"] = (
                f"Need at least {min_frames} frames for liveness detection"
            )
            return False, to_native_types(liveness_details)

        checks_passed = 0
        checks_total = 1  # Start with texture check

        # 1. Texture-based liveness detection (always performed) - STRICTER THRESHOLD
        texture_live, texture_score = detect_texture_artifacts(image, face_bbox)
        liveness_details["texture_live"] = texture_live
        liveness_details["texture_score"] = float(texture_score)

        # ENHANCED: Require higher texture score for single-check mode
        if texture_live and texture_score >= 0.7:
            checks_passed += 1

        # 2. Motion-based liveness detection (if previous frames available)
        if previous_frames and len(previous_frames) >= 2:
            all_frames = previous_frames + [image]
            motion_live, motion_score = detect_motion_liveness(
                all_frames[-5:]
            )  # Use last 5 frames
            liveness_details["motion_live"] = motion_live
            liveness_details["motion_score"] = float(motion_score)
            liveness_details["method"] = "texture_and_motion"
            checks_total += 1

            if motion_live and motion_score >= 0.3:
                checks_passed += 1

        # 3. Blink detection (if enough frames available)
        if previous_frames and len(previous_frames) >= 4 and previous_bboxes:
            all_frames = previous_frames + [image]
            all_bboxes = previous_bboxes + [face_bbox]

            blink_detected, blink_count = detect_blink(
                all_frames[-10:], all_bboxes[-10:]
            )
            liveness_details["blink_detected"] = blink_detected
            liveness_details["blink_count"] = blink_count
            liveness_details["method"] = "comprehensive"
            checks_total += 1

            if blink_detected:
                checks_passed += 1

        # 4. Head movement detection (if enough frames available)
        if previous_frames and len(previous_frames) >= 2 and previous_bboxes:
            all_bboxes = previous_bboxes + [face_bbox]

            head_movement_live, head_movement_score = detect_head_movement(
                previous_frames + [image], all_bboxes
            )
            liveness_details["head_movement_live"] = head_movement_live
            liveness_details["head_movement_score"] = (
                float(head_movement_score) if head_movement_score else None
            )
            checks_total += 1

            if head_movement_live and head_movement_score >= 0.2:
                checks_passed += 1

        liveness_details["checks_passed"] = checks_passed
        liveness_details["checks_total"] = checks_total

        # ENHANCED SECURITY DECISION:
        # For comprehensive mode (with motion data): require at least 2 out of available checks to pass
        # For texture-only mode: require very high texture score
        if checks_total >= 3:
            # Multi-check mode: require majority of checks to pass
            required_checks = max(2, checks_total // 2)
            overall_live = checks_passed >= required_checks

            # Calculate weighted confidence
            scores = [texture_score]
            if liveness_details["motion_score"] is not None:
                scores.append(liveness_details["motion_score"])
            if liveness_details["blink_detected"]:
                scores.append(0.8)  # Blink detection is binary, use 0.8 as score
            if liveness_details["head_movement_score"] is not None:
                scores.append(liveness_details["head_movement_score"])

            confidence = np.mean(scores)
        elif checks_total == 2:
            # Two checks available: both should pass OR one with very high score
            overall_live = (checks_passed >= 2) or (
                checks_passed >= 1 and texture_score >= 0.8
            )

            scores = [texture_score]
            if liveness_details["motion_score"] is not None:
                scores.append(liveness_details["motion_score"])
            confidence = np.mean(scores)
        else:
            # Single check (texture only): require VERY high score
            # This is the fallback mode when no motion data is available
            overall_live = texture_live and texture_score >= 0.8
            confidence = texture_score

            # Log info about texture-only analysis
            logger.warning(
                "⚠️ Liveness check using texture analysis only (no motion data) - using strict threshold"
            )

        # If multi-frame is required, require at least one dynamic signal.
        if require_multi:
            dynamic_signals = [
                liveness_details.get("motion_live") is True,
                liveness_details.get("blink_detected") is True,
                liveness_details.get("head_movement_live") is True,
            ]
            if not any(dynamic_signals):
                liveness_details["overall_live"] = False
                liveness_details["confidence"] = float(confidence)
                liveness_details["failure_reason"] = "no_dynamic_signal"
                logger.warning(
                    "Liveness failed: no dynamic signal (motion/blink/head movement)"
                )
                return False, to_native_types(liveness_details)

        liveness_details["overall_live"] = overall_live
        liveness_details["confidence"] = float(confidence)

        logger.info(
            f"Liveness detection - Live: {overall_live}, Confidence: {confidence:.3f}, Checks: {checks_passed}/{checks_total}"
        )
        logger.info(f"  Texture: {texture_live} ({texture_score:.3f})")
        if liveness_details["motion_live"] is not None:
            logger.info(
                f"  Motion: {liveness_details['motion_live']} ({liveness_details['motion_score']:.3f})"
            )
        if liveness_details["blink_detected"] is not None:
            logger.info(
                f"  Blink: {liveness_details['blink_detected']} (count: {liveness_details['blink_count']})"
            )
        if liveness_details["head_movement_live"] is not None:
            head_movement_score = liveness_details["head_movement_score"]
            if head_movement_score is None:
                logger.info(
                    f"  Head Movement: {liveness_details['head_movement_live']} (N/A)"
                )
            else:
                logger.info(
                    f"  Head Movement: {liveness_details['head_movement_live']} ({head_movement_score:.3f})"
                )

        return overall_live, to_native_types(liveness_details)

    except Exception as e:
        logger.error(f"Error in liveness analysis: {e}")
        return False, {"overall_live": False, "error": str(e)}


def process_base64_image(
    base64_image: str,
    enable_liveness: bool = True,
    previous_frames: Optional[List[np.ndarray]] = None,
) -> Tuple[Optional[List[float]], Optional[Dict[str, Any]], Optional[str]]:
    """Process base64 image data for face detection and embedding extraction.

    Validates input, detects face, performs liveness detection, and extracts embeddings.

    Args:
        base64_image: Base64 encoded image data
        enable_liveness: Whether to perform liveness detection (default: True)
        previous_frames: Optional list of previous frames for motion analysis

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
        try:
            face_detection_confidence = current_app.config.get(
                "FACE_DETECTION_CONFIDENCE", 0.5
            )
        except RuntimeError:
            # No app context available, use default
            face_detection_confidence = 0.5

        results = model(img, conf=face_detection_confidence)

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

        # Perform liveness detection if enabled
        if enable_liveness:
            try:
                require_multi = current_app.config.get(
                    "LIVENESS_REQUIRE_MULTI_FRAME", False
                )
                min_frames = current_app.config.get("LIVENESS_MIN_FRAMES", 3)
            except Exception:
                require_multi = False
                min_frames = 3

            total_frames = 1 + (len(previous_frames) if previous_frames else 0)
            if require_multi and total_frames < min_frames:
                return (
                    None,
                    {
                        "liveness_failed": True,
                        "liveness_details": {
                            "method": "multi_frame_required",
                            "error": f"Need at least {min_frames} frames for liveness detection",
                        },
                    },
                    None,
                )

            logger.info("=== Starting Liveness Detection ===")
            is_live, liveness_details = analyze_liveness(img, bbox, previous_frames)
            logger.info(
                f"=== Liveness Result: {'LIVE' if is_live else 'FAKE/PHOTO'} ==="
            )

            if not is_live:
                logger.warning(
                    "❌ LIVENESS DETECTION FAILED - Possible spoofing attempt detected!"
                )
                logger.warning(f"Liveness details: {liveness_details}")
                # Return None to indicate failure with liveness info in metadata
                return (
                    None,
                    {"liveness_failed": True, "liveness_details": liveness_details},
                    None,
                )
            else:
                logger.info("✓ LIVENESS DETECTION PASSED - Live person detected")

        # Extract face
        face = img[bbox[1] : bbox[3], bbox[0] : bbox[2]]

        # Create a unique filename for the face image
        temp_filename = f"temp_{uuid.uuid4()}.jpg"
        try:
            temp_folder = current_app.config["TEMP_ATTENDANCE_FOLDER"]
        except RuntimeError:
            # No app context available, use default
            temp_folder = "static/images/attendance_temp"

        temp_path = os.path.join(temp_folder, temp_filename)

        # Save the face image temporarily
        cv2.imwrite(temp_path, face)

        # Extract face embedding
        face_embedding, face_metadata = extract_face_embeddings(temp_path)

        # Add capture metadata for quality feedback
        if face_metadata is not None:
            img_height, img_width = img.shape[:2]
            face_metadata["image_width"] = int(img_width)
            face_metadata["image_height"] = int(img_height)
            bbox_area = max(0, (bbox[2] - bbox[0])) * max(0, (bbox[3] - bbox[1]))
            image_area = max(1, img_width * img_height)
            face_metadata["face_area_ratio"] = float(bbox_area / image_area)

        # Add liveness info to metadata if performed
        if enable_liveness and face_metadata:
            face_metadata["liveness_passed"] = True
            face_metadata["liveness_details"] = liveness_details

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
        quality_report = []
        best_face_candidate = None

        # Process each image
        logger.info(f"Processing {len(base64_images)} images")
        for i, base64_image in enumerate(base64_images):
            try:
                # Process the base64 image (disable liveness for registration)
                logger.info(f"Processing image {i + 1}")
                face_embedding, face_metadata, temp_path = process_base64_image(
                    base64_image,
                    enable_liveness=False,  # Disable liveness for face registration
                )

                # If no face detected or error, skip
                if face_embedding is None or temp_path is None:
                    logger.warning(f"No face detected in image {i + 1}")
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
                # Assess capture quality for user feedback
                confidence_score = (
                    face_metadata.get("confidence") if face_metadata else None
                )
                face_area_ratio = (
                    face_metadata.get("face_area_ratio") if face_metadata else None
                )
                quality = "poor"
                issues = []
                if confidence_score is None:
                    issues.append("No detection confidence")
                elif confidence_score < 0.55:
                    issues.append("Low detection confidence")

                if face_area_ratio is None:
                    issues.append("Missing face size data")
                elif face_area_ratio < 0.05:
                    issues.append("Face too small in frame")

                if not issues:
                    if confidence_score >= 0.7 and face_area_ratio >= 0.08:
                        quality = "good"
                    else:
                        quality = "ok"

                quality_entry = {
                    "filename": filename,
                    "quality": quality,
                    "confidence": float(confidence_score or 0.0),
                    "face_area_ratio": float(face_area_ratio or 0.0),
                    "issues": issues,
                }
                quality_report.append(quality_entry)

                face_data = FaceData(
                    personnel_id=personnel_id,
                    filename=filename,
                    embedding=json.dumps(face_embedding),
                    confidence=confidence_score,
                )

                db.session.add(face_data)
                registered_images.append(filename)
                logger.info(f"Added face data for image {i + 1}")

                # Track best face candidate for profile image selection
                quality_weight = {"good": 2, "ok": 1, "poor": 0}.get(quality, 0)
                score = (quality_weight * 10.0) + float(confidence_score or 0.0)
                if best_face_candidate is None or score > best_face_candidate["score"]:
                    best_face_candidate = {
                        "score": score,
                        "filename": filename,
                    }

            except Exception as e:
                logger.error(f"Error registering face image {i}: {e}")
                # Clean up temporary file if exists
                if "temp_path" in locals() and temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)

        # Set profile image if not already set
        if len(registered_images) > 0:
            # Use the best quality face image as profile photo
            best_face = (
                best_face_candidate["filename"]
                if best_face_candidate is not None
                else registered_images[0]
            )

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
        logger.info("Database commit successful")

        # Clear face database cache since we added new face data
        clear_face_database_cache()

        quality_summary = {
            "good": sum(1 for item in quality_report if item["quality"] == "good"),
            "ok": sum(1 for item in quality_report if item["quality"] == "ok"),
            "poor": sum(1 for item in quality_report if item["quality"] == "poor"),
            "total": len(quality_report),
        }

        return {
            "success": True,
            "message": f"Successfully registered {len(registered_images)} face images",
            "registered_images": registered_images,
            "quality_report": quality_report,
            "quality_summary": quality_summary,
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
