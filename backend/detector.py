import os
import time
import datetime
import cv2
import numpy as np

# Import configurations, face embedding pipelines, FAISS, and SQL database helpers
from backend.config import CONFIDENCE_THRESHOLD, SCREENSHOT_DIR, DB_PATH
from backend.embedder import detect_faces, get_embedding
from backend.faiss_store import FAISSStore
from backend.logger import log_match

# ==============================================================================
# CONCEPT EXPLANATION: Thread Safety and Synchronization
# ==============================================================================
# When running a video detection pipeline inside a production web application
# (such as a FastAPI backend with a React frontend), the frame processing loop
# should run in a separate background thread so it doesn't block the main web
# server thread.
#
# If multiple threads read or write to shared resources, we must implement safety:
# 1. Thread Stop Signaling:
#    We pass a `threading.Event` object (named `stop_event`) to the loop. The
#    background detection thread polls `stop_event.is_set()` on every frame.
#    When the main thread or UI signals to stop (e.g., clicking a 'Stop Stream'
#    button on the web interface), it calls `stop_event.set()`, allowing the
#    background thread to exit the loop and release resources cleanly.
# 2. Race Conditions & Mutex Locks:
#    If the main thread modifies the watchlist (adds/removes people in the FAISS
#    index) while the detector thread is querying the index using `store.search()`,
#    it can trigger race conditions and memory corruption. To prevent this, we can
#    use a `threading.Lock()` (mutual exclusion lock / mutex):
#      lock = threading.Lock()
#      # In detection thread:
#      with lock:
#          results = store.search(emb)
#      # In watchlist management thread:
#      with lock:
#          store.add(name, emb)
# 3. Thread-Safe Communication (Queues):
#    Instead of sharing database variables or lists directly between threads, the
#    background thread can publish detected match events or images to a thread-safe
#    `queue.Queue()`. The main thread reads from this queue to push real-time alerts
#    to users via WebSockets.
# ==============================================================================

def run_detection(source, stop_event=None) -> None:
    """
    Main frame loop that reads video from a source, detects faces, performs FAISS matching,
    and logs positive matches with screenshot captures.
    
    Args:
        source: OpenCV video source (e.g., integer 0 for webcam, or string path to a video file).
        stop_event (threading.Event, optional): A thread event to cleanly stop the loop.
    """
    # 1. Initialize and load the FAISS store index
    store = FAISSStore()
    if os.path.exists(DB_PATH):
        print(f"[Detector] Loading FAISS index watchlist from {DB_PATH}...")
        try:
            store.load_index(DB_PATH)
            print(f"[Detector] Watchlist loaded successfully. Registered people: {len(store.names)}")
        except Exception as e:
            print(f"[Detector] Error loading FAISS index: {e}. Starting with an empty index.")
    else:
        print(f"[Detector] Warning: FAISS index file not found at: {DB_PATH}. Detection will run, but no matches can occur.")

    # 2. Connect to the video stream source
    print(f"[Detector] Opening video source: {source}...")
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"[Detector] Error: Could not open video source {source}")
        return

    # 3. Initialize cooldown trackers and directories
    # - last_logged: maps name (str) -> timestamp (float) of the last logged match
    # - COOLDOWN_SECONDS: length of time (10s) we wait before logging the same person again
    last_logged = {}
    COOLDOWN_SECONDS = 10.0

    print("[Detector] Starting video processing loop. Press 'Q' to quit if window is active.")

    try:
        while True:
            # Check if thread stop signal has been set
            if stop_event is not None and stop_event.is_set():
                print("[Detector] Stop signal received. Exiting detection loop.")
                break

            # Read the next frame from the stream
            ret, frame = cap.read()
            if not ret:
                print("[Detector] End of video stream or failed to grab frame. Exiting loop.")
                break

            # Perform face detection on the frame
            faces = detect_faces(frame)

            for face in faces:
                try:
                    # Extract the 512-d normalized face representation
                    embedding = get_embedding(face)
                except RuntimeError:
                    # Skip face if we are in fallback Haar Cascades mode (no embeddings supported)
                    continue

                # Query the FAISS store for the closest match in our watchlist
                matches = store.search(embedding, top_k=1)
                if not matches:
                    continue

                person_name, confidence = matches[0]

                # Check if the match is strong enough to trigger an alert (above threshold)
                if confidence >= CONFIDENCE_THRESHOLD:
                    now = time.time()
                    
                    # Verify if the duplicate cooldown window has elapsed for this person
                    if person_name not in last_logged or (now - last_logged[person_name]) >= COOLDOWN_SECONDS:
                        # Update the last logged time to reset the cooldown window
                        last_logged[person_name] = now

                        # Generate screenshot file name and path
                        # Using YYYYMMDD_HHMMSS format to ensure valid filesystem naming
                        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        screenshot_filename = f"{person_name}_{timestamp_str}.jpg"
                        screenshot_path = SCREENSHOT_DIR / screenshot_filename

                        # Save the raw video frame snapshot containing the match
                        cv2.imwrite(str(screenshot_path), frame)

                        # Log the detection event in our SQLite database via logger ORM
                        # We capture the string representation of source for reference
                        video_source_str = str(source)
                        log_match(
                            person_name=person_name,
                            confidence=confidence,
                            screenshot_path=str(screenshot_path),
                            video_source=video_source_str
                        )

                        # Print explicit alert console output
                        print(f"\n[ALERT] MATCH DETECTED!")
                        print(f"  Name: {person_name}")
                        print(f"  Confidence: {confidence:.4f}")
                        print(f"  Source: {video_source_str}")
                        print(f"  Screenshot Saved: {screenshot_path}\n")

            # Draw green bounding boxes on the window frame if rendering is enabled.
            # In automated environments (CIs, headless containers), we might not be able to call imshow.
            # We wrap it in a try-except block just in case cv2.imshow is not supported.
            try:
                for face in faces:
                    x1, y1, x2, y2 = face.bbox.astype(int)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.imshow("Video Processing Stream", frame)
                if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q")):
                    print("[Detector] Quit key pressed. Exiting loop.")
                    break
            except Exception:
                # If running headlessly (no display driver or X-server), ignore GUI window display errors
                pass

    finally:
        # Clean up capture devices and windows
        cap.release()
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        print("[Detector] Video source released and windows destroyed.")
