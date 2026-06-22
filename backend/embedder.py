import numpy as np
import cv2

try:
    from insightface.app import FaceAnalysis
except ImportError:
    FaceAnalysis = None

if FaceAnalysis is not None:
    # buffalo_l is InsightFace's large, high-accuracy model pack with face detection and ArcFace recognition models.
    # We use it because Phase 1 needs reliable face boxes now and 512-d embeddings later for matching.
    face_app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])

    # prepare() loads the models; ctx_id=-1 selects CPU, and det_size controls detection input size.
    face_app.prepare(ctx_id=-1, det_size=(640, 640))
else:
    face_app = None
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)


class DetectedFace:
    def __init__(self, bbox: np.ndarray):
        self.bbox = bbox
        self.normed_embedding = None

def detect_faces(image_bgr: np.ndarray) -> list:
    """
    Detect faces in one OpenCV BGR image and return InsightFace Face objects.
    """
    if face_app is None:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        detections = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        return [
            DetectedFace(np.array([x, y, x + w, y + h], dtype=np.float32))
            for x, y, w, h in detections
        ]

    # face_app.get() detects faces and also attaches landmarks plus ArcFace embeddings.
    return face_app.get(image_bgr)


def get_embedding(face) -> np.ndarray:
    """
    Return the normalized 512-d ArcFace embedding from one InsightFace Face object.
    """
    if face.normed_embedding is None:
        raise RuntimeError("Embeddings require InsightFace. OpenCV fallback only supports face boxes.")

    # normed_embedding is ready for cosine-similarity search in FAISS.
    return np.asarray(face.normed_embedding, dtype=np.float32)
