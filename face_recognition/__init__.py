"""
Face recognition service module initialization.
"""

from .face_service import (
    get_yolo_model,
    extract_face_embeddings,
    compare_embeddings,
    load_face_database,
    recognize_face,
    process_attendance,
    save_attendance_image,
    process_base64_image,
    register_face,
)
