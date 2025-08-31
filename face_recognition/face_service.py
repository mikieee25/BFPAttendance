import os
import cv2
import torch
import numpy as np
import json
import logging
import base64
from ultralytics import YOLO
from flask import current_app
from datetime import datetime, timedelta
import uuid
from sqlalchemy import or_

from models import db, Personnel, FaceData, Attendance, AttendanceStatus, User

# Set up logger
logger = logging.getLogger(__name__)

# Global model instance
yolo_model = None


def get_yolo_model():
    global yolo_model
    if yolo_model is None:
        model_path = current_app.config["YOLO_MODEL_PATH"]
        try:
            # Force CPU usage if configured
            device = current_app.config.get("TORCH_DEVICE", "cpu")

            # Print debug info for device configuration
            logger.info(f"PyTorch version: {torch.__version__}")
            logger.info(f"CUDA available: {torch.cuda.is_available()}")
            logger.info(f"Current PyTorch device: {device}")

            # Ensure PyTorch uses the configured device
            if device == "cpu":
                torch.set_default_device("cpu")

            # Initialize model with specific device setting
            yolo_model = YOLO(model_path)
            yolo_model.to(device)
            logger.info(f"YOLO model loaded on {device}")
        except Exception as e:
            logger.error(f"Error loading YOLO model: {e}")
            # Fallback to default initialization with CPU
            yolo_model = YOLO(model_path)
            yolo_model.cpu()
    return yolo_model


def extract_face_embeddings(image_path):
    try:
        model = get_yolo_model()

        # Read the image
        img = cv2.imread(image_path)
        if img is None:
            logger.warning(f"Could not read image: {image_path}")
            return None, None

        # Run inference
        results = model(
            img, conf=current_app.config.get("FACE_DETECTION_CONFIDENCE", 0.5)
        )
        if len(results) == 0 or len(results[0].boxes) == 0:
            logger.debug(f"No faces detected in image: {image_path}")
            return None, None

        # Get the face with highest confidence
        boxes = results[0].boxes
        confidences = boxes.conf.cpu().numpy()
        max_idx = np.argmax(confidences)

        # Get bounding box
        bbox = boxes.xyxy[max_idx].cpu().numpy().astype(int)
        confidence = float(confidences[max_idx])

        # Extract face region
        face = img[bbox[1] : bbox[3], bbox[0] : bbox[2]]

        # Simple face embedding (resize to standard size and flatten)
        face_resized = cv2.resize(face, (128, 128))

        # Convert to grayscale to reduce dimensionality
        face_gray = cv2.cvtColor(face_resized, cv2.COLOR_BGR2GRAY)

        # Create embedding by flattening and normalizing
        embedding = face_gray.flatten().astype(float)

        # Normalize embedding
        if np.linalg.norm(embedding) > 0:
            embedding = embedding / np.linalg.norm(embedding)

        # Return as Python list and metadata
        return embedding.tolist(), {
            "bbox": bbox.tolist(),
            "confidence": float(confidence),
        }

    except Exception as e:
        logger.error(f"Error extracting face embeddings: {e}")
        return None, None


def compare_embeddings(emb1, emb2, threshold=0.75):
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


def load_face_database(station_id=None):
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

        return face_database

    except Exception as e:
        logger.error(f"Error loading face database: {e}")
        return {}


def recognize_face(face_embedding, face_database, threshold=None):
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


def process_attendance(personnel_id, confidence, base64_image=None):
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

        # Check for any recent attendance requests (time-in or time-out) across all records
        # This prevents rapid-fire attendance records even if no record exists for today
        recent_attendance = Attendance.query.filter(
            Attendance.personnel_id == personnel_id,
            or_(
                # Check for recent time_in
                Attendance.time_in >= current_time - cooldown_period,
                # Check for recent time_out
                Attendance.time_out >= current_time - cooldown_period,
            ),
        ).first()

        if recent_attendance:
            # Someone is trying to record attendance too quickly
            last_action_time = (
                recent_attendance.time_out
                if recent_attendance.time_out
                and recent_attendance.time_out >= current_time - cooldown_period
                else recent_attendance.time_in
            )

            time_since_last_action = current_time - last_action_time
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
                    recent_attendance.time_in.strftime("%I:%M:%S %p")
                    if recent_attendance.time_in
                    else None
                ),
                "time_out": (
                    recent_attendance.time_out.strftime("%I:%M:%S %p")
                    if recent_attendance.time_out
                    else None
                ),
            }

        # Check for existing attendance record for today
        attendance = Attendance.query.filter_by(
            personnel_id=personnel_id, date=today
        ).first()

        # If attendance record exists for today
        if attendance:
            # Check if in cooldown period from last action
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

            # If time_out is not recorded yet, check if this is a time-in attempt
            if attendance.time_out is None:
                # If we have time_in and system detects person is trying to sign in again,
                # show a message instead of recording time_out
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
                # Already completed attendance for the day
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


def save_attendance_image(personnel_id, base64_image, prefix):
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


def process_base64_image(base64_image):
    try:
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


def register_face(personnel_id, base64_images):
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

        return {
            "success": True,
            "message": f"Successfully registered {len(registered_images)} face images",
            "registered_images": registered_images,
        }

    except Exception as e:
        logger.error(f"Error registering faces: {e}")
        db.session.rollback()
        return {"success": False, "error": f"Error registering faces: {str(e)}"}


def cleanup_old_attendance_images():
    """
    Delete attendance images older than the configured retention period.
    This function should be called periodically (e.g., daily) to clean up old images.
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
