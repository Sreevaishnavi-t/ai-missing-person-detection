import os
import sys
import time
import shutil
import threading
from unittest.mock import patch
import cv2

# Add the project root to Python's import path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from backend.main import app, METADATA_PATH
from backend.config import DB_PATH, SCREENSHOT_DIR, WATCHLIST_DIR
from backend.logger import SessionLocal, Match

class MockVideoCapture:
    """Mock VideoCapture that feeds person_b.jpg for simulated detection."""
    def __init__(self, source):
        self.source = source
        self.image_path = os.path.join(WATCHLIST_DIR, "person_b.jpg")
        self.frame = cv2.imread(self.image_path)
        self.read_count = 0
        self.max_reads = 2

    def isOpened(self) -> bool:
        return True

    def read(self) -> tuple:
        if self.read_count < self.max_reads:
            self.read_count += 1
            return True, self.frame.copy()
        return False, None

    def get(self, prop_id) -> float:
        return 30.0

    def release(self) -> None:
        pass


def clean_state():
    """Reset database, metadata file, and screenshots for testing."""
    print("[Test Setup] Cleaning database and screenshots...")
    # Delete metadata file
    if os.path.exists(METADATA_PATH):
        try:
            os.remove(METADATA_PATH)
        except Exception as e:
            print(f"Warning: could not delete {METADATA_PATH}: {e}")

    # Delete FAISS DB
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except Exception as e:
            print(f"Warning: could not delete {DB_PATH}: {e}")
    names_json = DB_PATH.with_suffix(".json")
    if os.path.exists(names_json):
        try:
            os.remove(names_json)
        except Exception as e:
            print(f"Warning: could not delete {names_json}: {e}")

    # Delete records from SQLite database matches table
    session = SessionLocal()
    try:
        session.query(Match).delete()
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Warning: database clean failed: {e}")
    finally:
        session.close()

    # Clear watchlist folder files except gitkeep and original person_b / t1 / Tom_Hanks
    if os.path.exists(WATCHLIST_DIR):
        for filename in os.listdir(WATCHLIST_DIR):
            if filename not in (".gitkeep", "Tom_Hanks.png", "person_a.jpg", "person_b.jpg", "t1.jpg"):
                file_path = os.path.join(WATCHLIST_DIR, filename)
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Warning: could not delete file {file_path}: {e}")

    # Delete screenshots
    if os.path.exists(SCREENSHOT_DIR):
        for filename in os.listdir(SCREENSHOT_DIR):
            if filename != ".gitkeep":
                file_path = os.path.join(SCREENSHOT_DIR, filename)
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Warning: could not delete file {file_path}: {e}")


