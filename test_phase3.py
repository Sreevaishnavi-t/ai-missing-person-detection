import os
import sys
import time
import shutil
import threading
from unittest.mock import patch
import cv2

# Add the project root to Python's import path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.config import DB_PATH, SCREENSHOT_DIR, WATCHLIST_DIR
from backend.embedder import detect_faces, get_embedding
from backend.faiss_store import FAISSStore
from backend.logger import SessionLocal, Match, get_recent_matches
from backend.detector import run_detection

class MockVideoCapture:
    """
    Mock class for cv2.VideoCapture to simulate video frame capturing
    without requiring a physical webcam.
    """
    def __init__(self, source):
        self.source = source
        # Load a real face image that we will return as video frames
        # person_b.jpg was generated in Phase 2
        self.image_path = os.path.join(WATCHLIST_DIR, "person_b.jpg")
        if not os.path.exists(self.image_path):
            raise FileNotFoundError(f"Missing required person_b.jpg reference face at {self.image_path}")
        
        self.frame = cv2.imread(self.image_path)
        if self.frame is None:
            raise IOError(f"Could not load image file {self.image_path}")

        # Counter to limit the number of frames read before ending
        self.read_count = 0
        # We will allow 2 reads to test both detection and the 10-second cooldown window
        self.max_reads = 2

    def isOpened(self) -> bool:
        return True

    def read(self) -> tuple:
        if self.read_count < self.max_reads:
            self.read_count += 1
            # Return a copy of the frame to avoid modifications issues
            return True, self.frame.copy()
        else:
            # End of stream
            return False, None

    def release(self) -> None:
        pass


def clean_state():
    """
    Clears test records in the database and cleans up any existing
    test screenshots in data/screenshots.
    """
    print("[Test Setup] Cleaning database and screenshots...")
    # 1. Delete all records from SQLite database matches table
    session = SessionLocal()
    try:
        session.query(Match).delete()
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Warning: database clean failed: {e}")
    finally:
        session.close()

    # 2. Delete test screenshots
    if os.path.exists(SCREENSHOT_DIR):
        for filename in os.listdir(SCREENSHOT_DIR):
            if filename.startswith("Test Person B"):
                file_path = os.path.join(SCREENSHOT_DIR, filename)
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Warning: could not delete file {file_path}: {e}")


def enroll_test_face():
    """
    Loads person_b.jpg, extracts its embedding, and enrolls it into
    the FAISS index as 'Test Person B'.
    """
    print("[Test Setup] Enrolling 'Test Person B' in FAISS index...")
    image_path = os.path.join(WATCHLIST_DIR, "person_b.jpg")
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not load {image_path}")
        sys.exit(1)

    faces = detect_faces(img)
    if not faces:
        print("Error: No faces detected in person_b.jpg. Cannot enroll test face.")
        sys.exit(1)

    embedding = get_embedding(faces[0])
    
    store = FAISSStore()
    store.add("Test Person B", embedding)
    store.save_index(DB_PATH)
    print(f"Saved FAISS index with {store.index.ntotal} registered item at {DB_PATH}")


def main():
    print("=== Starting Phase 3 Integration Test ===")
    
    # 1. Clean the database and directory state
    clean_state()

    # 2. Ensure test person is enrolled in the FAISS index
    enroll_test_face()

    # 3. Patch cv2.VideoCapture to use our MockVideoCapture
    print("\n[Test Execution] Running detection loop with mocked video source...")
    stop_event = threading.Event()
    
    # We patch cv2.VideoCapture to instantiate MockVideoCapture instead
    with patch('cv2.VideoCapture', side_effect=MockVideoCapture):
        # We pass "mock_source_0" as the source string
        run_detection(source="mock_source_0", stop_event=stop_event)

    # 4. Verify test results in database and filesystem
    print("\n[Test Verification] Analyzing results...")
    
    # Retrieve all matches logged in database
    recent_matches = get_recent_matches(limit=10)
    print(f"Total matches logged in database: {len(recent_matches)}")
    for m in recent_matches:
        print(f"  Match ID: {m['id']} | Name: {m['person_name']} | Confidence: {m['confidence']:.4f} | Source: {m['video_source']} | Saved Screenshot: {m['screenshot_path']}")

    # Check database constraints
    # Since MockVideoCapture read the frame twice, we expect exactly ONE log entry.
    # The second frame read was processed immediately, so the 10-second cooldown
    # window should have suppressed it.
    if len(recent_matches) == 0:
        print("FAILURE: No matches were logged in the database.")
        sys.exit(1)
    elif len(recent_matches) > 1:
        print(f"FAILURE: Cooldown failed. Expected 1 log, but got {len(recent_matches)}.")
        sys.exit(1)
    
    match = recent_matches[0]
    
    # Verify field values
    assert match["person_name"] == "Test Person B", f"Expected 'Test Person B', got {match['person_name']}"
    assert match["video_source"] == "mock_source_0", f"Expected 'mock_source_0', got {match['video_source']}"
    assert match["confidence"] >= 0.45, f"Expected confidence >= 0.45, got {match['confidence']}"
    
    # Verify screenshot exists on disk
    screenshot_path = match["screenshot_path"]
    if not os.path.exists(screenshot_path):
        print(f"FAILURE: Screenshot file does not exist at {screenshot_path}")
        sys.exit(1)
    
    print(f"SUCCESS: Screenshot verified on disk: {screenshot_path}")
    print("SUCCESS: 10-second duplicate match cooldown successfully prevented double logging!")
    print("\n=== Phase 3 Integration Test PASSED Successfully! ===")


if __name__ == "__main__":
    main()