def main():
    print("=== Starting Phase 4 API Integration Test ===")
    
    clean_state()
    client = TestClient(app)

    # 1. Test GET /watchlist (Should be empty initially)
    print("\n[Test 1] Querying /watchlist initially...")
    resp = client.get("/watchlist")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert resp.json() == [], f"Expected empty watchlist, got {resp.json()}"
    print("SUCCESS: Watchlist is empty initially.")

    # 2. Test POST /enroll with person_b.jpg
    print("\n[Test 2] Enrolling person_b.jpg as 'Test Person B'...")
    image_path = os.path.join(WATCHLIST_DIR, "person_b.jpg")
    with open(image_path, "rb") as f:
        file_data = f.read()

    resp = client.post(
        "/enroll",
        data={"name": "Test Person B"},
        files={"file": ("person_b.jpg", file_data, "image/jpeg")}
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    enroll_data = resp.json()
    assert enroll_data["name"] == "Test Person B"
    assert enroll_data["id"] == 0
    assert "enrolled_at" in enroll_data
    print(f"SUCCESS: Enrollment successful: {enroll_data}")

    # 3. Test GET /watchlist (Should contain Test Person B now)
    print("\n[Test 3] Verifying /watchlist contents...")
    resp = client.get("/watchlist")
    assert resp.status_code == 200
    watchlist = resp.json()
    assert len(watchlist) == 1
    assert watchlist[0]["name"] == "Test Person B"
    assert watchlist[0]["id"] == 0
    print(f"SUCCESS: Watchlist verified: {watchlist}")

    # 4. Test POST /enroll error: Multiple faces
    print("\n[Test 4] Verifying /enroll error handling with multiple faces...")
    friends_path = os.path.join(WATCHLIST_DIR, "t1.jpg")
    if os.path.exists(friends_path):
        with open(friends_path, "rb") as f:
            friends_data = f.read()
    else:
        # Dynamically create a 2-face image by stitching person_b side-by-side
        import numpy as np
        b_img = cv2.imread(image_path)
        multi_img = np.hstack([b_img, b_img])
        _, buffer = cv2.imencode(".jpg", multi_img)
        friends_data = buffer.tobytes()

    resp = client.post(
        "/enroll",
        data={"name": "Multiple Faces Test"},
        files={"file": ("multi_face.jpg", friends_data, "image/jpeg")}
    )
    assert resp.status_code == 400
    assert "Multiple faces detected" in resp.json()["detail"]
    print(f"SUCCESS: Server correctly rejected multiple faces: {resp.json()}")

    # 5. Test POST /enroll error: Invalid file format
    print("\n[Test 5] Verifying /enroll error handling with invalid image file...")
    resp = client.post(
        "/enroll",
        data={"name": "Text File"},
        files={"file": ("test.txt", b"plain text data", "text/plain")}
    )
    assert resp.status_code == 400
    print(f"SUCCESS: Server correctly rejected invalid file: {resp.json()}")

    # 6. Test POST /start and POST /stop with mock VideoCapture
    # We patch VideoCapture inside detector.py when it is imported and called
    print("\n[Test 6] Starting background detection stream via /start...")
    
    with patch('cv2.VideoCapture', side_effect=MockVideoCapture):
        resp = client.post("/start", json={"source": "mock_source_0"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert resp.json() == {"status": "started"}
        print("SUCCESS: Detection thread launched.")

        # Let the thread run for a bit to detect faces and update latest_frame
        print("Waiting for detection thread to run and update state...")
        time.sleep(3.0)

        # 7. Test GET /stream (verify it yields boundary chunks)
        print("\n[Test 7] Verifying live stream response /stream...")
        # Since it is a streaming endpoint, we can read the first few bytes/boundary blocks
        with client.stream("GET", "/stream") as stream_resp:
            assert stream_resp.status_code == 200
            content_type = stream_resp.headers.get("content-type", "")
            assert "multipart/x-mixed-replace" in content_type, f"Expected MJPEG type, got {content_type}"
            
            # Read first chunk of bytes to verify boundary structure
            chunk = next(stream_resp.iter_bytes(1024))
            assert b"--frame" in chunk
            assert b"Content-Type: image/jpeg" in chunk
            print(f"SUCCESS: MJPEG boundary headers verified in stream chunk.")

        # 8. Stop detection
        print("\n[Test 8] Stopping detection via /stop...")
        resp = client.post("/stop")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"
        print("SUCCESS: Detection thread stopped successfully.")

    # 9. Test GET /results
    print("\n[Test 9] Fetching logged results from /results...")
    resp = client.get("/results")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1, f"Expected at least 1 logged match, got {len(results)}"
    
    match = results[0]
    assert match["person_name"] == "Test Person B"
    assert "screenshot_url" in match
    assert match["screenshot_url"].startswith("/screenshots/")
    print(f"SUCCESS: Logged matches retrieved successfully: {match}")

    # 10. Test GET /screenshots/{filename}
    print("\n[Test 10] Serving static screenshots via /screenshots/{filename}...")
    screenshot_url = match["screenshot_url"]
    screenshot_filename = os.path.basename(match["screenshot_path"])
    
    resp = client.get(screenshot_url)
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "image/jpeg"
    print(f"SUCCESS: Static screenshot served correctly.")

    print("\n=== Phase 4 API Integration Test PASSED Successfully! ===")


if __name__ == "__main__":
    main()
